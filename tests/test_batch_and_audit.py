import csv
import json

from tracker.audit import log_lookup, purge_audit, purge_cache
from tracker.batch import run_batch, write_csv
from tracker.geocode import GeoResult
from tracker.history import add_lookup, clear, recent
from tracker.lookup import lookup_number


def _write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "number"])
        writer.writeheader()
        writer.writerows(rows)


def test_batch_reports_valid_and_invalid_rows(tmp_path):
    source = tmp_path / "numbers.csv"
    _write_csv(
        source,
        [
            {"name": "A", "number": "+233241234567"},
            {"name": "B", "number": "not-a-number"},
            {"name": "C", "number": ""},
            {"name": "D", "number": "+16502530000"},
        ],
    )

    results, errors = run_batch(source)

    assert len(results) == 2
    assert len(errors) == 1
    assert errors[0]["row"] == 3
    assert results[0]["e164"] == "+233241234567"
    assert results[0]["formatted_international"].startswith("+233")

    out = write_csv(results, tmp_path / "out.csv")
    with out.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert "country" in rows[0]


def test_batch_geocodes_by_country(tmp_path):
    source = tmp_path / "numbers.csv"
    _write_csv(source, [{"name": "A", "number": "+233241234567"}])

    calls = []

    def fake_geocoder(country):
        calls.append(country)
        return GeoResult(lat=7.9, lng=-1.0, formatted=country, bounds=None, confidence=8)

    results, errors = run_batch(source, geocoder=fake_geocoder)
    assert not errors
    assert calls == ["Ghana"]
    assert results[0]["geo_lat"] == 7.9


def test_batch_missing_column(tmp_path):
    source = tmp_path / "numbers.csv"
    _write_csv(source, [{"name": "A", "number": "+233241234567"}])
    import pytest

    with pytest.raises(ValueError):
        run_batch(source, column="phone")


def test_audit_log_and_purge(tmp_path):
    path = tmp_path / "audit.jsonl"
    log_lookup(path, "+233241234567", source="test", purpose="unit test")
    entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert entries[0]["number"] == "+233241234567"
    assert entries[0]["purpose"] == "unit test"
    assert purge_audit(path) is True
    assert purge_audit(path) is False


def test_cache_purge(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("{}", encoding="utf-8")
    assert purge_cache(path) is True
    assert purge_cache(path) is False


def test_history_roundtrip(tmp_path):
    db = tmp_path / "history.db"
    metadata = lookup_number("+233241234567")
    add_lookup(db, metadata, source="test")
    rows = recent(db)
    assert rows[0]["e164"] == "+233241234567"
    assert rows[0]["source"] == "test"
    clear(db)
    assert recent(db) == []
