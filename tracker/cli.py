from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from .audit import log_lookup, purge_audit, purge_cache
from .batch import run_batch, write_csv
from .cache import JsonCache
from .config import DISCLAIMER, get_settings
from .geocode import Geocoder, GeocodeError
from .lookup import InvalidNumberError, PhoneMetadata, lookup_number
from .mapping import build_map


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main_file.py",
        description=(
            "Legal phone metadata OSINT tool. Returns country-level data only "
            "(country, region, carrier, line type, timezone)."
        ),
    )
    parser.add_argument("numbers", nargs="*", help="Phone number(s) in international format, e.g. +233241234567")
    parser.add_argument("--csv", type=Path, help="Enrich a CSV file of numbers instead of single numbers.")
    parser.add_argument("--column", default="number", help="CSV column containing numbers (default: number).")
    parser.add_argument("--out", type=Path, help="Output CSV path for batch mode.")
    parser.add_argument("--limit", type=int, help="Maximum rows to process in batch mode.")
    parser.add_argument("--region", default=None, help="Default ISO region for numbers without a country code.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--no-geocode", action="store_true", help="Skip OpenCage geocoding and maps.")
    parser.add_argument("--no-map", action="store_true", help="Skip map generation.")
    parser.add_argument("--no-open", action="store_true", help="Do not open the generated map in a browser.")
    parser.add_argument(
        "--consent",
        action="store_true",
        help="Confirm you own the numbers or have explicit permission to investigate them.",
    )
    parser.add_argument("--purpose", default="", help="Purpose recorded in the audit log.")
    parser.add_argument("--purge-audit", action="store_true", help="Delete the audit log and exit.")
    parser.add_argument("--purge-cache", action="store_true", help="Delete the geocode cache and exit.")
    return parser


def _print_metadata(metadata: PhoneMetadata) -> None:
    print(f"Number       {metadata.formatted['international']}")
    print(f"E.164        {metadata.e164}")
    print(f"Country      {metadata.display_location or 'Unknown'}")
    print(f"Carrier      {metadata.carrier}")
    print(f"Line type    {metadata.number_type}")
    print(f"Timezone     {', '.join(metadata.timezones) or 'Unknown'}")
    print(f"National     {metadata.formatted['national']}")
    print(f"RFC 3966     {metadata.formatted['rfc3966']}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = get_settings()

    if args.purge_audit:
        print("Audit log deleted." if purge_audit(settings.audit_path) else "No audit log found.")
        return 0
    if args.purge_cache:
        print("Geocode cache deleted." if purge_cache(settings.cache_path) else "No cache found.")
        return 0

    if not args.consent:
        print(DISCLAIMER)
        print("\nRe-run with --consent once you have permission to look up the number(s).")
        return 2

    if not args.numbers and not args.csv:
        parser.print_help()
        return 2

    region = args.region or settings.default_region
    cache = JsonCache(settings.cache_path, settings.cache_ttl_hours * 3600)
    geocoder_service = Geocoder(
        settings.geocoder,
        settings.opencage_key,
        cache,
        user_agent=settings.user_agent,
        nominatim_url=settings.nominatim_url,
        nominatim_email=settings.nominatim_email,
    )
    geocoder = None
    if not args.no_geocode:
        if geocoder_service.enabled:
            geocoder = geocoder_service.geocode
            if geocoder_service.provider == "nominatim":
                print(
                    "Geocoding with OpenStreetMap Nominatim (keyless, 1 req/sec).",
                    file=sys.stderr,
                )
        else:
            print(
                "Warning: geocoding is disabled. Set GEOCODER=nominatim or add "
                "OPENCAGE_API_KEY; maps will be skipped.",
                file=sys.stderr,
            )

    if args.csv:
        try:
            results, errors = run_batch(
                args.csv,
                column=args.column,
                default_region=region,
                geocoder=geocoder,
                limit=args.limit,
            )
        except (FileNotFoundError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        output = args.out or args.csv.with_name(f"{args.csv.stem}_enriched.csv")
        write_csv(results, output)

        for row in results:
            log_lookup(settings.audit_path, row["e164"], source="cli-batch", purpose=args.purpose)
        for error in errors:
            log_lookup(
                settings.audit_path,
                error["input"],
                source="cli-batch",
                purpose=args.purpose,
                result="invalid",
            )

        print(f"Processed {len(results)} valid number(s); {len(errors)} invalid row(s).")
        for error in errors:
            print(f"  Row {error['row']}: {error['input']} -> {error['error']}")
        print(f"CSV written to {output.resolve()}")
        return 0

    payloads = []
    failures = 0

    for number in args.numbers:
        try:
            metadata = lookup_number(number, region)
        except InvalidNumberError as exc:
            log_lookup(settings.audit_path, number, source="cli", purpose=args.purpose, result="invalid")
            print(f"Error: {exc}", file=sys.stderr)
            failures += 1
            continue

        log_lookup(settings.audit_path, metadata.e164, source="cli", purpose=args.purpose)
        payloads.append(metadata.to_dict())

        if not args.json:
            _print_metadata(metadata)

        if (
            geocoder
            and metadata.country
            and not args.no_map
            and not args.json
            and len(args.numbers) == 1
        ):
            try:
                geo = geocoder(metadata.country)
                destination = settings.map_dir / f"{metadata.e164.lstrip('+')}.html"
                build_map(metadata, geo, destination)
                print(f"Map         {destination.resolve()}")
                if not args.no_open:
                    webbrowser.open(destination.resolve().as_uri())
            except GeocodeError as exc:
                print(f"Map skipped: {exc}", file=sys.stderr)

        if not args.json:
            print()

    if args.json:
        print(json.dumps(payloads, indent=2, ensure_ascii=False))

    return 1 if failures else 0
