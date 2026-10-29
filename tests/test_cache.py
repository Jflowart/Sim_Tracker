import time

from tracker.cache import JsonCache


def test_cache_roundtrip(tmp_path):
    cache = JsonCache(tmp_path / "cache.json", ttl_seconds=60)
    cache.set("k", {"value": 1})
    assert cache.get("k") == {"value": 1}
    assert cache.get("missing") is None


def test_cache_expires(tmp_path):
    cache = JsonCache(tmp_path / "cache.json", ttl_seconds=0)
    cache.set("k", "v")
    time.sleep(0.01)
    assert cache.get("k") is None


def test_cache_clear(tmp_path):
    path = tmp_path / "cache.json"
    cache = JsonCache(path, ttl_seconds=60)
    cache.set("k", "v")
    cache.clear()
    assert not path.exists()
    assert cache.get("k") is None
