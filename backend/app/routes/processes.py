"""The five processes: what's at each stage, the playbook behind it, and its Run button."""

import logging
from collections import Counter

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..core.config import BACKEND_DIR
from ..core.database import SessionLocal, get_db
from ..engine import runner
from ..engine.playbook import get_playbook
from ..schemas.processes import LoanAtStage, PlaybookNode, PlaybookOut, ProcessDetail, ProcessSummary
from ..schemas.runs import ProcessRunQueued, ProcessRunRequest, RunQueued

router = APIRouter(prefix="/api/processes", tags=["processes"])
log = logging.getLogger(__name__)

NOT_REACHED = "Not reached"
WAITING = "Waiting"


def _stage_or_404(stage_no: int) -> models.Stage:
    stage = models.STAGE_BY_NO.get(stage_no)
    if stage is None:
        raise HTTPException(status_code=404, detail="Unknown stage")
    return stage


def _bucket(lm: models.LmStages | None, stage: models.Stage, has_docs: bool) -> str:
    position = runner.stage_position(lm, stage, has_docs)
    if position == "worked":
        return getattr(lm, f"{stage.key}_status")
    return WAITING if position == "waiting" else NOT_REACHED


def _summary(db: Session, stage: models.Stage, rows: list[tuple[models.Msp, models.LmStages | None]], with_docs: set[str]) -> dict:
    pb = get_playbook(stage.no)
    counts = Counter(_bucket(lm, stage, loan.loan_id in with_docs) for loan, lm in rows)
    run_counts = Counter(
        db.scalars(select(models.AgentRun.status).where(models.AgentRun.stage_no == stage.no, models.AgentRun.status.in_(runner.ACTIVE)))
    )
    return {
        "stage_no": stage.no,
        "name": stage.name,
        "key": stage.key,
        "allowed_statuses": list(stage.allowed),
        "advances": list(stage.advances),
        "playbook": pb is not None,
        "agent": pb.spec.agent if pb else None,
        "rules_version": pb.rules_version if pb else None,
        "counts": {s: counts.get(s, 0) for s in [NOT_REACHED, WAITING, *stage.allowed]},
        "waiting": counts.get(WAITING, 0),
        "runnable": len(runner.stage_candidates(db, stage.no)) if pb else 0,
        "running": run_counts.get("running", 0),
        "paused": run_counts.get("paused", 0),
    }


def _with_documents(db: Session) -> set[str]:
    return set(db.scalars(select(models.ExtractedData.loan_id)))


def _loan_rows(db: Session) -> list[tuple[models.Msp, models.LmStages | None]]:
    return list(
        db.execute(
            select(models.Msp, models.LmStages)
            .outerjoin(models.LmStages, models.LmStages.loan_id == models.Msp.loan_id)
            .order_by(models.Msp.borrower_name)
        )
    )


@router.get("", response_model=list[ProcessSummary])
def list_processes(db: Session = Depends(get_db)) -> list[ProcessSummary]:
    rows = _loan_rows(db)
    with_docs = _with_documents(db)
    return [ProcessSummary.model_validate(_summary(db, s, rows, with_docs)) for s in models.STAGES]


@router.get("/{stage_no}", response_model=ProcessDetail)
def get_process(stage_no: int, db: Session = Depends(get_db)) -> ProcessDetail:
    stage = _stage_or_404(stage_no)
    rows = _loan_rows(db)
    with_docs = _with_documents(db)
    last_runs: dict[str, models.AgentRun] = {}
    for run in db.scalars(select(models.AgentRun).where(models.AgentRun.stage_no == stage_no).order_by(models.AgentRun.started_at)):
        last_runs[run.loan_id] = run
    runnable = set(runner.stage_candidates(db, stage_no)) if get_playbook(stage_no) else set()
    open_decisions = {
        d.loan_id: d.id
        for d in db.scalars(select(models.Decision).where(models.Decision.stage_no == stage_no, models.Decision.status == "pending"))
    }
    loans = [
        LoanAtStage(
            loan_id=loan.loan_id,
            borrower_name=loan.borrower_name,
            status=getattr(lm, f"{stage.key}_status") if lm else None,
            position=runner.stage_position(lm, stage, loan.loan_id in with_docs),
            remark=(getattr(lm, f"{stage.key}_remark") if lm else "") or "",
            last_run_id=last_runs[loan.loan_id].id if loan.loan_id in last_runs else None,
            last_run_status=last_runs[loan.loan_id].status if loan.loan_id in last_runs else None,
            last_run_at=last_runs[loan.loan_id].started_at if loan.loan_id in last_runs else None,
            open_decision_id=open_decisions.get(loan.loan_id),
            runnable=loan.loan_id in runnable,
        )
        for loan, lm in rows
    ]
    return ProcessDetail.model_validate({**_summary(db, stage, rows, with_docs), "loans": loans})


@router.get("/{stage_no}/playbook", response_model=PlaybookOut)
def get_process_playbook(stage_no: int) -> PlaybookOut:
    _stage_or_404(stage_no)
    pb = get_playbook(stage_no)
    if pb is None:
        raise HTTPException(status_code=404, detail="No playbook for this stage yet")
    nodes = [
        PlaybookNode(
            id=name,
            title=n.title or name,
            kind=n.kind,
            run=n.run,
            routes=n.routes or ({"next": n.next} if n.next else {"approve": n.on_approve, "reject": n.on_reject} if n.gate else {}),
            team=n.team,
            status=n.status,
            advance=n.advance,
        )
        for name, n in pb.spec.nodes.items()
    ]
    return PlaybookOut(
        stage_no=stage_no,
        process=pb.spec.process,
        name=pb.spec.name,
        agent=pb.spec.agent,
        start=pb.spec.start,
        rules_version=pb.rules_version,
        nodes=nodes,
        rules=pb.rules,
        mermaid=pb.graph.get_graph().draw_mermaid(),
        files={
            str(path.relative_to(BACKEND_DIR)).replace("\\", "/"): path.read_text(encoding="utf-8")
            for path in (pb.path, pb.path.parent / pb.spec.rules)
        },
    )


def _run_stage_for(loan_ids: list[str], stage_no: int) -> None:
    for loan_id in loan_ids:
        lock = runner.loan_lock(loan_id)
        if not lock.acquire(blocking=False):
            continue
        try:
            with SessionLocal() as db:
                # Re-checks that the loan is still waiting here, then continues its workflow.
                if runner.continue_at_stage(db, loan_id, stage_no, trigger="manual") is not None:
                    db.commit()
        except Exception:
            log.exception("stage %s run failed for loan %s", stage_no, loan_id)
        finally:
            lock.release()


@router.post("/{stage_no}/run", response_model=ProcessRunQueued, response_model_exclude_none=True, status_code=202)
def run_process(stage_no: int, background: BackgroundTasks, body: ProcessRunRequest | None = None, db: Session = Depends(get_db)) -> RunQueued:
    """Run every loan waiting at this stage (or one loan). Each continues its own workflow, so it flows onward."""
    stage = _stage_or_404(stage_no)
    if get_playbook(stage_no) is None:
        raise HTTPException(status_code=409, detail=f"{stage.name} has no playbook yet")
    body = body or ProcessRunRequest()
    if body.rerun:
        if stage_no != 2:
            raise HTTPException(status_code=422, detail="Explicit re-run is supported only for Retention Eligibility")
        from ..engine import retention_runs

        result = retention_runs.queue(db, body.loan_id, body.requested_by)
        if body.loan_id and not result["queued"]:
            raise HTTPException(status_code=409, detail=result["skipped"][0]["reason"])
        background.add_task(retention_runs.execute, result["run_ids"])
        return ProcessRunQueued(**result)
    waiting = runner.stage_candidates(db, stage_no)
    if body.loan_id is not None:
        if body.loan_id not in waiting:
            raise HTTPException(status_code=409, detail=f"Loan {body.loan_id} is not waiting at {stage.name}")
        waiting = [body.loan_id]
    background.add_task(_run_stage_for, waiting, stage_no)
    return RunQueued(queued=len(waiting), loan_ids=waiting)
