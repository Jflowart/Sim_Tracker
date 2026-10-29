from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .lookup import PhoneMetadata

SCHEMA = """
CREATE TABLE IF NOT EXISTS lookups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    input TEXT NOT NULL,
    e164 TEXT NOT NULL,
    country TEXT,
    location TEXT,
    region TEXT,
    carrier TEXT,
    number_type TEXT,
    timezones TEXT,
    source TEXT NOT NULL,
    valid INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_lookups_created_at ON lookups (created_at);
CREATE INDEX IF NOT EXISTS idx_lookups_e164 ON lookups (e164);
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
        _migrate(connection)


def _existing_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _migrate(connection: sqlite3.Connection) -> None:
    """Bring databases created by earlier versions up to the current schema."""
    columns = _existing_columns(connection, "lookups")
    additions = {
        "input": "TEXT NOT NULL DEFAULT ''",
        "location": "TEXT DEFAULT ''",
        "region": "TEXT DEFAULT ''",
        "timezones": "TEXT DEFAULT ''",
        "valid": "INTEGER NOT NULL DEFAULT 1",
    }
    for name, definition in additions.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE lookups ADD COLUMN {name} {definition}")


def add_lookup(
    path: Path,
    metadata: PhoneMetadata,
    source: str = "web",
    valid: bool = True,
    when: datetime | None = None,
) -> None:
    init_db(path)
    timestamp = (when or datetime.now(timezone.utc)).astimezone(timezone.utc)
    with _connect(path) as connection:
        connection.execute(
            "INSERT INTO lookups (created_at, input, e164, country, location, region, "
            "carrier, number_type, timezones, source, valid) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                timestamp.isoformat(timespec="seconds"),
                metadata.input,
                metadata.e164,
                metadata.country,
                metadata.location,
                metadata.region,
                metadata.carrier,
                metadata.number_type,
                ", ".join(metadata.timezones),
                source,
                1 if valid else 0,
            ),
        )


def _build_filters(
    query: str = "",
    country: str = "",
    carrier: str = "",
    number_type: str = "",
    source: str = "",
    since: str = "",
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []

    if query:
        clauses.append("(e164 LIKE ? OR input LIKE ? OR country LIKE ? OR carrier LIKE ?)")
        needle = f"%{query}%"
        params.extend([needle, needle, needle, needle])
    if country:
        clauses.append("country = ?")
        params.append(country)
    if carrier:
        clauses.append("carrier = ?")
        params.append(carrier)
    if number_type:
        clauses.append("number_type = ?")
        params.append(number_type)
    if source:
        clauses.append("source = ?")
        params.append(source)
    if since:
        clauses.append("created_at >= ?")
        params.append(since)

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def search(
    path: Path,
    query: str = "",
    country: str = "",
    carrier: str = "",
    number_type: str = "",
    source: str = "",
    since: str = "",
    limit: int = 25,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    init_db(path)
    where, params = _build_filters(query, country, carrier, number_type, source, since)
    with _connect(path) as connection:
        total = connection.execute(
            f"SELECT COUNT(*) AS n FROM lookups{where}", params
        ).fetchone()["n"]
        rows = connection.execute(
            f"SELECT * FROM lookups{where} ORDER BY id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return [dict(row) for row in rows], total


def all_matching(
    path: Path,
    query: str = "",
    country: str = "",
    carrier: str = "",
    number_type: str = "",
    source: str = "",
    since: str = "",
    limit: int = 5000,
) -> list[dict[str, Any]]:
    init_db(path)
    where, params = _build_filters(query, country, carrier, number_type, source, since)
    with _connect(path) as connection:
        rows = connection.execute(
            f"SELECT * FROM lookups{where} ORDER BY id DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
    return [dict(row) for row in rows]


def recent(path: Path, limit: int = 15) -> list[dict[str, Any]]:
    init_db(path)
    with _connect(path) as connection:
        rows = connection.execute(
            "SELECT * FROM lookups ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def stats(path: Path) -> dict[str, Any]:
    init_db(path)
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS total, "
            "COUNT(DISTINCT e164) AS unique_numbers, "
            "COUNT(DISTINCT country) AS countries, "
            "MIN(created_at) AS first_seen, "
            "MAX(created_at) AS last_seen "
            "FROM lookups"
        ).fetchone()
        today = connection.execute(
            "SELECT COUNT(*) AS n FROM lookups WHERE created_at >= ?",
            (datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00+00:00"),),
        ).fetchone()["n"]
        by_country = connection.execute(
            "SELECT country, COUNT(*) AS n FROM lookups "
            "WHERE country <> '' GROUP BY country ORDER BY n DESC LIMIT 5"
        ).fetchall()
        by_carrier = connection.execute(
            "SELECT carrier, COUNT(*) AS n FROM lookups "
            "WHERE carrier <> '' GROUP BY carrier ORDER BY n DESC LIMIT 5"
        ).fetchall()

    return {
        "total": row["total"],
        "unique_numbers": row["unique_numbers"],
        "countries": row["countries"],
        "today": today,
        "first_seen": row["first_seen"],
        "last_seen": row["last_seen"],
        "by_country": [dict(r) for r in by_country],
        "by_carrier": [dict(r) for r in by_carrier],
    }


def filter_options(path: Path) -> dict[str, list[str]]:
    init_db(path)
    with _connect(path) as connection:
        countries = [
            r["country"]
            for r in connection.execute(
                "SELECT DISTINCT country FROM lookups WHERE country <> '' ORDER BY country"
            )
        ]
        carriers = [
            r["carrier"]
            for r in connection.execute(
                "SELECT DISTINCT carrier FROM lookups WHERE carrier <> '' ORDER BY carrier"
            )
        ]
        types = [
            r["number_type"]
            for r in connection.execute(
                "SELECT DISTINCT number_type FROM lookups WHERE number_type <> '' "
                "ORDER BY number_type"
            )
        ]
    return {"countries": countries, "carriers": carriers, "number_types": types}


def delete_many(path: Path, ids: list[int]) -> int:
    if not ids:
        return 0
    init_db(path)
    placeholders = ",".join("?" for _ in ids)
    with _connect(path) as connection:
        cursor = connection.execute(
            f"DELETE FROM lookups WHERE id IN ({placeholders})", ids
        )
    return cursor.rowcount


def delete_all(path: Path) -> int:
    init_db(path)
    with _connect(path) as connection:
        cursor = connection.execute("DELETE FROM lookups")
    return cursor.rowcount


def clear(path: Path) -> None:
    delete_all(path)
