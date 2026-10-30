"""Serve the React app from the API's own port, rebuilding it when the frontend source changes.

`uvicorn app.main:app --reload` then gives you the whole product on one port:
  * on startup, if anything in frontend/ is newer than frontend/dist, `npm run build` runs first;
  * while running, a watcher rebuilds after frontend edits (refresh the browser to see them);
  * without Node/npm (e.g. a server that ships a pre-built dist), it just serves what's there.

Turn either off with FRONTEND_AUTO_BUILD=false / FRONTEND_WATCH=false.
"""

import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .config import BACKEND_DIR, settings

log = logging.getLogger(__name__)

FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"
INDEX = DIST_DIR / "index.html"

# What a build depends on. node_modules and dist are deliberately not watched.
_SOURCES = ["src", "public", "index.html", "package.json", "package-lock.json", "vite.config.js"]
_build_lock = threading.Lock()
_stop = threading.Event()


def _newest_source_mtime() -> float:
    newest = 0.0
    for name in _SOURCES:
        path = FRONTEND_DIR / name
        if path.is_file():
            newest = max(newest, path.stat().st_mtime)
        elif path.is_dir():
            for f in path.rglob("*"):
                if f.is_file():
                    newest = max(newest, f.stat().st_mtime)
    return newest


def is_stale() -> bool:
    """True when there is no build, or a source file changed after the last one."""
    if not FRONTEND_DIR.is_dir():
        return False
    if not INDEX.is_file():
        return True
    return _newest_source_mtime() > INDEX.stat().st_mtime


def _npm() -> str | None:
    return shutil.which("npm")  # finds npm.cmd on Windows too


def build() -> bool:
    """Run `npm run build` (installing dependencies first if needed). Returns True on success."""
    npm = _npm()
    if npm is None:
        log.warning("Frontend changed but npm is not on PATH; serving the existing frontend/dist (if any).")
        return False
    with _build_lock:
        if not is_stale():  # another thread just built it
            return True
        steps = []
        if not (FRONTEND_DIR / "node_modules").is_dir():
            steps.append([npm, "ci" if (FRONTEND_DIR / "package-lock.json").is_file() else "install"])
        steps.append([npm, "run", "build"])
        started = time.perf_counter()
        for cmd in steps:
            log.info("Frontend: %s …", " ".join(cmd[1:]))
            result = subprocess.run(cmd, cwd=FRONTEND_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.returncode != 0:
                log.error("Frontend build failed (%s):\n%s", " ".join(cmd[1:]), (result.stdout + result.stderr)[-4000:])
                return False
        log.info("Frontend built in %.1fs → %s", time.perf_counter() - started, DIST_DIR)
        return True


def ensure_built() -> None:
    if settings.frontend_auto_build and is_stale():
        build()
    if not INDEX.is_file():
        log.warning("No frontend build at %s — the API works, the UI will not load until it is built.", DIST_DIR)


def _watch(interval: float) -> None:
    while not _stop.wait(interval):
        try:
            if is_stale():
                build()
        except Exception:  # noqa: BLE001 — never let the watcher die
            log.exception("Frontend watcher failed")


def start_watcher(interval: float = 2.0) -> None:
    if settings.frontend_auto_build and settings.frontend_watch and _npm() and FRONTEND_DIR.is_dir():
        _stop.clear()
        threading.Thread(target=_watch, args=(interval,), name="frontend-watch", daemon=True).start()


def stop_watcher() -> None:
    _stop.set()


def resolve(path: str) -> Path | None:
    """A file inside dist for this URL path, or None. Never escapes the dist folder."""
    if not path:
        return None
    candidate = (DIST_DIR / path).resolve()
    if DIST_DIR.resolve() in candidate.parents and candidate.is_file():
        return candidate
    return None
