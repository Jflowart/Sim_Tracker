from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import requests
from opencage.geocoder import OpenCageGeocode

from .cache import JsonCache

NOMINATIM_DEFAULT_URL = "https://nominatim.openstreetmap.org/search"


class GeocodeError(RuntimeError):
    pass


@dataclass
class GeoResult:
    lat: float
    lng: float
    formatted: str
    bounds: dict[str, Any] | None
    confidence: int | None
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "lat": self.lat,
            "lng": self.lng,
            "formatted": self.formatted,
            "bounds": self.bounds,
            "confidence": self.confidence,
            "source": self.source,
        }


_throttle_lock = threading.Lock()
_last_call = 0.0


def _throttle(min_interval: float) -> None:
    """Nominatim's usage policy is max 1 request/second. Apply it to every
    provider so switching providers never exceeds it."""
    global _last_call
    with _throttle_lock:
        wait = min_interval - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


class Geocoder:
    def __init__(
        self,
        mode: str,
        opencage_key: str,
        cache: JsonCache,
        user_agent: str = "simtracker-osint/2.0",
        nominatim_url: str = NOMINATIM_DEFAULT_URL,
        nominatim_email: str = "",
        retries: int = 3,
        min_interval: float = 1.0,
    ) -> None:
        self.mode = (mode or "auto").lower()
        self.opencage_key = opencage_key
        self.cache = cache
        self.user_agent = user_agent or "simtracker-osint/2.0"
        self.nominatim_url = nominatim_url or NOMINATIM_DEFAULT_URL
        self.nominatim_email = nominatim_email
        self.retries = retries
        self.min_interval = min_interval
        self.provider = self._resolve(self.mode, opencage_key)

    @staticmethod
    def _resolve(mode: str, key: str) -> str:
        if mode == "off":
            return "off"
        if mode == "opencage":
            return "opencage" if key else "off"
        if mode == "nominatim":
            return "nominatim"
        return "opencage" if key else "nominatim"

    @property
    def enabled(self) -> bool:
        return self.provider != "off"

    @property
    def description(self) -> str:
        if self.provider == "opencage":
            return "OpenCage"
        if self.provider == "nominatim":
            return "OpenStreetMap Nominatim (keyless)"
        return "disabled"

    def geocode(self, query: str) -> GeoResult:
        query = (query or "").strip()
        if not query:
            raise GeocodeError("Nothing to geocode.")
        if self.provider == "off":
            raise GeocodeError(
                "Geocoding is disabled. Add OPENCAGE_API_KEY or set GEOCODER=nominatim."
            )

        key = f"{self.provider}:v1:{query.lower()}"
        cached = self.cache.get(key)
        if cached:
            return GeoResult(**cached)

        if self.provider == "opencage":
            result = self._opencage(query)
        else:
            result = self._nominatim(query)

        self.cache.set(key, result.to_dict())
        return result

    def _opencage(self, query: str) -> GeoResult:
        client = OpenCageGeocode(
            self.opencage_key, user_agent_comment=self.user_agent or None
        )
        last_error: Exception | None = None

        for attempt in range(self.retries):
            try:
                _throttle(self.min_interval)
                results = client.geocode(query)
            except Exception as exc:
                last_error = exc
                time.sleep(2**attempt)
                continue

            if not results:
                raise GeocodeError(f"No geocoding result found for '{query}'.")

            first = results[0]
            geometry = first.get("geometry") or {}
            if geometry.get("lat") is None or geometry.get("lng") is None:
                raise GeocodeError(f"No coordinates returned for '{query}'.")

            return GeoResult(
                lat=float(geometry["lat"]),
                lng=float(geometry["lng"]),
                formatted=first.get("formatted", query),
                bounds=first.get("bounds"),
                confidence=(first.get("confidence") or None),
                source="opencage",
            )

        raise GeocodeError(f"Geocoding failed after {self.retries} attempts: {last_error}")

    def _nominatim(self, query: str) -> GeoResult:
        headers = {
            "User-Agent": self.user_agent,
            "Accept-Language": "en",
        }
        params: dict[str, Any] = {
            "q": query,
            "format": "jsonv2",
            "limit": 1,
            "addressdetails": 0,
        }
        if self.nominatim_email:
            params["email"] = self.nominatim_email

        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                _throttle(self.min_interval)
                response = requests.get(
                    self.nominatim_url, params=params, headers=headers, timeout=20
                )
                if response.status_code == 429:
                    last_error = GeocodeError("Nominatim rate limit hit (HTTP 429).")
                    time.sleep(2 * (attempt + 1))
                    continue
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:
                last_error = exc
                time.sleep(2**attempt)
                continue

            if not payload:
                raise GeocodeError(f"No geocoding result found for '{query}'.")

            first = payload[0]
            bbox = first.get("boundingbox") or []
            bounds = None
            if len(bbox) == 4:
                south, north, west, east = (float(value) for value in bbox)
                bounds = {
                    "southwest": {"lat": south, "lng": west},
                    "northeast": {"lat": north, "lng": east},
                }

            return GeoResult(
                lat=float(first["lat"]),
                lng=float(first["lon"]),
                formatted=first.get("display_name", query),
                bounds=bounds,
                confidence=None,
                source="nominatim",
            )

        raise GeocodeError(f"Geocoding failed after {self.retries} attempts: {last_error}")


def geocode_place(
    query: str,
    api_key: str,
    cache: JsonCache,
    user_agent: str = "",
    retries: int = 3,
    min_interval: float = 1.0,
) -> GeoResult:
    """Backwards-compatible OpenCage helper."""
    return Geocoder(
        "opencage",
        api_key,
        cache,
        user_agent=user_agent,
        retries=retries,
        min_interval=min_interval,
    ).geocode(query)
