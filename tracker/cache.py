from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any


class JsonCache:
    """Small JSON-backed cache with per-entry TTL and atomic writes."""

    def __init__(self, path: Path, ttl_seconds: int) -> None:
        self.path = Path(path)
        self.ttl_seconds = ttl_seconds
        self._lock = threading.Lock()

    def _load(self) -> dict[str, Any]:
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False)
        tmp.replace(self.path)

    def get(self, key: str) -> Any | None:
        with self._lock:
            data = self._load()
            entry = data.get(key)
            if not entry:
                return None
            if self.ttl_seconds >= 0 and time.time() - entry.get("ts", 0) > self.ttl_seconds:
                del data[key]
                self._save(data)
                return None
            return entry.get("value")

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            data = self._load()
            data[key] = {"ts": time.time(), "value": value}
            self._save(data)

    def clear(self) -> None:
        with self._lock:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
