"""Create a consistent SQLite snapshot and rotate backups older than 30 days."""

import argparse
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from .storage import DB, ROOT


def backup(directory):
    if not DB.is_file():
        raise FileNotFoundError(DB)
    directory.mkdir(parents=True, exist_ok=True)
    name = datetime.now(timezone.utc).strftime("recruiter-%Y%m%dT%H%M%S%fZ")
    temporary = directory / (name + ".tmp")
    output = directory / (name + ".sqlite3")
    source = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True)
    destination = sqlite3.connect(temporary)
    try:
        source.backup(destination)
        if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup integrity check failed.")
    finally:
        destination.close()
        source.close()
    os.replace(temporary, output)
    cutoff = time.time() - 30 * 24 * 60 * 60
    for previous in directory.glob("recruiter-*.sqlite3"):
        if previous.stat().st_mtime < cutoff:
            previous.unlink()
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=ROOT / "data" / "backups")
    print(backup(parser.parse_args().directory))
