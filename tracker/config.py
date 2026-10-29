from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    opencage_key: str
    default_region: str
    cache_path: Path
    audit_path: Path
    history_path: Path
    batches_path: Path
    map_dir: Path
    batches_dir: Path
    uploads_dir: Path
    cache_ttl_hours: int
    geocoder: str
    user_agent: str
    nominatim_url: str
    nominatim_email: str
    batch_max_rows: int
    batch_retention_days: int
    host: str
    port: int


def get_settings() -> Settings:
    data_dir = Path(os.getenv("TRACKER_DATA_DIR", str(BASE_DIR / "data")))
    map_dir = data_dir / "maps"
    batches_dir = data_dir / "batches"
    uploads_dir = data_dir / "uploads"
    for directory in (map_dir, batches_dir, uploads_dir):
        directory.mkdir(parents=True, exist_ok=True)

    return Settings(
        data_dir=data_dir,
        opencage_key=os.getenv("OPENCAGE_API_KEY", "").strip(),
        default_region=os.getenv("DEFAULT_REGION", "").strip().upper(),
        cache_path=data_dir / "geocode_cache.json",
        audit_path=data_dir / "audit.jsonl",
        history_path=data_dir / "history.db",
        batches_path=data_dir / "batches.db",
        map_dir=map_dir,
        batches_dir=batches_dir,
        uploads_dir=uploads_dir,
        cache_ttl_hours=int(os.getenv("CACHE_TTL_HOURS", "720")),
        geocoder=os.getenv("GEOCODER", "auto").strip().lower(),
        user_agent=os.getenv(
            "GEOCODER_USER_AGENT",
            os.getenv("OPENCAGE_USER_AGENT", "simtracker-osint/2.0"),
        ),
        nominatim_url=os.getenv(
            "NOMINATIM_URL", "https://nominatim.openstreetmap.org/search"
        ),
        nominatim_email=os.getenv("NOMINATIM_EMAIL", "").strip(),
        batch_max_rows=int(os.getenv("BATCH_MAX_ROWS", "2000")),
        batch_retention_days=int(os.getenv("BATCH_RETENTION_DAYS", "30")),
        host=os.getenv("FLASK_HOST", "127.0.0.1"),
        port=int(os.getenv("FLASK_PORT", "5000")),
    )


DISCLAIMER = (
    "This tool only returns public, country-level phone metadata "
    "(country, region, carrier, line type, timezone). It cannot locate a device "
    "or a person. Use it only for numbers you own or have explicit permission to "
    "investigate, and follow the privacy laws that apply to you."
)
