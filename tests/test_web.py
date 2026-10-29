import io
import time

import pytest

from app import app


@pytest.fixture()
def client():
    app.config.update(TESTING=True)
    with app.test_client() as test_client:
        yield test_client


def test_dashboard_renders(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Dashboard" in response.data
    assert b"Total lookups" in response.data


def test_lookup_form_requires_consent(client):
    response = client.post("/lookup", data={"number": "+233241234567"})
    assert response.status_code == 400
    assert b"permission" in response.data


def test_lookup_valid_number(client):
    response = client.post(
        "/lookup",
        data={"number": "+233241234567", "consent": "on"},
    )
    assert response.status_code == 200
    assert b"MTN" in response.data
    assert b"Africa/Accra" in response.data
    assert b"not" in response.data.lower()


def test_lookup_invalid_number(client):
    response = client.post(
        "/lookup",
        data={"number": "nonsense", "consent": "on"},
    )
    assert response.status_code == 400


def test_history_page_and_filters(client):
    client.post("/lookup", data={"number": "+233241234567", "consent": "on"})
    response = client.get("/history?country=Ghana")
    assert response.status_code == 200
    assert b"Ghana" in response.data


def test_history_export(client):
    client.post("/lookup", data={"number": "+233241234567", "consent": "on"})
    response = client.get("/history/export.csv")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert b"+233241234567" in response.data


def test_history_clear(client):
    response = client.post("/history", data={"action": "clear"}, follow_redirects=True)
    assert response.status_code == 200


def test_batch_requires_consent(client):
    response = client.post("/batch", data={}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Confirm" in response.data


def test_batch_upload_end_to_end(client):
    payload = b"name,number\nA,+233241234567\nB,+16502530000\n"
    data = {
        "consent": "on",
        "column": "number",
        "file": (io.BytesIO(payload), "numbers.csv"),
    }
    response = client.post(
        "/batch", data=data, content_type="multipart/form-data", follow_redirects=False
    )
    assert response.status_code == 302
    detail_url = response.headers["Location"]

    for _ in range(40):
        detail = client.get(detail_url)
        if b"done" in detail.data and b"Download enriched CSV" in detail.data:
            break
        time.sleep(0.25)

    assert b"Download enriched CSV" in detail.data


def test_batch_missing_column(client):
    payload = b"name,phone\nA,+233241234567\n"
    data = {
        "consent": "on",
        "column": "number",
        "file": (io.BytesIO(payload), "numbers.csv"),
    }
    response = client.post(
        "/batch", data=data, content_type="multipart/form-data", follow_redirects=True
    )
    assert response.status_code == 200
    assert b"not found" in response.data


def test_batch_detail_missing(client):
    response = client.get("/batch/doesnotexist")
    assert response.status_code == 404
