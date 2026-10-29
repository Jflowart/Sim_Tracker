# SIM Tracker

So, here's the honest version of what this is.

You type in a phone number, and it tells you the stuff that's actually public about it: which country and region it's registered in, which carrier runs it, whether it's a mobile or a landline, and what timezone it sits in. Then it drops that onto a map so you can see the area at a glance.

What it does **not** do — and can't do — is find the person holding the phone. A phone number is not a GPS tracker. Anyone who tells you their tool gives you someone's exact live location from the number alone is selling you something fake, or something they got illegally. This one doesn't pretend otherwise. The map shows you a country, not a doorstep.

That's the deal. If that's what you need, keep reading.

---

## What you can actually do with it

**Look up a single number.** Type it in, get the metadata back, see the map. Useful when you just want to know if a number is real, what network it's on, or whether it's a mobile or a VoIP line.

**Throw a whole CSV at it.** Got a spreadsheet with hundreds or thousands of numbers? Upload it in the browser, and it'll churn through them in the background and hand you back an enriched CSV with all the metadata columns filled in. Invalid rows get separated out so you can fix them without digging through the whole file.

**Keep a history.** Every lookup gets saved locally, so you can search back through them later, filter by country or carrier, export the lot to CSV, or delete what you don't want.

**Run it from the command line too.** Same engine, if you'd rather script it or use it in a pipeline.

---

## Getting it running

You'll need Python 3.11 or newer. Everything lives in a virtual environment so it doesn't touch the rest of your machine.

```powershell
# one-time setup
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# start the web app
.\.venv\Scripts\python.exe app.py
```

Then open **http://127.0.0.1:5000** in your browser.

That's it for the basics. No API key needed — it uses OpenStreetMap's free geocoding by default, which is why maps work straight out of the box.

### If you want to tweak things

Copy `.env.example` to `.env` and open it. Most people won't need to touch anything, but a couple of things are worth knowing about:

- **`OPENCAGE_API_KEY`** — optional. If you happen to have an OpenCage key, paste it here and the tool will use it instead of the free fallback. It's a bit faster and more precise, but honestly the free option is fine for most use.
- **`DEFAULT_REGION`** — if you're mostly working with numbers from one country, set this (e.g. `GH` for Ghana) so you can type local-format numbers without the country code.
- **`BATCH_MAX_ROWS`** — how many rows a CSV upload can have at once. Defaults to 2000.
- **`BATCH_RETENTION_DAYS`** — how long processed batch files stick around before they're cleaned up. Defaults to 30 days.

---

## Using the command line

The original entry point still works:

```powershell
# look up a single number
.\.venv\Scripts\python.exe main_file.py --consent +233241234567

# get the answer as JSON, for scripting
.\.venv\Scripts\python.exe main_file.py --consent --json --no-geocode +16502530000

# enrich a CSV
.\.venv\Scripts\python.exe main_file.py --consent --csv numbers.csv
```

One thing to note: the `--consent` flag isn't decoration. It's there on purpose. By passing it (or ticking the box in the web app), you're confirming the number is yours or that you have a legitimate reason to look it up. See the section further down for why we bother.

Run `main_file.py --help` to see everything it can do.

---

## Where your data goes

Short answer: nowhere. Everything stays on your machine.

- Lookups are stored in `data/history.db`.
- Batch uploads and results live in `data/batches/` and `data/uploads/`.
- Geocoding results get cached in `data/geocode_cache.json` so it doesn't hammer the free service.
- Maps are saved as HTML files in `data/maps/`.

None of it is sent anywhere except the phone number's country name, which goes to OpenStreetMap (or OpenCage) to be turned into map coordinates. If that matters to you, you can turn map generation off entirely with `--no-geocode` on the CLI, or `GEOCODER=off` in `.env`.

You can wipe the audit log and geocode cache from the command line:

```powershell
.\.venv\Scripts\python.exe main_file.py --purge-audit
.\.venv\Scripts\python.exe main_file.py --purge-cache
```

---

## A quick, important word on using this responsibly

Look, this tool exists because phone metadata is genuinely useful — for fraud checks, for validating a contact list, for figuring out whether a number is even real before you call it. But "useful" and "allowed" aren't the same thing.

Before you look up a number that isn't yours, ask yourself if you'd be comfortable explaining why you did, to the person, and to whoever regulates your industry. If the answer is shaky, don't. Depending on where you are, handling someone's phone data without a basis for it can run you straight into data protection law — in Ghana, that's the Data Protection Act (Act 843). Other countries have their own versions.

The tool gives you country-level facts, not identities, and that's deliberate. It won't reveal names, ID numbers, addresses, or live locations, and if you find yourself wanting it to, that's the moment to stop and think about what you're actually trying to do.

Use it on your own numbers, or on numbers you've been given clear permission to investigate. The consent checkbox is the least we could do to keep that front of mind.

---

## Wiring it into your own stuff

There are a couple of endpoints you can hit if you want to automate things:

- `POST /lookup` — same as the form. Send `number` and `consent=on`.
- `POST /batch` — multipart upload, fields `file`, `column`, and `consent=on`.
- `GET /batch/<id>/status` — returns JSON with the job's status and counts.

There's no authentication right now, which is fine because it's bound to `127.0.0.1`. If you ever expose this to a network, put a login in front of it first. Seriously.

---

## Running the tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

If they all pass, you've got a healthy install.

---

## What's under the hood

- `app.py` — the web application.
- `main_file.py` — the command-line entry point.
- `tracker/lookup.py` — the actual phone number parsing and metadata.
- `tracker/geocode.py` — turning country names into coordinates (OpenCage or the free OpenStreetMap fallback).
- `tracker/mapping.py` — building the map.
- `tracker/batch.py` and `tracker/jobs.py` — CSV ingestion and background processing.
- `tracker/history.py` — the local lookup database.
- `tracker/audit.py`, `tracker/cache.py`, `tracker/config.py` — the supporting bits.

It's just Python and a bit of HTML, nothing exotic. Feel free to poke around.
