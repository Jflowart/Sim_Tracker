from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def log_lookup(
    path: Path,
    number: str,
    source: str = "cli",
    purpose: str = "",
    result: str = "ok",
) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "number": number,
        "source": source,
        "purpose": purpose,
        "result": result,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def purge_audit(path: Path) -> bool:
    try:
        Path(path).unlink()
        return True
    except FileNotFoundError:
        return False


def purge_cache(path: Path) -> bool:
    try:
        Path(path).unlink()
        return True
    except FileNotFoundError:
        return False
