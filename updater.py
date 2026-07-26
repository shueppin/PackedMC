import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import requests

import logging


logging.basicConfig(format="%(levelname)s %(name)s: %(message)s", level=logging.INFO)
logger = logging.getLogger("updater")


API_URL = f"https://api.github.com/repos/shueppin/PackedMC/releases/latest"
ZIP_URL = "https://github.com/shueppin/PackedMC/archive/refs/tags/{tag}.zip"

VERSION_HISTORY = "version_history.json"

# Directories and files to ignore
IGNORE = {
    ".git",
    ".venv",
    "__pycache__",
    ".gitignore",
    VERSION_HISTORY,
    "README.md",
    "data.json"
}


PROJECT_ROOT = Path(__file__).resolve().parent


def get_latest_tag():
    logger.info("Fetching latest release...")

    response = requests.get(API_URL, timeout=30)
    response.raise_for_status()

    return response.json()["tag_name"]


def load_version_history():
    history_file = PROJECT_ROOT / VERSION_HISTORY

    if not history_file.exists():
        return []

    with open(history_file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_version_history(history):
    history_file = PROJECT_ROOT / VERSION_HISTORY

    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4)


def download_zip(tag, destination):
    url = ZIP_URL.format(tag=tag)

    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()

        with open(destination, "wb") as f:
            for chunk in r.iter_content(8192):
                if chunk:
                    f.write(chunk)


def files_are_equal(a: Path, b: Path):
    try:
        text_a = a.read_bytes().decode("utf-8")
        text_b = b.read_bytes().decode("utf-8")

        text_a = text_a.replace("\n", "\r\n")
        text_b = text_b.replace("\n", "\r\n")

        return text_a == text_b

    except UnicodeDecodeError:
        return a.read_bytes() == b.read_bytes()


def copy_file(source: Path, destination: Path):
    try:
        # Read raw bytes
        data = source.read_bytes()

        # Try decoding as UTF-8 text
        text = data.decode("utf-8")

        # Normalize line endings
        text = text.replace("\n", "\r\n")

        # Write exact LF bytes
        destination.write_bytes(text.encode("utf-8"))

    except UnicodeDecodeError:
        # Binary file
        shutil.copy2(source, destination)


def should_ignore(relative_path: Path):
    path_str = relative_path.as_posix()

    for ignored in IGNORE:
        if path_str == ignored or path_str.startswith(ignored + "/"):
            return True

    return False


def sync_files(source_root: Path):
    logger.info("Updating files...")

    for source in source_root.rglob("*"):
        relative = source.relative_to(source_root)

        if should_ignore(relative):
            continue

        destination = PROJECT_ROOT / relative

        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue

        destination.parent.mkdir(parents=True, exist_ok=True)

        if not destination.exists():
            copy_file(source, destination)
            continue

        if not files_are_equal(source, destination):
            copy_file(source, destination)


def main():
    history = load_version_history()
    if "dev" in history:
        logger.info(f'Development mode is active. To deactivate, remove "dev" from the history.')
        return

    latest_tag = get_latest_tag()
    if latest_tag in history:
        logger.info(f"{latest_tag} is already installed.")
        return

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        zip_path = tmp / "source.zip"

        download_zip(latest_tag, zip_path)

        with zipfile.ZipFile(zip_path) as z:
            z.extractall(tmp)

        source_root = tmp / f"PackedMC-{latest_tag.strip("v")}"  # Somehow GitHub does only use "0.1" if the tag is "v0.1"

        if not source_root.exists():
            raise RuntimeError(f"Source directory not found: {source_root}")

        sync_files(source_root)

    history.append(latest_tag)
    save_version_history(history)

    logger.info(f"Updated to {latest_tag} successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"\nUpdate failed: {e}")
        sys.exit(1)
