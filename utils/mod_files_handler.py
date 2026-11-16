import os
import logging
import time
import threading
import uuid
import requests
import shutil
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from urllib3.exceptions import ReadTimeoutError
from PyQt6.QtCore import QObject, pyqtSignal

from pyqt_utils.progress_window import ProgressWindow
from utils.file_paths import PACKEDMC_MINECRAFT_DATA_DIRECTORY
from utils.data_file_helper import Data
from minecraft_api.mod import InvalidModBaseUrl, ModNotExisting, EmptyArguments, get_download_url, NoModFileAvailable, APICooldown, TryAgainLater, REQUEST_TIMEOUT
from minecraft_api.minecraft import LATEST_RELEASE

# Import the MainWindow for Type Checking
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from interface import MainWindow

logger = logging.getLogger(__name__)


# This is the amount of seconds it should wait before checking something like the mod data or the mod download url again.
SKIP_WHEN_LAST_CHECKED_BEFORE = 600

# Every network request for a mod (looking up the download URL and downloading the file) is aborted if the website does not
# answer or send any more data for this many seconds. This is not a limit for the whole download, so big files can still be downloaded.
MOD_REQUEST_TIMEOUT = REQUEST_TIMEOUT

_DOWNLOAD_CHUNK_SIZE = 64 * 1024


'''
Result types
'''


@dataclass
class ModUpdateResult:
    """ What happened when the mods of an instance were updated. """
    not_found: list[str] = field(default_factory=list)  # Mods for which there is no file for this version and loader
    failed: dict[str, str] = field(default_factory=dict)  # Mods which could not be updated (e.g. timeout), with the reason. Existing files are kept.

    @property
    def has_problems(self) -> bool:
        return bool(self.not_found or self.failed)


@dataclass
class _ModToUpdate:
    url: str | None  # None if the mod does not exist in the mod list anymore
    entry: object  # The (download url, filename, last checked) entry of the instance. It can be broken.


@dataclass
class ModUpdateJob:
    """
    Everything that is needed to update the mods of an instance, copied from the data when the update starts.
    This way the thread that does the work never reads the data which the user may edit in the meantime.
    """
    instance_name: str
    mc_version: str  # Never "latest"
    loader: str
    mods: dict[str, _ModToUpdate]  # In the order in which they are updated (the mods which were not updated for the longest time first)
    mods_directory: Path
    checked_at: int


@dataclass
class ModUpdateOutcome:
    """ The result for one mod. It is computed in the worker and is applied to the data afterwards, see "apply_mod_update_outcome". """
    mod_name: str
    status: str  # 'skipped' (checked recently), 'updated', 'not_found' or 'failed'
    keep_filename: str = ''  # The file of this mod which must not be deleted
    download_url: str = ''
    filename: str = ''
    last_checked: int = 0
    checked_at: int = 0
    entry_was_broken: bool = False
    reason: str = ''  # Only for 'failed'


'''
Updating the mods (worker part: only network and files, never touches the data)
'''


def create_mod_update_job(data: Data, instance_name: str, mods_data: dict[str, tuple[str, str, int]], mc_version: str, loader: str) -> ModUpdateJob:
    if mc_version == 'latest':
        mc_version = LATEST_RELEASE

    # The mods which were not updated for the longest time come first. A mod which was never checked, which could not be updated
    # (timeout, offline...) or for which no file was found keeps its old check time (or none) and is therefore automatically
    # updated first the next time, while the mods which were just updated come last. Equal times keep the order of the instance.
    entries = sorted(list(mods_data.items()), key=lambda item: _parse_entry(item[1])[3])

    mods = {}
    for mod_name, entry in entries:
        mod_data = data.mods.get(mod_name)
        mods[mod_name] = _ModToUpdate(url=mod_data.url if mod_data is not None else None, entry=entry)

    return ModUpdateJob(
        instance_name=instance_name,
        mc_version=mc_version,
        loader=loader,
        mods=mods,
        mods_directory=PACKEDMC_MINECRAFT_DATA_DIRECTORY / 'mods' / instance_name,
        checked_at=round(time.time()),
    )


def _parse_entry(entry) -> tuple[bool, str, str, int]:
    """ Returns whether the entry is valid, followed by the download url, the filename and the time it was last checked. """
    try:
        old_download_url, old_filename, last_checked = entry
        if isinstance(entry, str) or not isinstance(old_download_url, str) or not isinstance(old_filename, str) or not isinstance(last_checked, (int, float)):
            raise ValueError
        return True, old_download_url, old_filename, last_checked
    except (TypeError, ValueError):  # If there is a mistake in the data, then use default values
        return False, '', '', 0


def _describe_request_error(error: requests.exceptions.RequestException) -> str:
    # A stalled download is reported by requests as a ConnectionError which wraps the timeout of urllib3
    stalled = isinstance(error, requests.exceptions.ConnectionError) and any(isinstance(argument, ReadTimeoutError) for argument in error.args)

    if isinstance(error, requests.exceptions.Timeout) or stalled:
        return f'timed out, no answer for {MOD_REQUEST_TIMEOUT} seconds'
    if isinstance(error, requests.exceptions.ConnectionError):
        return 'connection problem (are you offline?)'
    if isinstance(error, requests.exceptions.HTTPError) and error.response is not None:
        return f'the website answered with HTTP {error.response.status_code}'
    return f'network error ({type(error).__name__})'


def _download_file(url: str, destination: Path):
    """
    Download a file. It is first written to a temporary file, so that an aborted download never leaves a broken mod behind.
    Raises requests.exceptions.RequestException if the download fails and OSError if the file can not be written.
    """
    temporary_path = destination.with_name(f'{destination.name}.{uuid.uuid4().hex[:8]}.part')
    try:
        with requests.get(url, timeout=MOD_REQUEST_TIMEOUT, stream=True) as response:
            response.raise_for_status()
            with open(temporary_path, 'wb') as file:
                for chunk in response.iter_content(chunk_size=_DOWNLOAD_CHUNK_SIZE):
                    file.write(chunk)
        os.replace(temporary_path, destination)
    except BaseException:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _update_single_mod(job: ModUpdateJob, mod_name: str, mod: _ModToUpdate) -> ModUpdateOutcome:
    entry_is_valid, old_download_url, old_filename, last_checked = _parse_entry(mod.entry)

    # By default, the old file is kept and nothing changes
    outcome = ModUpdateOutcome(mod_name=mod_name, status='skipped', keep_filename=old_filename, last_checked=last_checked, entry_was_broken=not entry_is_valid)

    def failed(reason: str) -> ModUpdateOutcome:
        outcome.status = 'failed'
        outcome.reason = reason
        return outcome

    if mod.url is None:
        return failed('this mod is not in the mod list anymore')

    # Skip when it was last checked before our waiting interval
    if job.checked_at < last_checked + SKIP_WHEN_LAST_CHECKED_BEFORE:
        return outcome

    try:
        download_url, filename = get_download_url(mod.url, job.mc_version, job.loader, timeout=MOD_REQUEST_TIMEOUT)
    except (InvalidModBaseUrl, NoModFileAvailable):
        # Mod unavailable, thus no possible download URL. The old file is not needed anymore.
        outcome.status = 'not_found'
        outcome.keep_filename = ''
        return outcome
    except APICooldown:
        return failed('the rate limit of the mod website was reached')
    except TryAgainLater:
        return failed('the mod website is not ready yet')
    except ModNotExisting:
        return failed('the mod website could not find this mod or reported an error')
    except EmptyArguments as error:
        return failed(f'invalid arguments ({error})')
    except requests.exceptions.RequestException as error:
        return failed(_describe_request_error(error))

    # If you're offline, you get an empty URL in return.
    if not download_url:
        return failed('no connection to the mod website (are you offline?)')

    # If the download url has changed or the file does not exist, then download the file
    file_path = job.mods_directory / filename
    if old_download_url != download_url or not file_path.exists():
        try:
            _download_file(download_url, file_path)
        except requests.exceptions.RequestException as error:
            return failed(f'the download failed: {_describe_request_error(error)}')
        except OSError as error:
            return failed(f'the file could not be saved ({error})')

    outcome.status = 'updated'
    outcome.download_url = download_url
    outcome.filename = filename
    outcome.keep_filename = filename
    outcome.checked_at = job.checked_at
    return outcome


def run_mod_update(job: ModUpdateJob, result: ModUpdateResult | None = None, on_progress: Callable[[int, int, str], None] | None = None, on_outcome: Callable[[ModUpdateOutcome], None] | None = None) -> ModUpdateResult:
    """
    Go through all mods and try to get their download links (if they were not just checked recently).
    Then download the files if they don't already exist and remove the old mod versions.
    One mod that fails (timeout, offline...) never stops the others. Its existing file is kept, and it is retried on the next update.

    ``on_progress(finished_mods, total_mods, name_of_the_mod_being_updated)`` is called before every mod and once at the end.
    ``on_outcome(outcome)`` is called after every mod. This function itself never changes the data.
    """
    if result is None:
        result = ModUpdateResult()

    os.makedirs(job.mods_directory, exist_ok=True)  # Ensure it exists
    unneeded_files = set(os.listdir(job.mods_directory))
    total = len(job.mods)

    for index, (mod_name, mod) in enumerate(job.mods.items()):
        if on_progress is not None:
            on_progress(index, total, mod_name)

        try:
            outcome = _update_single_mod(job, mod_name, mod)
        except Exception as error:  # A bug must not stop the update of all other mods
            logger.exception(f'Unexpected error while updating the mod "{mod_name}".')
            outcome = ModUpdateOutcome(mod_name=mod_name, status='failed', keep_filename=_parse_entry(mod.entry)[2], reason=f'unexpected error ({type(error).__name__}: {error})')

        if outcome.status == 'not_found':
            logger.info(f'Found no file for the mod "{mod_name}" for {job.loader} {job.mc_version}.')
            result.not_found.append(mod_name)
        elif outcome.status == 'failed':
            logger.warning(f'Could not update the mod "{mod_name}" for "{job.instance_name}": {outcome.reason}. An existing file is kept and the update is tried again next time.')
            result.failed[mod_name] = outcome.reason

        # Remove the filename from the unneeded files, so it is not removed.
        unneeded_files.discard(outcome.keep_filename)

        if on_outcome is not None:
            on_outcome(outcome)

    if on_progress is not None:
        on_progress(total, total, '')

    # Delete all unneeded files (either from removed mods, or old versions of a mod)
    for unneeded_filename in unneeded_files:
        try:
            os.remove(job.mods_directory / unneeded_filename)
        except FileNotFoundError:
            # This happens when the update thread from startup interferes with the updater from pressing play.
            pass
        except OSError as error:
            logger.warning(f'Could not remove the unneeded file "{unneeded_filename}": {error}')

    return result


'''
Applying the results to the data (this must be done in the thread which owns the data)
'''


def apply_mod_update_outcome(data: Data, job: ModUpdateJob, outcome: ModUpdateOutcome):
    instance = data.instances.get(job.instance_name)
    if instance is None or outcome.mod_name not in instance.mods:
        return  # The instance was deleted or the mod was deselected while the update was running

    changed = False

    if outcome.entry_was_broken:
        instance.mods[outcome.mod_name] = ('', '', 0)
        changed = True

    if outcome.status == 'updated':
        instance.mods[outcome.mod_name] = (outcome.download_url, outcome.filename, outcome.checked_at)

        # If the version is not already in the supported versions, then add it.
        mod_data = data.mods.get(outcome.mod_name)
        if mod_data is not None and job.mc_version not in mod_data.supported_versions:
            mod_data.supported_versions.append(job.mc_version)
        changed = True

    elif outcome.status == 'not_found':
        instance.mods[outcome.mod_name] = ('', '', outcome.last_checked)
        changed = True

    if changed:
        data.save()


'''
The two ways to run an update
'''


def update_mod_files(main_window: MainWindow, instance_name: str, mods_data: dict[str, tuple[str, str, int]], mc_version: str, loader: str) -> ModUpdateResult:
    """
    Update the mods in the thread that calls this function and return what happened. It is used for the update in the background when starting PackedMC.
    To update with a progress window without blocking the window, use ModUpdateTask.
    """
    data: Data = main_window.data
    job = create_mod_update_job(data, instance_name, mods_data, mc_version, loader)

    logger.info(f'Start updating mods in the background for {instance_name}.')
    result = run_mod_update(job, on_outcome=lambda outcome: apply_mod_update_outcome(data, job, outcome))
    logger.info(f'Updated mods in the background for {instance_name}.')
    return result


class ModUpdateTask(QObject):
    """
    Updates the mods in a background thread and shows the progress in a separate, non-modal window, so the main window stays usable.

    The thread only downloads. All changes to the data are made in the thread of the window when the signals arrive. This is
    important, because the user can edit instances and mods while the download is running.
    ``on_finished(result)`` is called in the thread of the window when everything is done, also if something went wrong.
    The caller must keep a reference to the task until then.
    """
    progress = pyqtSignal(int, int, str)  # finished mods, total mods, mod which is processed now
    outcome_ready = pyqtSignal(object)  # ModUpdateOutcome
    finished = pyqtSignal(object)  # ModUpdateResult

    def __init__(self, main_window: MainWindow, instance_name: str, mods_data: dict[str, tuple[str, str, int]], mc_version: str, loader: str, on_finished: Callable[[ModUpdateResult], None] | None = None, show_progress_window=True):
        super().__init__(main_window)
        self._data: Data = main_window.data
        self._on_finished = on_finished
        self.job = create_mod_update_job(self._data, instance_name, mods_data, mc_version, loader)
        self.result = ModUpdateResult()

        self.progress_window: ProgressWindow | None = None
        if show_progress_window:
            self.progress_window = ProgressWindow(main_window, 'Downloading mods...', len(self.job.mods), 'Preparing...')

        self.progress.connect(self._show_progress)
        self.outcome_ready.connect(self._apply_outcome)
        self.finished.connect(self._finish)

    def start(self):
        if self.progress_window is not None:
            self.progress_window.show_centered_over_parent()
        threading.Thread(target=self._run, name=f'mod-update-{self.job.instance_name}', daemon=True).start()

    def _run(self):
        """ This runs in the background thread. The signals are delivered in the thread of the window. """
        try:
            run_mod_update(self.job, self.result, on_progress=self.progress.emit, on_outcome=self.outcome_ready.emit)
        except Exception:  # Nothing may stop the window from closing
            logger.exception('The mod update stopped unexpectedly.')
        finally:
            self.finished.emit(self.result)

    def _show_progress(self, finished_mods: int, total_mods: int, mod_name: str):
        if self.progress_window is not None:
            text = f'Downloading mod: \n{mod_name}' if mod_name else 'Finishing...'
            self.progress_window.set_progress(finished_mods, text)

    def _apply_outcome(self, outcome: ModUpdateOutcome):
        apply_mod_update_outcome(self._data, self.job, outcome)

    def _finish(self, result: ModUpdateResult):
        if self.progress_window is not None:
            self.progress_window.close()
            self.progress_window = None
        self.deleteLater()

        if self._on_finished is not None:
            self._on_finished(result)


def move_mods_from_packedmc_to_minecraft(instance_name: str, minecraft_directory: str):
    # Update the mods
    packedmc_mods_directory = PACKEDMC_MINECRAFT_DATA_DIRECTORY / 'mods' / instance_name

    # Get all the files in the mods directory which were not copied by PackedMC
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
