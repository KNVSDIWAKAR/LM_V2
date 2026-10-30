"""Auto-flow: a background loop that sends new cases through the workflow without anyone clicking.

Every `AUTO_FLOW_INTERVAL_SECONDS` it asks the runner which loans should move
(runner.workflow_candidates) and starts or continues their workflow runs. It is a simple
in-process loop; to scale out, replace it with a queue and workers that call the same
runner functions.
"""

import logging
import threading
from datetime import datetime, timezone

from ..core.config import settings
from ..core.database import SessionLocal
from . import runner

log = logging.getLogger(__name__)


class AutoFlow:
    def __init__(self) -> None:
        self.enabled = settings.auto_flow_enabled
        self.interval = settings.auto_flow_interval_seconds
        self.last_tick: datetime | None = None
        self.last_moved = 0
        self.last_error: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "interval_seconds": self.interval,
            "last_tick": self.last_tick,
            "last_moved": self.last_moved,
            "last_error": self.last_error,
        }

    def tick(self, trigger: str = "scheduled") -> int:
        """Move every candidate loan once. Returns how many loans moved."""
        moved = 0
        with SessionLocal() as db:
            candidates = runner.workflow_candidates(db)
        for loan_id, workflow in candidates:
            lock = runner.loan_lock(loan_id)
            if not lock.acquire(blocking=False):
                continue  # someone else is working this loan right now
            try:
                with SessionLocal() as db:
                    # Re-check under the lock: the list above may be stale by now.
                    fresh = dict(runner.workflow_candidates(db, loan_id))
                    if loan_id not in fresh:
                        continue
                    workflow = fresh[loan_id]
                    if workflow is None:
                        runner.start_workflow(db, loan_id, trigger=trigger, requested_by="auto-flow" if trigger == "scheduled" else "")
                    else:
                        runner.advance_workflow(db, workflow)
                    db.commit()
                    moved += 1
            except Exception:
                log.exception("auto-flow failed for loan %s", loan_id)
            finally:
                lock.release()
        return moved

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            if not self.enabled:
                continue
            try:
                self.last_moved = self.tick()
                self.last_error = None
            except Exception as err:  # noqa: BLE001 — keep the loop alive
                self.last_error = str(err)
                log.exception("auto-flow tick failed")
            self.last_tick = datetime.now(timezone.utc)

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="auto-flow", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()


auto_flow = AutoFlow()
