import traceback
import os
import logging
import time
import requests

# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QMessageBox, QProgressDialog
# noinspection PyPackageRequirements
from PyQt6.QtCore import Qt

from .file_paths import PACKEDMC_MINECRAFT_DATA_DIRECTORY

from minecraft_api.mod import InvalidModBaseUrl, get_download_url, NoModFileAvailable, APICooldown, TryAgainLater

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
