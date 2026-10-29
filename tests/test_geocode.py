import pytest

from tracker.cache import JsonCache
from tracker.geocode import Geocoder, GeocodeError, geocode_place


def test_provider_resolution():
    assert Geocoder("auto", "key", None).provider == "opencage"
    assert Geocoder("auto", "", None).provider == "nominatim"
    assert Geocoder("off", "key", None).provider == "off"
    assert Geocoder("opencage", "", None).provider == "off"
    assert Geocoder("nominatim", "key", None).provider == "nominatim"


def test_opencage_requires_key(tmp_path):
    cache = JsonCache(tmp_path / "cache.json", ttl_seconds=60)
    geocoder = Geocoder("opencage", "", cache)
    assert not geocoder.enabled
    with pytest.raises(GeocodeError):
        geocoder.geocode("Ghana")


def test_cache_hit_skips_client(tmp_path, monkeypatch):
    cache = JsonCache(tmp_path / "cache.json", ttl_seconds=60)
    cache.set(
        "opencage:v1:ghana",
        {
            "lat": 7.9,
            "lng": -1.0,
            "formatted": "Ghana",
            "bounds": None,
            "confidence": 9,
            "source": "opencage",
        },
    )

    def explode(*args, **kwargs):
        raise AssertionError("client should not be constructed on cache hit")

    monkeypatch.setattr("tracker.geocode.OpenCageGeocode", explode)
    result = Geocoder("opencage", "fake-key", cache, min_interval=0).geocode("Ghana")
    assert result.lat == 7.9
    assert result.confidence == 9


def test_successful_opencage_lookup_is_cached(tmp_path, monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def geocode(self, query):
            return [
                {
                    "geometry": {"lat": 7.95, "lng": -1.03},
                    "formatted": "Ghana",
                    "confidence": 8,
                    "bounds": {
                        "northeast": {"lat": 11.17, "lng": 1.20},
                        "southwest": {"lat": 4.74, "lng": -3.26},
                    },
                }
            ]

    monkeypatch.setattr("tracker.geocode.OpenCageGeocode", FakeClient)
    cache = JsonCache(tmp_path / "cache.json", ttl_seconds=60)

    result = Geocoder(
        "opencage", "fake-key", cache, retries=1, min_interval=0
    ).geocode("Ghana")
    assert result.lat == 7.95
    assert result.source == "opencage"
    assert result.bounds["northeast"]["lat"] == 11.17
    assert cache.get("opencage:v1:ghana") is not None


def test_opencage_no_results_raises(tmp_path, monkeypatch):
    class EmptyClient:
        def __init__(self, *args, **kwargs):
            pass

        def geocode(self, query):
            return []

    monkeypatch.setattr("tracker.geocode.OpenCageGeocode", EmptyClient)
    cache = JsonCache(tmp_path / "cache.json", ttl_seconds=60)
    with pytest.raises(GeocodeError):
        Geocoder("opencage", "fake-key", cache, retries=1, min_interval=0).geocode(
            "Nowhere"
        )


def test_nominatim_fallback_parses_bounding_box(tmp_path, monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return [
                {
                    "lat": "7.95",
                    "lon": "-1.03",
                    "display_name": "Ghana",
                    "boundingbox": ["4.74", "11.17", "-3.26", "1.20"],
                }
            ]

    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params, "headers": headers})
        return FakeResponse()

    monkeypatch.setattr("tracker.geocode.requests.get", fake_get)
    cache = JsonCache(tmp_path / "cache.json", ttl_seconds=60)

    result = Geocoder(
        "nominatim", "", cache, retries=1, min_interval=0
    ).geocode("Ghana")

    assert result.source == "nominatim"
    assert result.lat == 7.95
    assert result.bounds["southwest"] == {"lat": 4.74, "lng": -3.26}
    assert calls[0]["headers"]["User-Agent"]
    assert calls[0]["params"]["format"] == "jsonv2"
    assert cache.get("nominatim:v1:ghana") is not None


def test_nominatim_no_results_raises(tmp_path, monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return []

    monkeypatch.setattr(
        "tracker.geocode.requests.get",
        lambda *args, **kwargs: FakeResponse(),
    )
    cache = JsonCache(tmp_path / "cache.json", ttl_seconds=60)
    with pytest.raises(GeocodeError):
        Geocoder("nominatim", "", cache, retries=1, min_interval=0).geocode("Nowhere")


def test_backwards_compatible_helper(tmp_path, monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def geocode(self, query):
            return [{"geometry": {"lat": 1.0, "lng": 2.0}, "formatted": "X"}]

    monkeypatch.setattr("tracker.geocode.OpenCageGeocode", FakeClient)
    cache = JsonCache(tmp_path / "cache.json", ttl_seconds=60)
    result = geocode_place("X", "fake-key", cache, retries=1, min_interval=0)
    assert (result.lat, result.lng) == (1.0, 2.0)
