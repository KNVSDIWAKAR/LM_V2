"""End-to-end: run the whole workflow now, and switch auto-flow on or off."""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..core.database import get_db
from ..engine import runner
from ..engine.scheduler import auto_flow
from ..schemas.runs import AutoFlowStatus, AutoFlowUpdate, RunQueued, RunRequest

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


@router.post("/run", response_model=RunQueued, status_code=202)
def run_workflow(background: BackgroundTasks, body: RunRequest | None = None, db: Session = Depends(get_db)) -> RunQueued:
    """Start or continue end-to-end runs for every loan that should move (or for one loan)."""
    body = body or RunRequest()
    candidates = runner.workflow_candidates(db)
    if body.loan_id is not None:
        if db.get(models.Msp, body.loan_id) is None:
            raise HTTPException(status_code=404, detail="Loan not found")
        candidates = [c for c in candidates if c[0] == body.loan_id]
        if not candidates:
            raise HTTPException(status_code=409, detail=f"Loan {body.loan_id} has nothing to run: its workflow is active, done, or waiting on documents")
    background.add_task(auto_flow.tick, "manual")
    return RunQueued(queued=len(candidates), loan_ids=[loan_id for loan_id, _ in candidates])


@router.get("/auto", response_model=AutoFlowStatus)
def get_auto_flow() -> AutoFlowStatus:
    return AutoFlowStatus.model_validate(auto_flow.status())


@router.put("/auto", response_model=AutoFlowStatus)
def set_auto_flow(body: AutoFlowUpdate) -> AutoFlowStatus:
    auto_flow.enabled = body.enabled
    return AutoFlowStatus.model_validate(auto_flow.status())
