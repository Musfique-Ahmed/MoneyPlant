"""Background scheduler for due data sources.

Design choice: a plain daemon thread, **not** APScheduler or Celery.

Why:
- The requirement is "run due sources while the backend is running". A
  single thread that wakes every ``SYNC_SCHEDULER_INTERVAL_SECONDS``
  and asks "is anything due?" is ~60 lines and has zero new
  dependencies. Adding APScheduler for this would be a heavy
  dependency for one job and a persistence story we do not need (a
  cron/Task Scheduler entry or the CLI covers the "backend not
  running" case).
- The thread is a daemon: it never blocks process shutdown.
- Every sync opens its own SQLAlchemy Session and closes it, so a
  long-running sync never pins a request-scoped connection.

Due logic (deterministic, no hidden randomness):

- ``manual`` sources are never run by the scheduler.
- ``disabled`` sources are never run.
- ``hourly`` sources are due when ``now - last_sync_at >= 70 min``.
- ``daily`` sources are due when ``now - last_sync_at >= 28 h``.
- A source that has never synced is due immediately.

The thread logs only structural fields (source id, counts). It never
logs row descriptions, amounts, or connection strings.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.data_source import (
    SCHEDULE_DAILY,
    SCHEDULE_HOURLY,
    DataSource,
)

logger = logging.getLogger(__name__)

# Slack on top of the nominal interval so a job that runs long doesn't
# immediately re-trigger on the next tick.
_HOURLY_DUE = timedelta(minutes=70)
_DAILY_DUE = timedelta(hours=28)


def is_due(source: DataSource, now: datetime | None = None) -> bool:
    """Deterministic 'should this source run now?' predicate."""
    now = now or datetime.now(timezone.utc)
    if not source.enabled:
        return False
    if source.schedule not in {SCHEDULE_HOURLY, SCHEDULE_DAILY}:
        # ``manual`` sources are only ever run explicitly.
        return False
    if source.last_sync_at is None:
        return True
    last = source.last_sync_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    age = now - last
    if source.schedule == SCHEDULE_HOURLY:
        return age >= _HOURLY_DUE
    if source.schedule == SCHEDULE_DAILY:
        return age >= _DAILY_DUE
    return False


def due_sources(db: Session, now: datetime | None = None) -> list[DataSource]:
    rows = (
        db.query(DataSource)
        .filter(DataSource.enabled.is_(True))
        .order_by(DataSource.last_sync_at.asc().nullslast())
        .all()
    )
    return [s for s in rows if is_due(s, now)]


def run_due_sources(session_factory, *, now: datetime | None = None) -> int:
    """Sync every due source. Returns the number of runs started.

    Each source gets its own session so one failure cannot poison the
    others, and a slow source cannot hold the caller's session open.
    """
    db = session_factory()
    try:
        targets = due_sources(db, now)
    finally:
        db.close()
    if not targets:
        return 0

    from app.services.sync.service import run_sync

    started = 0
    for t in targets:
        s = session_factory()
        try:
            run = run_sync(s, source_id=t.id, trigger="schedule")
            started += 1
            logger.info(
                "sync.scheduled_run",
                extra={
                    "event": "scheduled_sync",
                    "source_id": t.id,
                    "status": run.status,
                    "rows_added": run.rows_added,
                    "rows_skipped_duplicate": run.rows_skipped_duplicate,
                    "rows_rejected": run.rows_rejected,
                },
            )
        except Exception:  # noqa: BLE001 — one bad source must not stop the loop
            s.rollback()
            logger.exception(
                "sync.scheduled_run_error",
                extra={"event": "scheduled_sync_error", "source_id": t.id},
            )
        finally:
            s.close()
    return started


class SyncScheduler:
    """A daemon thread that calls :func:`run_due_sources` on an interval."""

    def __init__(self, session_factory, *, interval_seconds: int = 300) -> None:
        self._session_factory = session_factory
        # Floor at 30 s so a misconfigured env var cannot spin the CPU.
        self._interval = max(30, int(interval_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="moneyplant-sync-scheduler", daemon=True,
        )
        self._thread.start()
        logger.info(
            "sync.scheduler_started",
            extra={"event": "scheduler_started", "interval_seconds": self._interval},
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._thread = None
        logger.info("sync.scheduler_stopped", extra={"event": "scheduler_stopped"})

    def run_once(self) -> int:
        """Run one pass immediately. Used by the CLI and by tests."""
        return run_due_sources(self._session_factory)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                run_due_sources(self._session_factory)
            except Exception:  # noqa: BLE001 — never let the thread die
                logger.exception(
                    "sync.scheduler_tick_failed", extra={"event": "scheduler_tick_failed"},
                )
            # ``wait`` (not ``sleep``) so ``stop()`` takes effect promptly.
            self._stop.wait(self._interval)


__all__ = [
    "SyncScheduler",
    "is_due",
    "due_sources",
    "run_due_sources",
]