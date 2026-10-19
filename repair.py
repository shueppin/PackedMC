"""
Repair script for PackedMC.
This will repair the updater and sitecustomize
"""

import json
import logging
import os
import tempfile
import urllib.request
from pathlib import Path


logging.basicConfig(format="%(levelname)s %(name)s: %(message)s", level=logging.INFO)
logger = logging.getLogger("repair")


API_URL = f"https://api.github.com/repos/shueppin/PackedMC/releases/latest"
RAW_URL = "https://raw.githubusercontent.com/shueppin/PackedMC/{ref}/{path}"
FALLBACK_REF = "main"  # Used when the latest release can't be determined

UPDATER_FILE = "updater.py"
MAIN_FILE = "main.py"
VERSION_HISTORY = "version_history.json"
REPAIRED_FLAG = "repaired"  # Passed to the updater so it doesn't call the repair again (prevents loops)

PROJECT_ROOT = Path(__file__).resolve().parent
SITECUSTOMIZE_PATH = PROJECT_ROOT / "python" / "sitecustomize.py"


def fetch(url, timeout=30):
    request = urllib.request.Request(url, headers={"User-Agent": "shueppin/PackedMC"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def get_branch_name():
    """ Latest release tag, or the fallback branch if that fails (e.g. rate limit). """
    try:
        return json.loads(fetch(API_URL))["tag_name"]
    except Exception as e:
        logger.warning(f"Could not get latest release ({e}), using '{FALLBACK_REF}' instead.")
        return FALLBACK_REF


def is_dev_mode():
    history_file = PROJECT_ROOT / VERSION_HISTORY
    try:
        with open(history_file, "r", encoding="utf-8") as f:
            return "dev" in json.load(f)
    except Exception:
        return False


def ensure_sitecustomize():
    """ Same as the updater: Ensure that main.py is directly started instead of updater.py. """
    if not SITECUSTOMIZE_PATH.exists():
        logger.warning(f"{SITECUSTOMIZE_PATH} not found, skipping.")
        return

    content = SITECUSTOMIZE_PATH.read_text(encoding="utf-8")
    fixed = content.replace(UPDATER_FILE, MAIN_FILE)

    if fixed != content:
        SITECUSTOMIZE_PATH.write_text(fixed, encoding="utf-8")
        logger.info("Fixed sitecustomize.py.")
    else:
        logger.info("sitecustomize.py is already correct.")


def download_updater():
    branch_name = get_branch_name()
    url = RAW_URL.format(ref=branch_name, path=UPDATER_FILE)
    logger.info(f"Downloading {UPDATER_FILE} ({branch_name})...")

    text = fetch(url).decode("utf-8")

    # Same line endings as the updater writes (CRLF)
    text = text.replace("\r\n", "\n").replace("\n", "\r\n")

    # Write to a temporary file first, so a failed write never leaves a half-written updater
    target = PROJECT_ROOT / UPDATER_FILE
    fd, tmp_path = tempfile.mkstemp(dir=PROJECT_ROOT, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(text.encode("utf-8"))
        os.replace(tmp_path, target)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise Exception(f"Could not create {UPDATER_FILE} ({branch_name}).")

    logger.info(f"{UPDATER_FILE} restored.")


if __name__ == "__main__":
    if is_dev_mode():
        logger.info('Development mode is active, nothing is repaired. To deactivate, remove "dev" from the history.')
        exit()

    try:
        ensure_sitecustomize()
    except Exception as e:
        logger.error(f"Could not fix sitecustomize.py: {e}")  # Not fatal, continue with the updater

    try:
        download_updater()
    except Exception as e:
        logger.error(f"Could not restore {UPDATER_FILE}: {e}")

    # TODO: Update / Download the requirements
