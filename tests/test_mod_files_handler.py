import json
import logging
from datetime import datetime
from types import SimpleNamespace

import pytest
import requests

from utils import mod_files_handler
from utils.data_file_helper import Data, SingleInstanceData, SingleModData
from utils.mod_files_handler import (
    ModUpdateOutcome, apply_mod_update_outcome, create_mod_update_job, move_mods_from_packedmc_to_minecraft, run_mod_update,
    update_mod_files, MOD_REQUEST_TIMEOUT, SKIP_WHEN_LAST_CHECKED_BEFORE,
)

from . import fake_file_paths as paths
from .helpers import directory_listing, freeze_datetime, read_data_file

NOW = 1_800_000_000
INSTANCE = 'My Fabric'
MODS_DIRECTORY = paths.PACKEDMC_MINECRAFT_DATA_DIRECTORY / 'mods' / INSTANCE

FABRIC_API_URL = 'https://cdn.modrinth.com/data/P7dR8mSH/versions/v1214/fabric-api-0.115.0-1.21.4.jar'
FABRIC_API_FILE = 'fabric-api-0.115.0-1.21.4.jar'
SODIUM_URL = 'https://cdn.modrinth.com/data/AANobbMI/versions/s1214/sodium-fabric-0.6.0-1.21.4.jar'
SODIUM_FILE = 'sodium-fabric-0.6.0-1.21.4.jar'
JEI_URL = 'https://edge.forgecdn.net/files/5953/701/jei-1.21.4-fabric-19.0.0.jar'
JEI_FILE = 'jei-1.21.4-fabric-19.0.0.jar'


@pytest.fixture(autouse=True)
def frozen_time(monkeypatch):
    """ ``mod_files_handler`` decides what to re-check using the current time. NOW is the time in all tests. """
    # noinspection unresolved-references
    monkeypatch.setattr(mod_files_handler, 'time', SimpleNamespace(time=lambda: NOW))
    return NOW


@pytest.fixture
def window():
    """ update_mod_files only needs ``main_window.data``, so no real window is necessary for these tests. """
    data = Data(paths.DATA_FILE_PATH)
    data.mods['Fabric API'] = SingleModData(url='https://modrinth.com/mod/fabric-api', loaders=['Fabric'])
    data.mods['Sodium'] = SingleModData(url='https://modrinth.com/mod/sodium', loaders=['Fabric'])
    data.mods['JEI'] = SingleModData(url='https://www.curseforge.com/minecraft/mc-mods/jei', loaders=['Fabric'])
    data.mods['Old Mod'] = SingleModData(url='https://modrinth.com/mod/old-mod', loaders=['Fabric'])
    data.mods['Strange'] = SingleModData(url='https://example.com/strange', loaders=['Fabric'])
    data.instances[INSTANCE] = SingleInstanceData(type='Fabric', version='1.21.4')
    data.save()
    return SimpleNamespace(data=data)


def select_mods(window, *names, state=('', '', 0)):
    """ Select mods for the instance, like ticking them in the UI. """
    for name in names:
        window.data.instances[INSTANCE].mods[name] = state
    return window.data.instances[INSTANCE].mods


def run_update(window, mc_version='1.21.4', loader='Fabric'):
    return update_mod_files(window, INSTANCE, window.data.instances[INSTANCE].mods, mc_version, loader)


# ================================================================================================== update_mod_files
def test_downloads_the_mod_files_into_the_packedmc_mods_directory(window, fake_internet):
    select_mods(window, 'Fabric API', 'Sodium', 'JEI')

    result = run_update(window)

    assert not result.has_problems
    assert directory_listing(MODS_DIRECTORY) == sorted([FABRIC_API_FILE, SODIUM_FILE, JEI_FILE])
    assert (MODS_DIRECTORY / FABRIC_API_FILE).read_bytes() == b'fabric-api 0.115.0 for 1.21.4'
    assert (MODS_DIRECTORY / JEI_FILE).read_bytes() == b'jei 19.0.0 for 1.21.4 fabric'
    assert sorted(fake_internet.urls()) == sorted([
        'https://api.modrinth.com/v2/project/fabric-api/version', FABRIC_API_URL,
        'https://api.modrinth.com/v2/project/sodium/version', SODIUM_URL,
        'https://api.cfwidget.com/minecraft/mc-mods/jei?version=1.21.4&loader=fabric', JEI_URL,
    ])


def test_download_info_is_stored_in_the_instance_data_and_saved(window):
    select_mods(window, 'Fabric API')

    run_update(window)

    assert window.data.instances[INSTANCE].mods['Fabric API'] == (FABRIC_API_URL, FABRIC_API_FILE, NOW)
    assert read_data_file()['instances'][INSTANCE]['mods']['Fabric API'] == [FABRIC_API_URL, FABRIC_API_FILE, NOW]


def test_the_game_version_is_added_to_the_supported_versions_of_the_mod(window):
    select_mods(window, 'Fabric API')
    window.data.mods['Fabric API'].supported_versions = ['1.20.1']

    run_update(window)

    assert window.data.mods['Fabric API'].supported_versions == ['1.20.1', '1.21.4']
    assert read_data_file()['mods']['Fabric API']['supported_versions'] == ['1.20.1', '1.21.4']


def test_latest_is_replaced_by_the_latest_release(window, fake_internet):
    select_mods(window, 'Fabric API')

    run_update(window, mc_version='latest')

    assert directory_listing(MODS_DIRECTORY) == [FABRIC_API_FILE]  # The 1.21.4 file was chosen
    assert window.data.mods['Fabric API'].supported_versions == ['1.21.4']


def test_recently_checked_mods_are_skipped_without_any_request(window, fake_internet):
    MODS_DIRECTORY.mkdir(parents=True)
    (MODS_DIRECTORY / FABRIC_API_FILE).write_bytes(b'already here')
    select_mods(window, 'Fabric API', state=(FABRIC_API_URL, FABRIC_API_FILE, NOW - 10))

    result = run_update(window)

    assert not result.has_problems
    fake_internet.assert_no_requests()
    assert (MODS_DIRECTORY / FABRIC_API_FILE).read_bytes() == b'already here'  # Not deleted as "unneeded" and not replaced


def test_mods_are_checked_again_after_the_waiting_time_but_an_existing_file_is_not_downloaded_again(window, fake_internet):
    MODS_DIRECTORY.mkdir(parents=True)
    (MODS_DIRECTORY / FABRIC_API_FILE).write_bytes(b'already here')
    select_mods(window, 'Fabric API', state=(FABRIC_API_URL, FABRIC_API_FILE, NOW - SKIP_WHEN_LAST_CHECKED_BEFORE - 1))

    run_update(window)

    fake_internet.assert_requested('https://api.modrinth.com/v2/project/fabric-api/version')
    fake_internet.assert_not_requested(FABRIC_API_URL)
    assert (MODS_DIRECTORY / FABRIC_API_FILE).read_bytes() == b'already here'
    assert window.data.instances[INSTANCE].mods['Fabric API'][2] == NOW  # The check time was refreshed


def test_a_changed_download_url_replaces_the_old_file(window, fake_internet):
    MODS_DIRECTORY.mkdir(parents=True)
    (MODS_DIRECTORY / 'fabric-api-0.100.0-1.21.4.jar').write_bytes(b'old version')
    select_mods(window, 'Fabric API', state=('https://cdn.modrinth.com/old.jar', 'fabric-api-0.100.0-1.21.4.jar', 0))

    run_update(window)

    assert directory_listing(MODS_DIRECTORY) == [FABRIC_API_FILE]
    fake_internet.assert_requested(FABRIC_API_URL)


def test_a_missing_file_is_downloaded_again_even_if_the_url_is_unchanged(window, fake_internet):
    select_mods(window, 'Fabric API', state=(FABRIC_API_URL, FABRIC_API_FILE, 0))

    run_update(window)

    assert (MODS_DIRECTORY / FABRIC_API_FILE).exists()
    fake_internet.assert_requested(FABRIC_API_URL)


def test_files_of_deselected_mods_are_deleted(window):
    MODS_DIRECTORY.mkdir(parents=True)
    (MODS_DIRECTORY / 'removed-mod.jar').write_bytes(b'x')
    select_mods(window, 'Fabric API')

    run_update(window)

    assert directory_listing(MODS_DIRECTORY) == [FABRIC_API_FILE]


def test_mods_without_a_file_for_this_version_are_reported(window, fake_internet):
    select_mods(window, 'Fabric API', 'Old Mod')

    result = run_update(window)

    assert result.not_found == ['Old Mod'] and result.failed == {}
    assert directory_listing(MODS_DIRECTORY) == [FABRIC_API_FILE]
    assert window.data.instances[INSTANCE].mods['Old Mod'] == ('', '', 0)  # Keeps the old "last checked" so it is retried next time
    fake_internet.assert_not_requested('https://cdn.modrinth.com/data/OLD/versions/o1/old-mod-1.0-1.19.4.jar')


def test_mods_from_unsupported_websites_are_reported_without_requests(window, fake_internet):
    select_mods(window, 'Strange')

    assert run_update(window).not_found == ['Strange']
    fake_internet.assert_no_requests()


def test_api_cooldown_is_reported_as_failed_and_retried_later(window, fake_internet):
    fake_internet.add_route('https://api.modrinth.com/v2/project/fabric-api/version', file='modrinth_versions_fabric-api.json', headers={'X-Ratelimit-Remaining': '0'})
    select_mods(window, 'Fabric API')

    result = run_update(window)

    assert result.not_found == [] and list(result.failed) == ['Fabric API'] and 'rate limit' in result.failed['Fabric API']
    assert directory_listing(MODS_DIRECTORY) == []
    assert window.data.instances[INSTANCE].mods['Fabric API'] == ('', '', 0)  # Unchanged, so the next update tries again


def test_curseforge_try_again_later_is_reported_as_failed(window, fake_internet):
    fake_internet.add_route('https://api.cfwidget.com/minecraft/mc-mods/jei?version=1.21.4&loader=fabric', status=202, json={})
    select_mods(window, 'JEI')

    result = run_update(window)

    assert result.not_found == [] and list(result.failed) == ['JEI']
    assert directory_listing(MODS_DIRECTORY) == []


def test_broken_mod_entries_are_repaired(window):
    window.data.instances[INSTANCE].mods['Fabric API'] = 'garbage'

    run_update(window)

    assert window.data.instances[INSTANCE].mods['Fabric API'] == (FABRIC_API_URL, FABRIC_API_FILE, NOW)


def test_updating_while_offline_for_the_first_time_does_not_crash(window, fake_internet):
    fake_internet.go_offline()
    select_mods(window, 'Fabric API')

    result = run_update(window)

    assert result.not_found == [] and list(result.failed) == ['Fabric API'] and 'offline' in result.failed['Fabric API']
    assert directory_listing(MODS_DIRECTORY) == []
    assert window.data.instances[INSTANCE].mods['Fabric API'] == ('', '', 0)  # Not marked as checked, so it is tried again soon


def test_updating_while_offline_keeps_previously_downloaded_mods(window, fake_internet):
    MODS_DIRECTORY.mkdir(parents=True)
    (MODS_DIRECTORY / FABRIC_API_FILE).write_bytes(b'downloaded yesterday')
    select_mods(window, 'Fabric API', state=(FABRIC_API_URL, FABRIC_API_FILE, NOW - 86400))
    fake_internet.go_offline()

    result = run_update(window)

    assert list(result.failed) == ['Fabric API']
    assert (MODS_DIRECTORY / FABRIC_API_FILE).read_bytes() == b'downloaded yesterday'
    assert window.data.instances[INSTANCE].mods['Fabric API'][0] == FABRIC_API_URL


# ============================================================================================ timeouts and failing mods
LOOKUP_URL = 'https://api.modrinth.com/v2/project/fabric-api/version'


def test_every_request_of_a_mod_update_has_a_timeout(window, fake_internet):
    select_mods(window, 'Fabric API', 'Sodium', 'JEI')

    run_update(window)

    assert MOD_REQUEST_TIMEOUT == 10
    assert len(fake_internet.requests) == 6  # 3 lookups and 3 downloads
    assert [request.timeout for request in fake_internet.requests] == [MOD_REQUEST_TIMEOUT] * 6


@pytest.mark.parametrize('error', [requests.exceptions.ReadTimeout(), requests.exceptions.ConnectTimeout()], ids=['read_timeout', 'connect_timeout'])
def test_a_timeout_fails_only_that_mod_and_is_reported(window, fake_internet, caplog, error):
    fake_internet.add_route(LOOKUP_URL, raises=error)
    select_mods(window, 'Fabric API', 'Sodium')

    with caplog.at_level(logging.WARNING):
        result = run_update(window)

    assert list(result.failed) == ['Fabric API'] and 'timed out' in result.failed['Fabric API'] and result.not_found == []
    assert directory_listing(MODS_DIRECTORY) == [SODIUM_FILE]  # The other mod was still updated
    warnings = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1 and 'Fabric API' in warnings[0] and 'timed out' in warnings[0]


def test_a_failed_mod_is_not_marked_as_checked_so_the_next_update_retries_it(window, fake_internet):
    fake_internet.add_route(LOOKUP_URL, raises=requests.exceptions.ReadTimeout())
    select_mods(window, 'Fabric API')
    run_update(window)
    assert window.data.instances[INSTANCE].mods['Fabric API'] == ('', '', 0)

    fake_internet.add_route(LOOKUP_URL, file='modrinth_versions_fabric-api.json')  # The website works again
    result = run_update(window)

    assert not result.has_problems and directory_listing(MODS_DIRECTORY) == [FABRIC_API_FILE]


def test_a_download_which_stalls_leaves_no_broken_file_and_keeps_the_old_one(window, fake_internet, caplog):
    MODS_DIRECTORY.mkdir(parents=True)
    (MODS_DIRECTORY / 'fabric-api-old.jar').write_bytes(b'old version')
    select_mods(window, 'Fabric API', state=('https://cdn.modrinth.com/old.jar', 'fabric-api-old.jar', 0))
    fake_internet.add_route(FABRIC_API_URL, stall_after=b'partial data')

    with caplog.at_level(logging.WARNING):
        result = run_update(window)

    assert list(result.failed) == ['Fabric API'] and 'timed out' in result.failed['Fabric API']
    assert directory_listing(MODS_DIRECTORY) == ['fabric-api-old.jar']  # No new file and no leftover temporary file
    assert window.data.instances[INSTANCE].mods['Fabric API'] == ('https://cdn.modrinth.com/old.jar', 'fabric-api-old.jar', 0)
    assert 'Fabric API' in caplog.text


def test_an_error_page_is_not_saved_as_a_mod(window, fake_internet):
    fake_internet.add_route(FABRIC_API_URL, status=404, text='<html>Not found</html>')
    select_mods(window, 'Fabric API')

    result = run_update(window)

    assert 'HTTP 404' in result.failed['Fabric API']
    assert directory_listing(MODS_DIRECTORY) == []


def test_a_mod_which_the_website_does_not_know_is_a_failure_and_not_a_missing_version(window):
    window.data.mods['Gone'] = SingleModData(url='https://modrinth.com/mod/does-not-exist', loaders=['Fabric'])
    select_mods(window, 'Gone', 'Sodium')

    result = run_update(window)

    assert list(result.failed) == ['Gone'] and result.not_found == []
    assert directory_listing(MODS_DIRECTORY) == [SODIUM_FILE]


def test_missing_versions_and_failures_are_reported_together(window, fake_internet):
    fake_internet.add_route('https://api.modrinth.com/v2/project/sodium/version', raises=requests.exceptions.ReadTimeout())
    select_mods(window, 'Fabric API', 'Sodium', 'Old Mod')

    result = run_update(window)

    assert result.not_found == ['Old Mod'] and list(result.failed) == ['Sodium'] and result.has_problems
    assert directory_listing(MODS_DIRECTORY) == [FABRIC_API_FILE]


def test_an_unexpected_error_in_one_mod_does_not_stop_the_others(window, monkeypatch, caplog):
    original = mod_files_handler.get_download_url

    def broken_for_sodium(mod_url, *arguments, **keyword_arguments):
        if 'sodium' in mod_url:
            raise RuntimeError('something unexpected')
        return original(mod_url, *arguments, **keyword_arguments)

    # noinspection unresolved-references
    monkeypatch.setattr(mod_files_handler, 'get_download_url', broken_for_sodium)
    select_mods(window, 'Sodium', 'Fabric API')

    result = run_update(window)

    assert list(result.failed) == ['Sodium'] and 'something unexpected' in result.failed['Sodium']
    assert directory_listing(MODS_DIRECTORY) == [FABRIC_API_FILE]


def test_the_worker_part_never_changes_the_data(window):
    """ The download runs in a background thread while the user edits the data. So the thread must only return what to change. """
    select_mods(window, 'Fabric API')
    job = create_mod_update_job(window.data, INSTANCE, window.data.instances[INSTANCE].mods, '1.21.4', 'Fabric')
    outcomes = []

    run_mod_update(job, on_outcome=outcomes.append)

    assert directory_listing(MODS_DIRECTORY) == [FABRIC_API_FILE]  # The file was downloaded...
    assert window.data.instances[INSTANCE].mods['Fabric API'] == ('', '', 0)  # ...but the data is unchanged
    assert [(outcome.mod_name, outcome.status, outcome.filename) for outcome in outcomes] == [('Fabric API', 'updated', FABRIC_API_FILE)]


def test_progress_is_reported_before_every_mod_and_at_the_end(window):
    select_mods(window, 'Fabric API', 'Sodium')
    job = create_mod_update_job(window.data, INSTANCE, window.data.instances[INSTANCE].mods, '1.21.4', 'Fabric')
    progress = []

    run_mod_update(job, on_progress=lambda *arguments: progress.append(arguments))

    assert progress == [(0, 2, 'Fabric API'), (1, 2, 'Sodium'), (2, 2, '')]


def test_results_for_mods_which_were_deselected_in_the_meantime_are_ignored(window):
    select_mods(window, 'Fabric API', 'Sodium')
    job = create_mod_update_job(window.data, INSTANCE, window.data.instances[INSTANCE].mods, '1.21.4', 'Fabric')
    del window.data.instances[INSTANCE].mods['Sodium']  # The user deselects it while the download is running

    apply_mod_update_outcome(window.data, job, ModUpdateOutcome('Sodium', 'updated', download_url=SODIUM_URL, filename=SODIUM_FILE, keep_filename=SODIUM_FILE, checked_at=NOW))

    assert 'Sodium' not in window.data.instances[INSTANCE].mods


def test_results_for_a_deleted_instance_are_ignored(window):
    select_mods(window, 'Fabric API')
    job = create_mod_update_job(window.data, INSTANCE, window.data.instances[INSTANCE].mods, '1.21.4', 'Fabric')
    del window.data.instances[INSTANCE]

    apply_mod_update_outcome(window.data, job, ModUpdateOutcome('Fabric API', 'updated', download_url=FABRIC_API_URL, filename=FABRIC_API_FILE, checked_at=NOW))  # Must not raise


def test_leftover_temporary_files_are_cleaned_up(window):
    MODS_DIRECTORY.mkdir(parents=True)
    (MODS_DIRECTORY / f'{FABRIC_API_FILE}.1a2b3c4d.part').write_bytes(b'from an aborted download')
    select_mods(window, 'Fabric API')

    run_update(window)

    assert directory_listing(MODS_DIRECTORY) == [FABRIC_API_FILE]


def test_a_file_which_can_not_be_removed_is_only_a_warning(window, monkeypatch, caplog):
    MODS_DIRECTORY.mkdir(parents=True)
    (MODS_DIRECTORY / 'stray.jar').write_bytes(b'x')

    def locked(path, *arguments, **keyword_arguments):
        raise PermissionError('in use by another program')

    monkeypatch.setattr(mod_files_handler.os, 'remove', locked)
    with caplog.at_level(logging.WARNING):
        run_update(window)  # Must not raise

    assert 'stray.jar' in caplog.text


# ================================================================================================= update order
def lookups(fake_internet) -> list[str]:
    """ The requests which asked a mod website for the download url of a mod (not the downloads themselves), in order. """
    return [url.removeprefix('https://') for url in fake_internet.urls() if url.split('?')[0].endswith('/version') or 'api.cfwidget.com' in url]


def move_time_forward(monkeypatch, seconds: int):
    monkeypatch.setattr(mod_files_handler, 'time', SimpleNamespace(time=lambda: NOW + seconds))


def test_the_mods_which_were_not_updated_for_the_longest_time_come_first(window, fake_internet):
    window.data.instances[INSTANCE].mods['Fabric API'] = (FABRIC_API_URL, FABRIC_API_FILE, NOW - 5000)  # Updated recently
    window.data.instances[INSTANCE].mods['JEI'] = ('', '', NOW - 9000)  # Updated long ago
    window.data.instances[INSTANCE].mods['Sodium'] = ('', '', 0)  # Never updated
    job = create_mod_update_job(window.data, INSTANCE, window.data.instances[INSTANCE].mods, '1.21.4', 'Fabric')

    assert list(job.mods) == ['Sodium', 'JEI', 'Fabric API']

    run_update(window)
    assert lookups(fake_internet) == ['api.modrinth.com/v2/project/sodium/version', 'api.cfwidget.com/minecraft/mc-mods/jei?version=1.21.4&loader=fabric', 'api.modrinth.com/v2/project/fabric-api/version']


def test_mods_with_the_same_update_time_keep_the_order_of_the_instance(window):
    select_mods(window, 'JEI', 'Fabric API', 'Sodium')
    job = create_mod_update_job(window.data, INSTANCE, window.data.instances[INSTANCE].mods, '1.21.4', 'Fabric')
    assert list(job.mods) == ['JEI', 'Fabric API', 'Sodium']


def test_mods_with_broken_entries_come_first(window):
    select_mods(window, 'Sodium', state=('', '', NOW - 100))
    window.data.instances[INSTANCE].mods['Fabric API'] = 'garbage'
    job = create_mod_update_job(window.data, INSTANCE, window.data.instances[INSTANCE].mods, '1.21.4', 'Fabric')
    assert list(job.mods) == ['Fabric API', 'Sodium']


def test_the_progress_follows_the_update_order(window):
    window.data.instances[INSTANCE].mods['Fabric API'] = (FABRIC_API_URL, FABRIC_API_FILE, NOW - 5000)
    window.data.instances[INSTANCE].mods['Sodium'] = ('', '', 0)
    job = create_mod_update_job(window.data, INSTANCE, window.data.instances[INSTANCE].mods, '1.21.4', 'Fabric')
    progress = []

    run_mod_update(job, on_progress=lambda *arguments: progress.append(arguments))

    assert progress == [(0, 2, 'Sodium'), (1, 2, 'Fabric API'), (2, 2, '')]


def test_the_order_of_the_mods_in_the_instance_itself_is_not_changed(window):
    select_mods(window, 'Fabric API', 'Sodium')
    window.data.instances[INSTANCE].mods['Fabric API'] = (FABRIC_API_URL, FABRIC_API_FILE, NOW - 5000)

    run_update(window)

    assert list(window.data.instances[INSTANCE].mods) == ['Fabric API', 'Sodium']


def test_a_mod_which_failed_is_updated_first_the_next_time(window, fake_internet, monkeypatch):
    select_mods(window, 'Sodium', 'Fabric API')  # The mod which fails is listed last
    fake_internet.add_route(LOOKUP_URL, raises=requests.exceptions.ReadTimeout())
    first_result = run_update(window)
    assert list(first_result.failed) == ['Fabric API']
    assert window.data.instances[INSTANCE].mods['Sodium'][2] == NOW  # Updated
    assert window.data.instances[INSTANCE].mods['Fabric API'][2] == 0  # Not updated, so it still has no update time

    fake_internet.add_route(LOOKUP_URL, file='modrinth_versions_fabric-api.json')  # The website works again
    fake_internet.clear_history()
    move_time_forward(monkeypatch, SKIP_WHEN_LAST_CHECKED_BEFORE + 1)  # Sodium is due for a check again, too
    second_result = run_update(window)

    assert not second_result.has_problems
    assert lookups(fake_internet) == ['api.modrinth.com/v2/project/fabric-api/version', 'api.modrinth.com/v2/project/sodium/version']  # Not in the order of the instance


def test_a_mod_for_which_no_file_was_found_is_checked_first_the_next_time(window, fake_internet, monkeypatch):
    select_mods(window, 'Sodium', 'Old Mod')
    first_result = run_update(window)
    assert first_result.not_found == ['Old Mod']
    assert window.data.instances[INSTANCE].mods['Old Mod'] == ('', '', 0)  # Keeps its old update time

    fake_internet.clear_history()
    move_time_forward(monkeypatch, SKIP_WHEN_LAST_CHECKED_BEFORE + 1)
    run_update(window)

    assert lookups(fake_internet) == ['api.modrinth.com/v2/project/old-mod/version', 'api.modrinth.com/v2/project/sodium/version']


def test_an_interrupted_update_continues_with_the_mods_which_were_not_reached(window):
    select_mods(window, 'Fabric API', 'Sodium', 'JEI')

    class Interrupted(Exception):
        pass

    def stop_after_the_first_mod(outcome):
        apply_mod_update_outcome(window.data, job, outcome)
        raise Interrupted  # For example PackedMC is closed in the middle of the update

    job = create_mod_update_job(window.data, INSTANCE, window.data.instances[INSTANCE].mods, '1.21.4', 'Fabric')
    with pytest.raises(Interrupted):
        run_mod_update(job, on_outcome=stop_after_the_first_mod)
    assert window.data.instances[INSTANCE].mods['Fabric API'][2] == NOW  # Only this one was updated

    next_job = create_mod_update_job(window.data, INSTANCE, window.data.instances[INSTANCE].mods, '1.21.4', 'Fabric')

    assert list(next_job.mods) == ['Sodium', 'JEI', 'Fabric API']


# ================================================================================ move_mods_from_packedmc_to_minecraft
@pytest.fixture
def minecraft_mods():
    return paths.MINECRAFT_DIRECTORY / 'mods'


@pytest.fixture
def packedmc_mods():
    MODS_DIRECTORY.mkdir(parents=True)
    return MODS_DIRECTORY


def move():
    move_mods_from_packedmc_to_minecraft(INSTANCE, str(paths.MINECRAFT_DIRECTORY))


def test_mods_are_copied_into_the_minecraft_mods_directory(packedmc_mods, minecraft_mods):
    (packedmc_mods / 'a.jar').write_bytes(b'AAA')
    (packedmc_mods / 'b.jar').write_bytes(b'BBB')

    move()

    assert directory_listing(minecraft_mods) == ['a.jar', 'b.jar', 'packedmc.json']
    assert (minecraft_mods / 'a.jar').read_bytes() == b'AAA'
    assert sorted(json.loads((minecraft_mods / 'packedmc.json').read_text())) == ['a.jar', 'b.jar']
    assert directory_listing(packedmc_mods) == ['a.jar', 'b.jar']  # The PackedMC copies stay


def test_the_minecraft_mods_directory_is_created_if_necessary(packedmc_mods, minecraft_mods):
    assert not minecraft_mods.exists()
    move()
    assert minecraft_mods.is_dir()
    assert json.loads((minecraft_mods / 'packedmc.json').read_text()) == []


def test_foreign_mod_files_are_moved_to_a_backup_directory(packedmc_mods, minecraft_mods, monkeypatch):
    freeze_datetime(monkeypatch, mod_files_handler, datetime(2026, 2, 3, 4, 5, 6))
    (packedmc_mods / 'a.jar').write_bytes(b'AAA')
    minecraft_mods.mkdir(parents=True)
    (minecraft_mods / 'my-own-mod.jar').write_bytes(b'mine')

    move()

    backup = minecraft_mods / 'packedmc_backup_2026-02-03_04-05-06'
    assert directory_listing(minecraft_mods) == ['a.jar', 'packedmc.json', 'packedmc_backup_2026-02-03_04-05-06']
    assert (backup / 'my-own-mod.jar').read_bytes() == b'mine'


def test_a_second_move_replaces_old_packedmc_files_and_makes_no_backup(packedmc_mods, minecraft_mods):
    (packedmc_mods / 'a.jar').write_bytes(b'AAA')
    (packedmc_mods / 'b.jar').write_bytes(b'BBB')
    move()

    (packedmc_mods / 'b.jar').unlink()
    (packedmc_mods / 'c.jar').write_bytes(b'CCC')
    (packedmc_mods / 'a.jar').write_bytes(b'AAA v2')
    move()

    assert directory_listing(minecraft_mods) == ['a.jar', 'c.jar', 'packedmc.json']  # b.jar is gone, no backup directory
    assert (minecraft_mods / 'a.jar').read_bytes() == b'AAA v2'
    assert sorted(json.loads((minecraft_mods / 'packedmc.json').read_text())) == ['a.jar', 'c.jar']


def test_directories_inside_the_minecraft_mods_directory_are_left_alone(packedmc_mods, minecraft_mods):
    (minecraft_mods / '1.21.4').mkdir(parents=True)
    (minecraft_mods / '1.21.4' / 'sub.jar').write_bytes(b'x')
    (packedmc_mods / 'a.jar').write_bytes(b'AAA')

    move()

    assert directory_listing(minecraft_mods) == ['1.21.4', 'a.jar', 'packedmc.json']
    assert (minecraft_mods / '1.21.4' / 'sub.jar').exists()


def test_moving_twice_in_a_row_is_harmless(packedmc_mods, minecraft_mods):
    (packedmc_mods / 'a.jar').write_bytes(b'AAA')
    move()
    move()
    assert directory_listing(minecraft_mods) == ['a.jar', 'packedmc.json']
