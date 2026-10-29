from __future__ import annotations

import csv
import io
import secrets
import threading
import uuid
from pathlib import Path

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    url_for,
)

from tracker.cache import JsonCache
from tracker.config import DISCLAIMER, get_settings
from tracker.geocode import GeocodeError, Geocoder
from tracker.history import (
    add_lookup,
    delete_all,
    delete_many,
    filter_options,
    init_db,
    search,
    stats,
)
from tracker.jobs import (
    STATUS_DONE,
    get as get_batch,
    list_all as list_batches,
    process as process_batch,
    purge_older_than,
    read_rows as read_batch_rows,
)
from tracker.jobs import create as create_batch
from tracker.lookup import InvalidNumberError, lookup_number
from tracker.mapping import build_map

settings = get_settings()
cache = JsonCache(settings.cache_path, settings.cache_ttl_hours * 3600)
geocoder = Geocoder(
    settings.geocoder,
    settings.opencage_key,
    cache,
    user_agent=settings.user_agent,
    nominatim_url=settings.nominatim_url,
    nominatim_email=settings.nominatim_email,
)
init_db(settings.history_path)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024


def _secret_key() -> str:
    import os

    env_key = os.getenv("FLASK_SECRET_KEY", "").strip()
    if env_key:
        return env_key
    key_file = Path(settings.data_dir) / ".secret_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    generated = secrets.token_hex(32)
    key_file.write_text(generated, encoding="utf-8")
    return generated


app.secret_key = _secret_key()
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


@app.context_processor
def inject_globals():
    return {
        "disclaimer": DISCLAIMER,
        "geocoder_name": geocoder.description,
        "version": "2.1.0",
        "batch_max_rows": settings.batch_max_rows,
        "batch_retention_days": settings.batch_retention_days,
    }


@app.get("/")
def dashboard():
    return render_template("dashboard.html", stats=stats(settings.history_path))


@app.route("/lookup", methods=["GET", "POST"])
def lookup():
    if request.method == "GET":
        return render_template("index.html", number="", error=None)

    if request.form.get("consent") != "on":
        return (
            render_template(
                "index.html",
                number=request.form.get("number", ""),
                error="Please confirm you have permission to look up this number.",
            ),
            400,
        )

    number = (request.form.get("number") or "").strip()
    try:
        metadata = lookup_number(number, settings.default_region)
    except InvalidNumberError as exc:
        return render_template("index.html", number=number, error=str(exc)), 400

    add_lookup(settings.history_path, metadata, source="web")

    map_url = None
    geo_error = None
    if geocoder.enabled and metadata.country:
        try:
            geo = geocoder.geocode(metadata.country)
            map_name = f"{uuid.uuid4().hex}.html"
            build_map(metadata, geo, settings.map_dir / map_name)
            map_url = url_for("map_file", name=map_name)
        except GeocodeError as exc:
            geo_error = str(exc)
    elif not geocoder.enabled:
        geo_error = "Geocoding is disabled. Set GEOCODER=nominatim or add OPENCAGE_API_KEY."

    return render_template(
        "result.html",
        metadata=metadata,
        map_url=map_url,
        geo_error=geo_error,
    )


@app.get("/maps/<path:name>")
def map_file(name: str):
    if not name.endswith(".html"):
        abort(404)
    return send_from_directory(Path(settings.map_dir), name, max_age=0)


@app.route("/history", methods=["GET", "POST"])
def history():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "delete":
            ids = [int(i) for i in request.form.getlist("ids") if i.isdigit()]
            removed = delete_many(settings.history_path, ids)
            flash(f"Deleted {removed} record(s).", "success")
        elif action == "clear":
            removed = delete_all(settings.history_path)
            flash(f"Cleared {removed} record(s).", "success")
        return redirect(url_for("history"))

    query = request.args.get("q", "").strip()
    country = request.args.get("country", "").strip()
    carrier = request.args.get("carrier", "").strip()
    number_type = request.args.get("number_type", "").strip()
    since = request.args.get("since", "").strip()
    page = max(1, request.args.get("page", 1, type=int))
    per_page = 25

    rows, total = search(
        settings.history_path,
        query=query,
        country=country,
        carrier=carrier,
        number_type=number_type,
        since=since,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    pages = max(1, (total + per_page - 1) // per_page)

    return render_template(
        "history.html",
        rows=rows,
        total=total,
        page=page,
        pages=pages,
        options=filter_options(settings.history_path),
        filters={
            "q": query,
            "country": country,
            "carrier": carrier,
            "number_type": number_type,
            "since": since,
        },
    )


@app.get("/history/export.csv")
def history_export():
    from tracker.history import all_matching

    rows = all_matching(
        settings.history_path,
        query=request.args.get("q", "").strip(),
        country=request.args.get("country", "").strip(),
        carrier=request.args.get("carrier", "").strip(),
        number_type=request.args.get("number_type", "").strip(),
        since=request.args.get("since", "").strip(),
    )
    buffer = io.StringIO()
    fieldnames = [
        "created_at",
        "input",
        "e164",
        "country",
        "location",
        "region",
        "carrier",
        "number_type",
        "timezones",
        "source",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    data = io.BytesIO(buffer.getvalue().encode("utf-8-sig"))
    return send_file(
        data,
        mimetype="text/csv",
        as_attachment=True,
        download_name="lookup_history.csv",
    )


@app.route("/batch", methods=["GET", "POST"])
def batch():
    if request.method == "POST":
        if request.form.get("consent") != "on":
            flash("Confirm you have permission to process these numbers.", "error")
            return redirect(url_for("batch"))

        uploaded = request.files.get("file")
        if not uploaded or not uploaded.filename:
            flash("Choose a CSV file to upload.", "error")
            return redirect(url_for("batch"))

        raw = uploaded.read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            flash("File must be UTF-8 encoded CSV.", "error")
            return redirect(url_for("batch"))

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            flash("CSV has no header row.", "error")
            return redirect(url_for("batch"))

        column = (request.form.get("column") or "number").strip()
        if column not in reader.fieldnames:
            flash(
                f"Column '{column}' not found. Available: {', '.join(reader.fieldnames)}",
                "error",
            )
            return redirect(url_for("batch"))

        row_count = sum(1 for _ in reader)
        if row_count == 0:
            flash("CSV has no data rows.", "error")
            return redirect(url_for("batch"))
        if row_count > settings.batch_max_rows:
            flash(
                f"File has {row_count} rows; the limit is {settings.batch_max_rows}.",
                "error",
            )
            return redirect(url_for("batch"))

        safe_name = Path(uploaded.filename).name
        stored = settings.uploads_dir / f"{uuid.uuid4().hex}_{safe_name}"
        stored.write_bytes(raw)

        batch_id = create_batch(settings.batches_path, safe_name, column, stored)
        worker = threading.Thread(
            target=process_batch,
            kwargs={
                "db_path": settings.batches_path,
                "batch_id": batch_id,
                "source_path": stored,
                "column": column,
                "output_dir": settings.batches_dir,
                "default_region": settings.default_region,
                "geocoder": geocoder.geocode if geocoder.enabled else None,
            },
            daemon=True,
        )
        worker.start()
        flash("Upload accepted. Processing has started.", "success")
        return redirect(url_for("batch_detail", batch_id=batch_id))

    purge_older_than(
        settings.batches_path, settings.batches_dir, settings.batch_retention_days
    )
    return render_template("batch.html", batches=list_batches(settings.batches_path))


@app.get("/batch/<batch_id>")
def batch_detail(batch_id: str):
    record = get_batch(settings.batches_path, batch_id)
    if not record:
        abort(404)
    preview = []
    if record["status"] == STATUS_DONE and record.get("rows_path"):
        preview = read_batch_rows(Path(record["rows_path"]), limit=100)
    return render_template("batch_detail.html", batch=record, preview=preview)


@app.get("/batch/<batch_id>/download")
def batch_download(batch_id: str):
    record = get_batch(settings.batches_path, batch_id)
    if not record or not record.get("rows_path"):
        abort(404)
    path = Path(record["rows_path"])
    if not path.exists():
        abort(404)
    return send_file(
        path,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"enriched_{record['source_name']}",
    )


@app.get("/batch/<batch_id>/errors")
def batch_errors(batch_id: str):
    record = get_batch(settings.batches_path, batch_id)
    if not record or not record.get("errors_path"):
        abort(404)
    path = Path(record["errors_path"])
    if not path.exists():
        abort(404)
    return send_file(
        path,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"errors_{record['source_name']}",
    )


@app.get("/batch/<batch_id>/status")
def batch_status(batch_id: str):
    record = get_batch(settings.batches_path, batch_id)
    if not record:
        abort(404)
    return {
        "id": record["id"],
        "status": record["status"],
        "valid": record["valid"],
        "invalid": record["invalid"],
        "total": record["total"],
        "error": record["error"],
    }


if __name__ == "__main__":
    app.run(host=settings.host, port=settings.port, debug=False)
