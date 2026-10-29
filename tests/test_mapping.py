from tracker.geocode import GeoResult
from tracker.lookup import lookup_number
from tracker.mapping import build_map

BOUNDS = {
    "northeast": {"lat": 11.17, "lng": 1.20},
    "southwest": {"lat": 4.74, "lng": -3.26},
}


def test_map_uses_country_rectangle_not_point(tmp_path):
    metadata = lookup_number("+233 24 123 4567")
    geo = GeoResult(lat=7.95, lng=-1.03, formatted="Ghana", bounds=BOUNDS, confidence=8)

    destination = build_map(metadata, geo, tmp_path / "ghana.html")

    assert destination.exists()
    html = destination.read_text(encoding="utf-8")
    assert "Country-level" in html
    assert "not a device location" in html
    assert "rectangle" in html.lower()


def test_map_falls_back_to_approximate_circle(tmp_path):
    metadata = lookup_number("+233 24 123 4567")
    geo = GeoResult(lat=7.95, lng=-1.03, formatted="Ghana", bounds=None, confidence=5)

    destination = build_map(metadata, geo, tmp_path / "ghana.html")
    html = destination.read_text(encoding="utf-8")
    assert "Approximate" in html
