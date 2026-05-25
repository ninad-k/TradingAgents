"""
Standalone scheduler worker for TradingAgents.

Pattern ported from HKUDS/AI-Trader's service/server/worker.py: a singleton
file-lock guards against double-spawn, and the scheduler runs in this process
so heavy analysis work does not compete with FastAPI request handlers.

Usage:
    # Recommended layout — two processes:
    #   Terminal 1: standalone worker (this script)
    #   Terminal 2: dashboard API with the in-process scheduler disabled

    WATCHLIST_DISABLE_IN_PROCESS=1 \\
        uvicorn tradingagents.api.dashboard_api:app --host 127.0.0.1 --port 8000

    python -m tradingagents.monitor.worker

NOTE: scheduler/watchlist state is currently in-memory module-level singletons,
so the worker process and the API process do NOT share results. The split
gives you process isolation today, and is the natural seam to add JSON-file
or SQLite persistence later — see HKUDS/AI-Trader's database.py for inspiration.
"""

from __future__ import annotations

import fcntl
import logging
import os
import signal
import sys
import time
from contextlib import suppress
from typing import Optional, IO

from tradingagents.dataflows.config import get_config
from tradingagents.monitor.scheduler import scheduler

logger = logging.getLogger(__name__)


DEFAULT_LOCK_PATH = "/tmp/tradingagents-worker.lock"


def _acquire_file_lock(lock_path: str) -> Optional[IO[str]]:
    handle = open(lock_path, "w", encoding="utf-8")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        logger.warning(
            "Another TradingAgents worker is already running (lock=%s).",
            lock_path,
        )
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def _release_file_lock(handle: Optional[IO[str]]) -> None:
    if handle is None:
        return
    with suppress(Exception):
        fcntl.flock(handle, fcntl.LOCK_UN)
    with suppress(Exception):
        handle.close()


def _install_nice_value() -> None:
    try:
        os.nice(int(os.getenv("TRADINGAGENTS_WORKER_NICE", "10")))
    except (ValueError, OSError):
        pass


def main() -> int:
    logging.basicConfig(
        level=os.getenv("TRADINGAGENTS_WORKER_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    lock_path = os.getenv("TRADINGAGENTS_WORKER_LOCK_FILE", DEFAULT_LOCK_PATH)
    handle = _acquire_file_lock(lock_path)
    if handle is None:
        return 1

    _install_nice_value()

    config = get_config()
    scheduler.set_config(config)
    scheduler.start()
    logger.info("TradingAgents worker started (lock=%s, pid=%d)", lock_path, os.getpid())

    stop = {"flag": False}

    def _shutdown(signum, _frame):
        logger.info("Received signal %s, stopping worker.", signum)
        stop["flag"] = True

    for signame in ("SIGINT", "SIGTERM"):
        with suppress(Exception):
            signal.signal(getattr(signal, signame), _shutdown)

    try:
        while not stop["flag"]:
            time.sleep(1)
    finally:
        scheduler.stop()
        _release_file_lock(handle)
        logger.info("TradingAgents worker stopped.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
