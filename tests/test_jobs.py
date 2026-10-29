import time

from tracker.jobs import (
    STATUS_DONE,
    STATUS_FAILED,
    create,
    get,
    list_all,
    process,
    purge_older_than,
    read_rows,
)


def _csv(path, rows):
    path.write_text("name,number\n" + "\n".join(rows), encoding="utf-8")


def test_process_records_results(tmp_path):
    db = tmp_path / "batches.db"
    source = tmp_path / "in.csv"
    _csv(source, ["A,+233241234567", "B,nonsense", "C,+16502530000"])

    job = create(db, "in.csv", "number", source)
    process(db, job, source, "number", tmp_path)

    record = get(db, job)
    assert record["status"] == STATUS_DONE
    assert record["valid"] == 2
    assert record["invalid"] == 1
    assert record["total"] == 3

    rows = read_rows(record["rows_path"])
    assert len(rows) == 2
    assert rows[0]["e164"] == "+233241234567"
    assert "formatted_international" in rows[0]

    errors = read_rows(record["errors_path"])
    assert len(errors) == 1


def test_process_failure_is_recorded(tmp_path):
    db = tmp_path / "batches.db"
    source = tmp_path / "in.csv"
    _csv(source, ["A,not-a-number"])

    job = create(db, "in.csv", "number", source)
    process(db, job, source, "number", tmp_path)

    record = get(db, job)
    assert record["status"] == STATUS_FAILED
    assert record["error"]


def test_list_and_get(tmp_path):
    db = tmp_path / "batches.db"
    source = tmp_path / "in.csv"
    _csv(source, ["A,+233241234567"])
    job = create(db, "in.csv", "number", source)
    assert get(db, job)["id"] == job
    assert len(list_all(db)) == 1
    assert get(db, "missing") is None


def test_purge_older_than(tmp_path):
    db = tmp_path / "batches.db"
    source = tmp_path / "in.csv"
    _csv(source, ["A,+233241234567"])
    job = create(db, "in.csv", "number", source)
    process(db, job, source, "number", tmp_path)

    assert purge_older_than(db, tmp_path, days=0) == 0
    assert purge_older_than(db, tmp_path, days=-1) == 0
    time.sleep(0.01)
    assert purge_older_than(db, tmp_path, days=0) == 0
    assert len(list_all(db)) == 1
