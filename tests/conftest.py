import os
import tempfile

os.environ["TRACKER_DATA_DIR"] = tempfile.mkdtemp(prefix="tracker-tests-")
os.environ["OPENCAGE_API_KEY"] = ""
os.environ["GEOCODER"] = "off"
os.environ["DEFAULT_REGION"] = ""
