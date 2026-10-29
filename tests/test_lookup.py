import pytest

from tracker.lookup import InvalidNumberError, lookup_number, normalize_number, parse_number


def test_normalize_strips_formatting_and_handles_00():
    assert normalize_number("+233 (24) 123-4567") == "+233241234567"
    assert normalize_number("00233241234567") == "+233241234567"


def test_ghana_metadata():
    metadata = lookup_number("+233 24 123 4567")
    assert metadata.valid is True
    assert metadata.region == "GH"
    assert metadata.country == "Ghana"
    assert metadata.carrier == "MTN"
    assert metadata.number_type == "mobile"
    assert metadata.timezones == ["Africa/Accra"]
    assert metadata.formatted["e164"] == "+233241234567"


def test_us_number_uses_country_name_and_area_information():
    metadata = lookup_number("+1 (650) 253-0000")
    assert metadata.region == "US"
    assert metadata.country == "United States"
    assert "Mountain View" in metadata.location
    assert metadata.number_type in {"fixed line", "mobile", "fixed line or mobile"}


def test_national_number_with_default_region():
    metadata = lookup_number("024 123 4567", default_region="GH")
    assert metadata.e164 == "+233241234567"


def test_missing_plus_without_region_is_rejected():
    with pytest.raises(InvalidNumberError):
        parse_number("0241234567")


@pytest.mark.parametrize("raw", ["", "not a number", "+1 234", "+999 1234567890"])
def test_invalid_numbers(raw):
    with pytest.raises(InvalidNumberError):
        lookup_number(raw)
