"""Kairos 4 · Operations intelligence — sensors that watch every stage run.

Prevent: stop something wrong from happening even if a playbook were edited badly.
Detect:  record what a reviewer or a dashboard needs to see.
"""

from datetime import datetime
from typing import Any


def evaluate(state: dict[str, Any], rules: dict[str, Any], now: datetime) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Return (sensor readings, override). An override replaces the end-node result."""
    readings: list[dict[str, Any]] = []
    override = None
    result = state.get("result") or {}
    msp = (state.get("context") or {}).get("msp") or {}

    # Prevent · an active bankruptcy must never reach the handoff.
    bk_status = (msp.get("bankruptcy") or {}).get("status")
    if result.get("advance") and bk_status in (rules.get("bk_fc") or {}).get("bk_active_statuses", []):
        override = {"node": "sensor:prevent_bk_handoff", "status": "End Case", "advance": False, "team": rules["bk_fc"].get("bk_team")}
        readings.append({"sensor": "Prevent · BK before handoff", "result": "fired", "detail": "Active bankruptcy reached handoff; case ended instead"})
    else:
        readings.append({"sensor": "Prevent · BK before handoff", "result": "ok", "detail": "No active bankruptcy at handoff"})

    # Detect · mismatches flagged for review.
    flagged = [f for f in state.get("findings", []) if f.get("result") in ("fail", "review")]
    readings.append({"sensor": "Detect · mismatches", "result": "flagged" if flagged else "ok", "detail": f"{len(flagged)} finding(s) flagged for review"})

    # Detect · intake time against the SLA (documents received → stage finished).
    hours_allowed = (rules.get("sla") or {}).get("intake_hours")
    received = ((state.get("context") or {}).get("case") or {}).get("received_at")
    if hours_allowed and received:
        received_at = datetime.fromisoformat(received)
        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=now.tzinfo)
        hours = (now - received_at).total_seconds() / 3600
        readings.append(
            {
                "sensor": "Detect · intake SLA",
                "result": "breached" if hours > hours_allowed else "ok",
                "detail": f"{hours:.1f} h from documents received to intake decision (SLA {hours_allowed} h)",
                "hours": round(hours, 1),
            }
        )
    return readings, override
