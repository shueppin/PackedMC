"""
To suppress any updates add "dev" to version_history.json
"""

import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
import subprocess
import requests
import logging


logging.basicConfig(format="%(levelname)s %(name)s: %(message)s", level=logging.INFO)
logger = logging.getLogger("updater")


API_URL = f"https://api.github.com/repos/shueppin/PackedMC/releases/latest"
ZIP_URL = "https://github.com/shueppin/PackedMC/archive/refs/tags/{tag}.zip"

VERSION_HISTORY = "version_history.json"
DATA_FILE = "data.json"
DATA_BACKUP_FILE = "data_before_{tag}.json"

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
BACKUP_DIRECTORY = PROJECT_ROOT / "backup"


# Ensure correct directories exist
os.makedirs(BACKUP_DIRECTORY, exist_ok=True)  # creates all missing parents; no error if exists


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


def update_project():
    history = load_version_history()
    if "dev" in history:
        logger.info(f'Development mode is active, files are not updated. To deactivate, remove "dev" from the history.')
        return

    # Get latest tag
    latest_tag = get_latest_tag()
    if latest_tag in history:
        logger.info(f"{latest_tag} is already installed.")
        return

    # Create a backup of data.json before the update
    source = PROJECT_ROOT / DATA_FILE
    if source.exists():
        destination = BACKUP_DIRECTORY / DATA_BACKUP_FILE.format(tag=latest_tag)
        shutil.copy2(source, destination)

    # Extract and update files using temporary directory
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

    # After updating add the version tag
    history.append(latest_tag)
    save_version_history(history)

    # Remove the old backups, keep only the newest 3.
    for old_version_tag in history[:-3]:
        old_backup_path = BACKUP_DIRECTORY / DATA_BACKUP_FILE.format(tag=old_version_tag)
        if old_backup_path.exists():
            os.remove(old_backup_path)
            logger.info(f"Deleted {old_backup_path}...")

    logger.info(f"Updated to {latest_tag} successfully.")


def launch_background(script_path, args=None):
    script_path = Path(script_path)
    cmd = [sys.executable, str(script_path)]
    if args:
        cmd += list(args)

    subprocess.Popen(  # Take the output to the main console
        cmd,
        start_new_session=True,  # mostly helps on Unix/POSIX
    )


if __name__ == "__main__":
    try:
        # Check if it is being run by cmd installer, and if so change the path to the main python script
        if len(sys.argv) >= 2:
            if sys.argv[1] == "cmd_installer":
                sitecustomize_path = PROJECT_ROOT / "python" / "sitecustomize.py"
                # Change the installation and reconfigure that the main.py file will be run from now on
                with open(sitecustomize_path, encoding="utf-8") as sitecustomize_file:
                    content = sitecustomize_file.read()

                content = content.replace("updater.py", "main.py")

                with open(sitecustomize_path, "w", encoding="utf-8") as sitecustomize_file:
                    sitecustomize_file.write(content)

        # Download / Update all relevant files
        update_project()

        # Launch main file after installation
        if len(sys.argv) >= 2:
            if sys.argv[1] == "cmd_installer":
                # Run the main file
                launch_background("main.py")

    # Catch every exception and start the repair
    except BaseException as e:
        # TODO: Start the repair
        logger.error(f"Update failed: {e}")
        sys.exit(1)
