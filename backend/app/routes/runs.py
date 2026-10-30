"""Read the execution history. Runs are created by the engine (app/engine/runner.py), not by hand."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models
from ..core.database import get_db
from ..schemas.runs import AgentRunOut, WorkflowRunDetail, WorkflowRunOut

router = APIRouter(prefix="/api", tags=["runs"])

STAGE_NAMES = {s.no: s.name for s in models.STAGES}


def agent_out(run: models.AgentRun) -> AgentRunOut:
    return AgentRunOut.model_validate(
        {**{c: getattr(run, c) for c in AgentRunOut.model_fields if hasattr(run, c)}, "stage_name": STAGE_NAMES.get(run.stage_no, "")}
    )


def workflow_out(run: models.WorkflowRun, detail: bool = False) -> WorkflowRunOut | WorkflowRunDetail:
    data = {
        **{c: getattr(run, c) for c in WorkflowRunOut.model_fields if hasattr(run, c)},
        "current_stage_name": STAGE_NAMES.get(run.current_stage, "Done"),
        "stages_total": len(models.STAGES),
        "stages_completed": sum(1 for a in run.agent_runs if a.status == "completed" and (a.output or {}).get("advance")),
    }
    if detail:
        return WorkflowRunDetail.model_validate({**data, "agent_runs": [agent_out(a) for a in run.agent_runs]})
    return WorkflowRunOut.model_validate(data)


@router.get("/workflow-runs", response_model=list[WorkflowRunOut])
def list_workflow_runs(loan_id: str | None = None, db: Session = Depends(get_db)) -> list[WorkflowRunOut]:
    query = select(models.WorkflowRun).order_by(models.WorkflowRun.started_at.desc())
    if loan_id is not None:
        query = query.where(models.WorkflowRun.loan_id == loan_id)
    return [workflow_out(r) for r in db.scalars(query)]


@router.get("/workflow-runs/{run_id}", response_model=WorkflowRunDetail)
def get_workflow_run(run_id: str, db: Session = Depends(get_db)) -> WorkflowRunDetail:
    run = db.get(models.WorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return workflow_out(run, detail=True)


@router.get("/agent-runs", response_model=list[AgentRunOut])
def list_agent_runs(
    stage_no: int | None = None,
    workflow_run_id: str | None = None,
    loan_id: str | None = None,
    db: Session = Depends(get_db),
) -> list[AgentRunOut]:
    query = select(models.AgentRun).order_by(models.AgentRun.started_at.desc())
    if stage_no is not None:
        query = query.where(models.AgentRun.stage_no == stage_no)
    if workflow_run_id is not None:
        query = query.where(models.AgentRun.workflow_run_id == workflow_run_id)
    if loan_id is not None:
        query = query.where(models.AgentRun.loan_id == loan_id)
    return [agent_out(r) for r in db.scalars(query)]


@router.get("/agent-runs/{run_id}", response_model=AgentRunOut)
def get_agent_run(run_id: str, db: Session = Depends(get_db)) -> AgentRunOut:
    run = db.get(models.AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return agent_out(run)
