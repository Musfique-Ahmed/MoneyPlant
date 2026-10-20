r"""CLI to sync connected data sources from outside the backend process.

Intended for Windows Task Scheduler or cron so syncing continues even
when the FastAPI server is not running.

Usage (from the ``backend`` directory)::

    python ..\scripts\sync_sources.py --all
    python ..\scripts\sync_sources.py --source <SOURCE_ID>
    python ..\scripts\sync_sources.py --all --dry-run

Flags::

    --all          Sync every source whose schedule is due.
    --source ID    Sync exactly one source by id (ignores the schedule).
    --dry-run      Report what would run without touching the database.
    --list         List configured sources and exit.

Exit codes::

    0  success (or nothing was due)
    1  one or more sources failed
    2  a configuration/usage error

No credentials are ever printed. The script logs source ids and
counters only, matching the backend's logging policy.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the backend package importable when this file is run directly.
BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

import app.models  # noqa: E402, F401  (register every model)
from app.core.config import get_settings  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.models.data_source import DataSource  # noqa: E402
from app.services.sync.scheduler import due_sources  # noqa: E402
from app.services.sync.service import run_sync  # noqa: E402


def _session_factory():
    """Return a fresh Session factory.

    Resolved lazily (not at import time) so tests and embedders can point
    the CLI at a different database by patching
    ``app.db.session.SessionLocal``.
    """
    from app.db.session import SessionLocal

    return SessionLocal


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="sync_sources",
        description="Sync connected data sources (file / SQL) into MoneyPlant.",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--all", action="store_true", help="Sync every source that is due.")
    g.add_argument("--source", metavar="ID", help="Sync exactly one source id.")
    g.add_argument("--list", action="store_true", help="List sources and exit.")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would run without writing anything.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])

    settings = get_settings()
    configure_logging(level=settings.log_level, redact=settings.log_redact_financial)

    if not (args.all or args.source or args.list):
        print("error: choose one of --all, --source ID, --list", file=sys.stderr)
        return 2

    db = _session_factory()()
    try:
        if args.list:
            sources = db.execute(
                select(DataSource).order_by(DataSource.created_at.asc())
            ).scalars().all()
            if not sources:
                print("No data sources configured yet.")
                return 0
            print(f"{'ID':38} {'TYPE':5} {'SCHEDULE':9} {'ENABLED':8} {'LAST STATUS':12} NAME")
            for s in sources:
                print(
                    f"{s.id:38} {s.type:5} {s.schedule:9} "
                    f"{'yes' if s.enabled else 'no':8} {s.last_status:12} {s.name}"
                )
            return 0

        if args.source:
            target = db.get(DataSource, args.source)
            if target is None:
                print(f"error: data source not found: {args.source}", file=sys.stderr)
                return 2
            targets = [target]
        else:
            targets = due_sources(db)

        if not targets:
            print("No sources are due. Nothing to do.")
            return 0

        if args.dry_run:
            print(f"Dry run — {len(targets)} source(s) would sync:")
            for t in targets:
                print(f"  {t.id}  {t.type:5} {t.schedule:9} {t.name}")
            return 0

        failures = 0
        for t in targets:
            db.expire_all()
            try:
                run = run_sync(db, source_id=t.id, trigger="cli")
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                failures += 1
                print(
                    f"FAILED  {t.name} ({t.id}): {type(exc).__name__}",
                    file=sys.stderr,
                )
                continue
            # Human-readable, credential-free summary line.
            print(
                f"{run.status.upper():8} {t.name} ({t.id})  "
                f"read={run.rows_read} added={run.rows_added} "
                f"dup={run.rows_skipped_duplicate} rejected={run.rows_rejected}"
            )
            if run.status == "failed":
                failures += 1
        return 1 if failures else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())