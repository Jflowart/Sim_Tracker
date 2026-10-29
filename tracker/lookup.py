from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

import phonenumbers
import pycountry
from phonenumbers import carrier, geocoder
from phonenumbers import timezone as pn_timezone

TYPE_LABELS = {
    phonenumbers.PhoneNumberType.FIXED_LINE: "fixed line",
    phonenumbers.PhoneNumberType.MOBILE: "mobile",
    phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed line or mobile",
    phonenumbers.PhoneNumberType.TOLL_FREE: "toll free",
    phonenumbers.PhoneNumberType.PREMIUM_RATE: "premium rate",
    phonenumbers.PhoneNumberType.SHARED_COST: "shared cost",
    phonenumbers.PhoneNumberType.VOIP: "VoIP",
    phonenumbers.PhoneNumberType.PERSONAL_NUMBER: "personal number",
    phonenumbers.PhoneNumberType.PAGER: "pager",
    phonenumbers.PhoneNumberType.UAN: "UAN",
    phonenumbers.PhoneNumberType.VOICEMAIL: "voicemail",
    phonenumbers.PhoneNumberType.UNKNOWN: "unknown",
}


class InvalidNumberError(ValueError):
    pass


@dataclass
class PhoneMetadata:
    input: str
    e164: str
    valid: bool
    country_code: int
    national_number: str
    country: str
    location: str
    region: str
    carrier: str
    number_type: str
    timezones: list[str]
    formatted: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def display_location(self) -> str:
        if self.country and self.location and self.location != self.country:
            return f"{self.country} ({self.location})"
        return self.country or self.location or self.region or "Unknown"


def normalize_number(raw: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", raw or "")
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    return cleaned


def parse_number(raw: str, default_region: str = "") -> phonenumbers.PhoneNumber:
    cleaned = normalize_number(raw)
    if not cleaned:
        raise InvalidNumberError("No phone number was provided.")
    if not cleaned.startswith("+") and not default_region:
        raise InvalidNumberError(
            "Include the country code (e.g. +233...) or set DEFAULT_REGION."
        )

    region = None if cleaned.startswith("+") else (default_region or None)
    try:
        parsed = phonenumbers.parse(cleaned, region)
    except phonenumbers.NumberParseException as exc:
        raise InvalidNumberError(str(exc)) from exc

    if not phonenumbers.is_valid_number(parsed):
        raise InvalidNumberError(
            "Invalid phone number. Include the country code (e.g. +233...) "
            "and double-check the digits."
        )
    return parsed


def _country_name(region_code: str, fallback: str) -> str:
    if region_code:
        record = pycountry.countries.get(alpha_2=region_code)
        if record:
            return record.name
    return fallback


def lookup_number(raw: str, default_region: str = "") -> PhoneMetadata:
    parsed = parse_number(raw, default_region)
    number_type = TYPE_LABELS.get(
        phonenumbers.number_type(parsed), "unknown"
    )
    region_code = geocoder.region_code_for_number(parsed) or ""
    location = geocoder.description_for_number(parsed, "en") or ""
    formatted = {
        "e164": phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.E164
        ),
        "international": phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL
        ),
        "national": phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.NATIONAL
        ),
        "rfc3966": phonenumbers.format_number(
            parsed, phonenumbers.PhoneNumberFormat.RFC3966
        ),
    }
    return PhoneMetadata(
        input=raw,
        e164=formatted["e164"],
        valid=True,
        country_code=parsed.country_code,
        national_number=str(parsed.national_number),
        country=_country_name(region_code, location),
        location=location,
        region=region_code,
        carrier=carrier.name_for_number(parsed, "en") or "Unknown / not publicly listed",
        number_type=number_type,
        timezones=list(pn_timezone.time_zones_for_number(parsed)),
        formatted=formatted,
    )
