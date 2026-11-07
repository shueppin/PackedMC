import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from utils import mod_files_handler
from utils.data_file_helper import Data, SingleInstanceData, SingleModData
from utils.mod_files_handler import update_mod_files, move_mods_from_packedmc_to_minecraft, SKIP_WHEN_LAST_CHECKED_BEFORE

from . import testing_file_paths as paths
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
    return update_mod_files(window, INSTANCE, window.data.instances[INSTANCE].mods, mc_version, loader, output=False)


# ================================================================================================== update_mod_files
def test_downloads_the_mod_files_into_the_packedmc_mods_directory(window, fake_internet):
    select_mods(window, 'Fabric API', 'Sodium', 'JEI')

    not_found = run_update(window)

    assert not_found == []
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

    not_found = run_update(window)

    assert not_found == []
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

    not_found = run_update(window)

    assert not_found == ['Old Mod']
    assert directory_listing(MODS_DIRECTORY) == [FABRIC_API_FILE]
    assert window.data.instances[INSTANCE].mods['Old Mod'] == ('', '', 0)  # Keeps the old "last checked" so it is retried next time
    fake_internet.assert_not_requested('https://cdn.modrinth.com/data/OLD/versions/o1/old-mod-1.0-1.19.4.jar')


def test_mods_from_unsupported_websites_are_reported_without_requests(window, fake_internet):
    select_mods(window, 'Strange')

    assert run_update(window) == ['Strange']
    fake_internet.assert_no_requests()


def test_api_cooldown_is_ignored_and_retried_later(window, fake_internet):
    fake_internet.add_route('https://api.modrinth.com/v2/project/fabric-api/version', file='modrinth_versions_fabric-api.json', headers={'X-Ratelimit-Remaining': '0'})
    select_mods(window, 'Fabric API')

    assert run_update(window) == []
    assert directory_listing(MODS_DIRECTORY) == []
    assert window.data.instances[INSTANCE].mods['Fabric API'] == ('', '', 0)


def test_curseforge_try_again_later_is_ignored(window, fake_internet):
    fake_internet.add_route('https://api.cfwidget.com/minecraft/mc-mods/jei?version=1.21.4&loader=fabric', status=202, json={})
    select_mods(window, 'JEI')

    assert run_update(window) == []
    assert directory_listing(MODS_DIRECTORY) == []


def test_broken_mod_entries_are_repaired(window):
    window.data.instances[INSTANCE].mods['Fabric API'] = 'garbage'

    run_update(window)

    assert window.data.instances[INSTANCE].mods['Fabric API'] == (FABRIC_API_URL, FABRIC_API_FILE, NOW)


def test_updating_while_offline_for_the_first_time_does_not_crash(window, fake_internet):
    fake_internet.go_offline()
    select_mods(window, 'Fabric API')

    assert run_update(window) == []
    assert directory_listing(MODS_DIRECTORY) == []


@pytest.mark.xfail(reason='BUG: When offline, get_download_url returns ("", ""). If the mod was downloaded before, the empty URL differs from the stored URL, '
                          'so requests.get("") is called and raises MissingSchema. Playing offline crashes.')
def test_updating_while_offline_keeps_previously_downloaded_mods(window, fake_internet):
    MODS_DIRECTORY.mkdir(parents=True)
    (MODS_DIRECTORY / FABRIC_API_FILE).write_bytes(b'downloaded yesterday')
    select_mods(window, 'Fabric API', state=(FABRIC_API_URL, FABRIC_API_FILE, NOW - 86400))
    fake_internet.go_offline()

    run_update(window)

    assert (MODS_DIRECTORY / FABRIC_API_FILE).read_bytes() == b'downloaded yesterday'
    assert window.data.instances[INSTANCE].mods['Fabric API'][0] == FABRIC_API_URL


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
