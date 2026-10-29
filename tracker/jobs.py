from __future__ import annotations

import csv
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .batch import run_batch, write_csv

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source_name TEXT NOT NULL,
    column TEXT NOT NULL,
    status TEXT NOT NULL,
    total INTEGER NOT NULL DEFAULT 0,
    valid INTEGER NOT NULL DEFAULT 0,
    invalid INTEGER NOT NULL DEFAULT 0,
    rows_path TEXT,
    errors_path TEXT,
    error TEXT
);
"""


def _connect(path: Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(path: Path) -> None:
    with _connect(path) as connection:
        connection.executescript(SCHEMA)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create(
    db_path: Path,
    source_name: str,
    column: str,
    original_path: Path,
) -> str:
    init_db(db_path)
    batch_id = uuid.uuid4().hex
    with _connect(db_path) as connection:
        connection.execute(
            "INSERT INTO batches (id, created_at, updated_at, source_name, column, "
            "status, rows_path) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (batch_id, _now(), _now(), source_name, column, STATUS_PENDING, str(original_path)),
        )
    return batch_id


def set_status(
    db_path: Path,
    batch_id: str,
    status: str,
    valid: int | None = None,
    invalid: int | None = None,
    total: int | None = None,
    rows_path: str | None = None,
    errors_path: str | None = None,
    error: str | None = None,
) -> None:
    fields = ["status = ?", "updated_at = ?"]
    params: list[Any] = [status, _now()]
    for name, value in (
        ("valid", valid),
        ("invalid", invalid),
        ("total", total),
        ("rows_path", rows_path),
        ("errors_path", errors_path),
        ("error", error),
    ):
        if value is not None:
            fields.append(f"{name} = ?")
            params.append(value)
    params.append(batch_id)
    with _connect(db_path) as connection:
        connection.execute(
            f"UPDATE batches SET {', '.join(fields)} WHERE id = ?", params
        )


def get(db_path: Path, batch_id: str) -> dict[str, Any] | None:
    init_db(db_path)
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM batches WHERE id = ?", (batch_id,)
        ).fetchone()
    return dict(row) if row else None


def list_all(db_path: Path, limit: int = 50) -> list[dict[str, Any]]:
    init_db(db_path)
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM batches ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def process(
    db_path: Path,
    batch_id: str,
    source_path: Path,
    column: str,
    output_dir: Path,
    default_region: str = "",
    geocoder=None,
    limit: int | None = None,
) -> None:
    """Run the batch job and record results. Intended to run off the request thread."""
    set_status(db_path, batch_id, STATUS_RUNNING)
    try:
        results, errors = run_batch(
            source_path,
            column=column,
            default_region=default_region,
            geocoder=geocoder,
            limit=limit,
        )
        if not results:
            raise ValueError(
                f"No valid numbers found in column '{column}'."
            )

        rows_path = output_dir / f"{batch_id}_enriched.csv"
        errors_path = output_dir / f"{batch_id}_errors.csv"
        write_csv(results, rows_path)
        if errors:
            write_csv(errors, errors_path)

        set_status(
            db_path,
            batch_id,
            STATUS_DONE,
            total=len(results) + len(errors),
            valid=len(results),
            invalid=len(errors),
            rows_path=str(rows_path),
            errors_path=str(errors_path) if errors else "",
        )
    except Exception as exc:
        set_status(db_path, batch_id, STATUS_FAILED, error=str(exc))


def read_rows(path: Path, limit: int = 200) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for index, row in enumerate(reader):
            if index >= limit:
                break
            rows.append(row)
    return rows


def purge_older_than(db_path: Path, output_dir: Path, days: int) -> int:
    if days <= 0:
        return 0
    init_db(db_path)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT id, rows_path, errors_path FROM batches WHERE created_at < ?",
            (cutoff,),
        ).fetchall()
        ids = [row["id"] for row in rows]
        for row in rows:
            for stored in (row["rows_path"], row["errors_path"]):
                if stored:
                    try:
                        Path(stored).unlink()
                    except (OSError, TypeError):
                        pass
        if ids:
            placeholders = ",".join("?" for _ in ids)
            connection.execute(
                f"DELETE FROM batches WHERE id IN ({placeholders})", ids
            )
    return len(ids)
