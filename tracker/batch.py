from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Callable

from .lookup import InvalidNumberError, lookup_number


def run_batch(
    csv_path: Path,
    column: str = "number",
    default_region: str = "",
    geocoder: Callable[[str], Any] | None = None,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or column not in reader.fieldnames:
            raise ValueError(
                f"Column '{column}' not found. Available: {', '.join(reader.fieldnames or [])}"
            )

        for row_number, row in enumerate(reader, start=2):
            if limit is not None and len(results) >= limit:
                break
            raw = (row.get(column) or "").strip()
            if not raw:
                continue
            try:
                metadata = lookup_number(raw, default_region)
            except InvalidNumberError as exc:
                errors.append({"row": row_number, "input": raw, "error": str(exc)})
                continue

            record: dict[str, Any] = {"row": row_number}
            record.update(metadata.to_dict())
            for name, value in metadata.formatted.items():
                record[f"formatted_{name}"] = value
            record.pop("formatted")
            record.pop("input")

            if geocoder is not None and metadata.country:
                try:
                    geo = geocoder(metadata.country)
                    record.update(
                        {
                            "geo_lat": geo.lat,
                            "geo_lng": geo.lng,
                            "geo_bounds": geo.bounds,
                        }
                    )
                except Exception as exc:
                    record["geo_error"] = str(exc)

            results.append(record)

    return results, errors


def write_csv(rows: list[dict[str, Any]], destination: Path) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return destination
