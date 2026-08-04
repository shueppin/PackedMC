import traceback
import os
import logging
import time
import requests
import shutil
import json
from datetime import datetime

# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QMessageBox, QProgressDialog
# noinspection PyPackageRequirements
from PyQt6.QtCore import Qt

from .file_paths import PACKEDMC_MINECRAFT_DATA_DIRECTORY

from minecraft_api.mod import InvalidModBaseUrl, get_download_url, NoModFileAvailable, APICooldown, TryAgainLater
from minecraft_api.minecraft import LATEST_RELEASE

# Import the MainWindow for Type Checking
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from interface import MainWindow

logger = logging.getLogger(__name__)


# This is the amount of seconds it should wait before checking something like the mod data or the mod download url again.
SKIP_WHEN_LAST_CHECKED_BEFORE = 600


def update_mod_files(main_window: MainWindow, instance_name: str, mods_data: dict[str, tuple[str, str, int]], mc_version: str, loader: str, output=True):
    """
    Go through all mods and try to get their download links (if they were not just checked recently).
    Then download the files if they don't already exist and remove the old mod versions.
    """
    data = main_window.data

    if mc_version == 'latest':
        mc_version = LATEST_RELEASE

    if not output:
        logger.info(f'Start updating mods in the background for {instance_name}.')

    actual_time = round(time.time())

    packedmc_mods_directory = os.path.join(PACKEDMC_MINECRAFT_DATA_DIRECTORY, 'mods', instance_name)
    os.makedirs(packedmc_mods_directory, exist_ok=True)  # Ensure it exists
    unneeded_files = os.listdir(packedmc_mods_directory)

    mods_not_found_for_this_version = []

    progress_dialog = None  # Define it
    if output:
        progress_dialog = QProgressDialog("Downloading mods...", "", 0, len(mods_data), main_window)  # empty cancel text
        progress_dialog.setCancelButton(None)  # remove cancel button
        progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress_dialog.setAutoClose(True)
        progress_dialog.setWindowTitle("Downloading mods...")
        progress_dialog.setAutoReset(True)
        progress_dialog.setMinimumDuration(0)

        progress_dialog.setFixedSize(300, 250)

    # Go through every mod and download it if needed
    for index, mod_name in enumerate(mods_data):
        if output:
            progress_dialog.setValue(index + 1)
            progress_dialog.setLabelText("Downloading mod: \n" + mod_name)

        try:
            old_download_url, old_filename, last_checked = mods_data[mod_name]
        except Exception:  # If there is a mistake in the data, then update it and use default values
            data['instances'][instance_name]['mods'][mod_name] = ('', '', 0)
            data.save()
            old_download_url, old_filename, last_checked = ('', '', 0)

        # Skip when it was last checked before our waiting interval
        if actual_time < last_checked + SKIP_WHEN_LAST_CHECKED_BEFORE:
            # Remove the old filename from the unneeded files, so it is not removed. Because it is just skipped.
            if old_filename in unneeded_files:
                unneeded_files.remove(old_filename)
            continue

        try:
            download_url, filename = get_download_url(data['mods'][mod_name]['url'], mc_version, loader)
            data['instances'][instance_name]['mods'][mod_name] = (download_url, filename, actual_time)

            # If the version is not already in the supported versions, then add it.
            if mc_version not in data['mods'][mod_name]['supported_versions']:
                data['mods'][mod_name]['supported_versions'].append(mc_version)
            data.save()

            # If the download url has changed or the file does not exist, then download the file
            file_path = os.path.join(packedmc_mods_directory, filename)
            if not os.path.exists(file_path) or old_download_url != download_url:
                response = requests.get(download_url)
                file_data = response.content
                with open(file_path, 'wb') as f:
                    f.write(file_data)

            # Remove the filename from the unneeded files, so it is not removed.
            if filename in unneeded_files:
                unneeded_files.remove(filename)
        except (InvalidModBaseUrl, NoModFileAvailable):
            # Mod unavailable, thus no possible download URL
            mods_not_found_for_this_version.append(mod_name)
            data['instances'][instance_name]['mods'][mod_name] = ('', '', last_checked)
            data.save()
        except (APICooldown, TryAgainLater):
            # Just do nothing. It will be tried again when playing this instance again.
            pass
        except Exception:
            traceback.print_exc()

    if output:
        progress_dialog.close()
        # If not all mods could be updated, show a message
        if len(mods_not_found_for_this_version) > 0:
            QMessageBox.information(main_window, 'Could not find all mods', f'Could not find a file for the following mods for {loader} {mc_version}: \n - {"\n - ".join(mods_not_found_for_this_version)}')

    # Delete all unneeded files (either from removed mods, or old versions of a mod)
    for unneeded_filename in unneeded_files:
        os.remove(os.path.join(packedmc_mods_directory, unneeded_filename))

    if not output:
        logger.info(f'Updated mods in the background for {instance_name}.')


def move_mods_from_packedmc_to_minecraft(instance_name: str, minecraft_directory: str):
    # Update the mods
    packedmc_mods_directory = os.path.join(PACKEDMC_MINECRAFT_DATA_DIRECTORY, 'mods', instance_name)

    # Get all the files in the mods directory which were not copied by PackedMC
    try:
        mods_directory = os.path.join(minecraft_directory, 'mods')
        os.makedirs(mods_directory, exist_ok=True)  # Creates the mod folder if it does not already exist

        packedmc_copied_mods_file = os.path.join(mods_directory, 'packedmc.json')
        if os.path.exists(packedmc_copied_mods_file):
            with open(packedmc_copied_mods_file, 'r') as f:
                old_packedmc_copied_files: list[str] = json.load(f)
        else:
            old_packedmc_copied_files = []
        old_packedmc_copied_files.append('packedmc.json')

        with os.scandir(mods_directory) as it:
            actual_mod_files = [entry.name for entry in it if entry.is_file()]

        for filename in old_packedmc_copied_files:
            if filename in actual_mod_files:
                actual_mod_files.remove(filename)

        # Store all the mods which were not copied by PackedMC in a backup folder
        if len(actual_mod_files) > 0:
            backup_directory_name = 'packedmc_backup_' + datetime.now().isoformat(timespec='seconds').replace('T', '_').replace(':', '-')
            backup_directory = os.path.join(mods_directory, backup_directory_name)
            os.mkdir(backup_directory)
            for filename in actual_mod_files:
                shutil.move(os.path.join(mods_directory, filename), backup_directory)

        # Remove all the files which are not replaced soon with the files from the PackedMC mods directory
        new_mod_files = os.listdir(packedmc_mods_directory)
        for filename in old_packedmc_copied_files:
            if filename not in new_mod_files:
                if os.path.exists(os.path.join(mods_directory, filename)):
                    os.remove(os.path.join(mods_directory, filename))

        # Copy all files from the packedmc mods folder to the minecraft mods folder and list them in the JSON file
        for filename in new_mod_files:
            shutil.copy2(os.path.join(packedmc_mods_directory, filename), mods_directory)

        with open(packedmc_copied_mods_file, 'w') as f:
            json.dump(new_mod_files, f)
    except Exception:
        traceback.print_exc()
