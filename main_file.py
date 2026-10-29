"""Backwards-compatible entry point.

Usage:
    python main_file.py --consent +233241234567
    python main_file.py --consent --csv numbers.csv
    python app.py            # web dashboard
"""

from tracker.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
