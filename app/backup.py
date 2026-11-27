"""Back up and restore the database.

    python -m app.backup save /app/state/backups/2026-11-27.db
    python -m app.backup restore /app/state/backups/2026-11-27.db

Both use SQLite's online backup, which copies a consistent snapshot while the service keeps running.
A restore replaces everything in the live database with the copy, so stop sending requests first.
"""
import argparse
import sqlite3
from contextlib import closing
from pathlib import Path

from app import store
from app.config import settings


def _copy(source: Path, destination: Path) -> None:
    with closing(sqlite3.connect(source)) as origin, closing(sqlite3.connect(destination)) as target:
        origin.backup(target)


def save(destination: Path) -> Path:
    store.init()
    destination.parent.mkdir(parents=True, exist_ok=True)
    _copy(settings.database_path, destination)
    return destination


def restore(source: Path) -> None:
    if not source.is_file():  # sqlite3.connect would create an empty file and "restore" an empty database
        raise FileNotFoundError(source)
    _copy(source, settings.database_path)
    store.init()  # a backup taken by an older build is brought up to the current schema


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Back up or restore the database.")
    parser.add_argument("action", choices=["save", "restore"])
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    if args.action == "save":
        print(f"saved {save(args.file)}")
    else:
        restore(args.file)
        print(f"restored {settings.database_path} from {args.file}")
