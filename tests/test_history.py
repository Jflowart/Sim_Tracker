from tracker.history import (
    add_lookup,
    delete_all,
    delete_many,
    filter_options,
    recent,
    search,
    stats,
)
from tracker.lookup import lookup_number


def _seed(db):
    add_lookup(db, lookup_number("+233241234567"), source="web")
    add_lookup(db, lookup_number("+16502530000"), source="cli")
    add_lookup(db, lookup_number("+442079460958"), source="web")


def test_add_and_recent(tmp_path):
    db = tmp_path / "history.db"
    _seed(db)
    rows = recent(db, limit=10)
    assert len(rows) == 3
    assert rows[0]["e164"] == "+442079460958"


def test_search_by_text(tmp_path):
    db = tmp_path / "history.db"
    _seed(db)
    rows, total = search(db, query="233")
    assert total == 1
    assert rows[0]["country"] == "Ghana"


def test_search_by_country_filter(tmp_path):
    db = tmp_path / "history.db"
    _seed(db)
    rows, total = search(db, country="Ghana")
    assert total == 1
    assert rows[0]["e164"] == "+233241234567"


def test_search_pagination(tmp_path):
    db = tmp_path / "history.db"
    _seed(db)
    page1, total = search(db, limit=2, offset=0)
    page2, _ = search(db, limit=2, offset=2)
    assert total == 3
    assert len(page1) == 2
    assert len(page2) == 1
    assert {r["id"] for r in page1}.isdisjoint({r["id"] for r in page2})


def test_stats(tmp_path):
    db = tmp_path / "history.db"
    _seed(db)
    summary = stats(db)
    assert summary["total"] == 3
    assert summary["unique_numbers"] == 3
    assert summary["countries"] >= 2
    assert summary["today"] == 3
    assert summary["by_carrier"]


def test_filter_options(tmp_path):
    db = tmp_path / "history.db"
    _seed(db)
    options = filter_options(db)
    assert "Ghana" in options["countries"]
    assert "mobile" in options["number_types"]


def test_delete_many_and_all(tmp_path):
    db = tmp_path / "history.db"
    _seed(db)
    rows, _ = search(db)
    removed = delete_many(db, [rows[0]["id"], rows[1]["id"]])
    assert removed == 2
    assert search(db)[1] == 1
    assert delete_all(db) == 1
    assert search(db)[1] == 0
