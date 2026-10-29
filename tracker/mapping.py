from __future__ import annotations

import html
from pathlib import Path

import folium

from .geocode import GeoResult
from .lookup import PhoneMetadata


def _popup_html(metadata: PhoneMetadata) -> str:
    rows = [
        ("Number", metadata.formatted["international"]),
        ("Country", metadata.display_location),
        ("Carrier", metadata.carrier),
        ("Line type", metadata.number_type),
        ("Timezone", ", ".join(metadata.timezones) or "Unknown"),
    ]
    body = "".join(
        f"<tr><th style='text-align:left;padding:2px 8px 2px 0'>{html.escape(k)}</th>"
        f"<td style='padding:2px 0'>{html.escape(str(v))}</td></tr>"
        for k, v in rows
    )
    return f"<table style='font-size:12px'>{body}</table>"


def build_map(
    metadata: PhoneMetadata,
    geo: GeoResult,
    destination: Path,
) -> Path:
    """Render a country-level map. A rectangle is drawn for the country bounds,
    never a point pretending to be the device location."""
    bounds = geo.bounds
    if bounds and "southwest" in bounds and "northeast" in bounds:
        sw = bounds["southwest"]
        ne = bounds["northeast"]
        center = [(sw["lat"] + ne["lat"]) / 2, (sw["lng"] + ne["lng"]) / 2]
    else:
        sw = ne = None
        center = [geo.lat, geo.lng]

    map_obj = folium.Map(location=center, zoom_start=6, control_scale=True)
    popup = folium.Popup(_popup_html(metadata), max_width=320)

    if sw and ne:
        folium.Rectangle(
            bounds=[[sw["lat"], sw["lng"]], [ne["lat"], ne["lng"]]],
            color="#b23b3b",
            weight=2,
            fill=True,
            fill_opacity=0.08,
            tooltip="Country-level boundary, not a device location",
            popup=popup,
        ).add_to(map_obj)
        map_obj.fit_bounds([[sw["lat"], sw["lng"]], [ne["lat"], ne["lng"]]])
    else:
        folium.Circle(
            location=center,
            radius=75000,
            color="#b23b3b",
            weight=2,
            fill=True,
            fill_opacity=0.08,
            tooltip="Approximate country/region center, not a device location",
            popup=popup,
        ).add_to(map_obj)

    banner = folium.Element(
        "<div style='position:fixed;top:10px;left:50%;transform:translateX(-50%);"
        "z-index:9999;background:#fff3cd;color:#664d03;border:1px solid #ffecb5;"
        "padding:8px 14px;border-radius:6px;font:13px/1.35 system-ui,sans-serif;"
        "box-shadow:0 2px 8px rgba(0,0,0,.15);max-width:90%;'>"
        "Country-level metadata only. This is not a live device location.</div>"
    )
    map_obj.get_root().html.add_child(banner)

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    map_obj.save(str(destination))
    return destination
