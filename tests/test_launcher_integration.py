import logging
from datetime import datetime

import pytest

from minecraft_api import minecraft_launcher_integration as launcher
from minecraft_api.minecraft_launcher_integration import (
    DEFAULT_OTHER_JVM_ARGS, MINECRAFT_LAUNCHER_APP, MINECRAFT_LAUNCHER_PACKEDMC_PROFILE_ID,
    get_last_played_minecraft_launcher_profile, load_options_file_from_packedmc, save_options_file_of_last_used_instance,
    start_official_launcher, write_instance_data_to_profiles_file,
)
from utils.data_file_helper import SingleInstanceData, AdvancedArgumentsData

from . import testing_file_paths as paths
from .helpers import directory_listing, freeze_datetime, make_launcher_profile, read_launcher_profiles, write_launcher_profiles, write_text

OPTIONS_DIRECTORY = paths.PACKEDMC_OPTIONS_FILES_DIRECTORY
MINECRAFT_OPTIONS = paths.MINECRAFT_DIRECTORY / 'options.txt'
DEFAULT_NAME = 'Latest Release'


def instance(**kwargs) -> SingleInstanceData:
    kwargs.setdefault('minecraft_directory', str(paths.MINECRAFT_DIRECTORY))
    return SingleInstanceData(**kwargs)


# ========================================================================================== start_official_launcher
def test_start_official_launcher_opens_the_store_app(subprocesses):
    start_official_launcher()

    assert len(subprocesses.calls) == 1
    call = subprocesses.calls[0]
    assert call.function == 'run' and call.kwargs.get('shell') is True
    assert call.command == rf'explorer.exe shell:AppsFolder\{MINECRAFT_LAUNCHER_APP}'


def test_start_official_launcher_survives_a_missing_launcher(subprocesses, caplog):
    subprocesses.run_exception = FileNotFoundError()
    with caplog.at_level(logging.ERROR):
        start_official_launcher()
    assert 'Could not find the Minecraft Launcher' in caplog.text


# ============================================================================== get_last_played_minecraft_launcher_profile
def test_last_played_profile_without_profiles_file():
    assert get_last_played_minecraft_launcher_profile() == ('', {})


@pytest.mark.xfail(reason='ROBUSTNESS: A launcher_profiles.json with an empty "profiles" object raises KeyError(""), which breaks starting PackedMC and playing.')
def test_last_played_profile_with_empty_profiles_object():
    write_launcher_profiles({})
    assert get_last_played_minecraft_launcher_profile() == ('', {})


def test_last_played_profile_is_the_one_with_the_newest_last_used_time():
    write_launcher_profiles({
        'old': make_launcher_profile(name='Old', last_used='2025-01-01T10:00:00.000Z'),
        'newest': make_launcher_profile(name='Newest', last_used='2026-03-01T10:00:00.000Z'),
        'middle': make_launcher_profile(name='Middle', last_used='2025-12-01T10:00:00.000Z'),
    })

    profile_id, profile = get_last_played_minecraft_launcher_profile()

    assert profile_id == 'newest' and profile['name'] == 'Newest'


# ============================================================================ save_options_file_of_last_used_instance
def packedmc_was_last_played(**kwargs):
    write_launcher_profiles({
        MINECRAFT_LAUNCHER_PACKEDMC_PROFILE_ID: make_launcher_profile(name='PackedMC - Survival', last_used='2026-03-01T10:00:00.000Z'),
        'other': make_launcher_profile(name='Other', last_used='2026-01-01T10:00:00.000Z'),
    })


def test_options_of_the_last_played_instance_are_stored_under_its_name():
    packedmc_was_last_played()
    write_text(MINECRAFT_OPTIONS, 'fov:90.0')

    save_options_file_of_last_used_instance('Survival', instance(), DEFAULT_NAME)

    assert directory_listing(OPTIONS_DIRECTORY) == ['Survival.txt']
    assert (OPTIONS_DIRECTORY / 'Survival.txt').read_text() == 'fov:90.0'


def test_options_are_stored_as_default_options_if_the_instance_uses_them():
    packedmc_was_last_played()
    write_text(MINECRAFT_OPTIONS, 'fov:70.0')

    save_options_file_of_last_used_instance('Survival', instance(use_default_options_file=True), DEFAULT_NAME)

    assert directory_listing(OPTIONS_DIRECTORY) == [f'{DEFAULT_NAME}.txt']
    assert (OPTIONS_DIRECTORY / f'{DEFAULT_NAME}.txt').read_text() == 'fov:70.0'


def test_options_are_read_from_the_minecraft_directory_of_the_instance(tmp_path):
    packedmc_was_last_played()
    custom_directory = paths.FAKE_HOME_DIRECTORY / 'custom_minecraft'
    write_text(custom_directory / 'options.txt', 'from custom directory')
    write_text(MINECRAFT_OPTIONS, 'from default directory')

    save_options_file_of_last_used_instance('Survival', instance(minecraft_directory=str(custom_directory)), DEFAULT_NAME)

    assert (OPTIONS_DIRECTORY / 'Survival.txt').read_text() == 'from custom directory'


def test_missing_options_file_is_only_a_warning(caplog):
    packedmc_was_last_played()

    with caplog.at_level(logging.WARNING):
        save_options_file_of_last_used_instance('Survival', instance(), DEFAULT_NAME)

    assert 'Options file not found' in caplog.text
    assert directory_listing(OPTIONS_DIRECTORY) == []


def test_nothing_is_stored_when_another_profile_was_played_last(caplog):
    write_launcher_profiles({'other': make_launcher_profile(name='Other')})  # No gameDir
    write_text(MINECRAFT_OPTIONS, 'fov:90.0')

    with caplog.at_level(logging.WARNING):
        save_options_file_of_last_used_instance('Survival', instance(), DEFAULT_NAME)

    assert directory_listing(OPTIONS_DIRECTORY) == []
    assert 'PackedMC was not the last played profile' in caplog.text


def test_without_a_profiles_file_nothing_is_stored():
    write_text(MINECRAFT_OPTIONS, 'fov:90.0')
    save_options_file_of_last_used_instance('Survival', instance(), DEFAULT_NAME)
    assert directory_listing(OPTIONS_DIRECTORY) == []


@pytest.mark.xfail(reason='BUG: When another profile was played last, the backup should copy "<gameDir>/options.txt" of that profile, but the code joins the profile ID '
                          '("other") instead of the game directory, so the backup is never made.')
def test_options_of_another_last_played_profile_are_backed_up():
    game_directory = paths.FAKE_HOME_DIRECTORY / 'other_game_dir'
    write_launcher_profiles({'other': make_launcher_profile(name='Other', game_dir=game_directory)})
    write_text(game_directory / 'options.txt', 'fov:50.0')

    save_options_file_of_last_used_instance('Survival', instance(), DEFAULT_NAME)

    assert (paths.PACKEDMC_MINECRAFT_DATA_DIRECTORY / 'backup_options.txt').read_text() == 'fov:50.0'


# ================================================================================================ load_options_file_from_packedmc
def test_options_of_the_instance_are_copied_to_minecraft():
    write_text(OPTIONS_DIRECTORY / 'Survival.txt', 'fov:100.0')
    write_text(MINECRAFT_OPTIONS, 'replaced')

    load_options_file_from_packedmc('Survival', instance(), DEFAULT_NAME)

    assert MINECRAFT_OPTIONS.read_text() == 'fov:100.0'


def test_options_are_created_in_minecraft_if_they_did_not_exist():
    write_text(OPTIONS_DIRECTORY / 'Survival.txt', 'fov:100.0')
    assert not MINECRAFT_OPTIONS.exists()

    load_options_file_from_packedmc('Survival', instance(), DEFAULT_NAME)

    assert MINECRAFT_OPTIONS.read_text() == 'fov:100.0'


def test_default_options_are_used_if_the_instance_has_none():
    write_text(OPTIONS_DIRECTORY / f'{DEFAULT_NAME}.txt', 'default options')

    load_options_file_from_packedmc('Brand New', instance(), DEFAULT_NAME)

    assert MINECRAFT_OPTIONS.read_text() == 'default options'


def test_default_options_are_used_if_the_instance_asks_for_them():
    write_text(OPTIONS_DIRECTORY / 'Survival.txt', 'own options')
    write_text(OPTIONS_DIRECTORY / f'{DEFAULT_NAME}.txt', 'default options')

    load_options_file_from_packedmc('Survival', instance(use_default_options_file=True), DEFAULT_NAME)

    assert MINECRAFT_OPTIONS.read_text() == 'default options'


def test_nothing_is_copied_if_no_options_exist():
    write_text(MINECRAFT_OPTIONS, 'untouched')
    load_options_file_from_packedmc('Survival', instance(), DEFAULT_NAME)
    assert MINECRAFT_OPTIONS.read_text() == 'untouched'


# ========================================================================================= write_instance_data_to_profiles_file
@pytest.fixture
def now(monkeypatch):
    return freeze_datetime(monkeypatch, launcher, datetime(2026, 2, 3, 4, 5, 6))


def test_without_launcher_profiles_file_nothing_is_created(caplog):
    with caplog.at_level(logging.ERROR):
        write_instance_data_to_profiles_file('Survival', instance(type='Release', version='1.21.4'))

    assert not paths.MINECRAFT_LAUNCHER_PROFILES_PATH.exists()
    assert 'Could not find the Minecraft Launcher profiles file' in caplog.text


def test_a_packedmc_profile_is_written(now):
    write_launcher_profiles()

    write_instance_data_to_profiles_file('Survival', instance(type='Release', version='1.20.1', minecraft_directory=str(paths.MINECRAFT_DIRECTORY)))

    profile = read_launcher_profiles()['profiles'][MINECRAFT_LAUNCHER_PACKEDMC_PROFILE_ID]
    assert profile['name'] == 'PackedMC - Survival'
    assert profile['lastVersionId'] == '1.20.1'
    assert profile['gameDir'] == str(paths.MINECRAFT_DIRECTORY)
    assert profile['type'] == 'custom'
    assert profile['created'] == profile['lastUsed'] == '2026-02-03T04:05:06.000Z'
    assert profile['icon'] == 'data:image/png;base64,' + (paths.ICONS_FILE_PATH / 'logo64.b64').read_text()


def test_the_java_arguments_are_built_from_the_advanced_arguments():
    write_launcher_profiles()
    arguments = AdvancedArgumentsData(start_heap_size=4, max_heap_size=8, other_arguments='-Dfoo=bar -XX:+UseG1GC')

    write_instance_data_to_profiles_file('Survival', instance(version='1.20.1', advanced_arguments=arguments))

    assert read_launcher_profiles()['profiles']['packedmc']['javaArgs'] == ' -Xms4G -Xmx8G -Dfoo=bar -XX:+UseG1GC'


def test_default_java_arguments():
    write_launcher_profiles()
    write_instance_data_to_profiles_file('Survival', instance(version='1.20.1'))
    assert read_launcher_profiles()['profiles']['packedmc']['javaArgs'] == f' -Xms2G -Xmx2G {DEFAULT_OTHER_JVM_ARGS}'


def test_latest_is_replaced_by_the_newest_release():
    write_launcher_profiles()
    write_instance_data_to_profiles_file('Survival', instance(type='Release', version='latest'))
    assert read_launcher_profiles()['profiles']['packedmc']['lastVersionId'] == '1.21.4'


def test_the_creation_time_and_other_profiles_are_preserved(now):
    write_launcher_profiles({
        'packedmc': make_launcher_profile(name='PackedMC - Old', last_used='2025-05-05T05:05:05.000Z', created='2025-01-01T00:00:00.000Z'),
        'other': make_launcher_profile(name='Other profile'),
    })

    write_instance_data_to_profiles_file('Survival', instance(version='1.20.1'))

    profiles = read_launcher_profiles()['profiles']
    assert profiles['packedmc']['created'] == '2025-01-01T00:00:00.000Z'
    assert profiles['packedmc']['lastUsed'] == '2026-02-03T04:05:06.000Z'
    assert profiles['packedmc']['name'] == 'PackedMC - Survival'
    assert profiles['other'] == make_launcher_profile(name='Other profile')
    assert read_launcher_profiles()['version'] == 3  # The rest of the file is kept


def test_an_existing_fabric_loader_is_used_without_downloading(fake_internet):
    write_launcher_profiles()
    (paths.VERSIONS_DIRECTORY / 'fabric-loader-0.16.5-1.21.4').mkdir(parents=True)
    (paths.VERSIONS_DIRECTORY / 'fabric-loader-0.16.5-1.20.1').mkdir()  # Another Minecraft version

    write_instance_data_to_profiles_file('Survival', instance(type='Fabric', version='1.21.4'))

    assert read_launcher_profiles()['profiles']['packedmc']['lastVersionId'] == 'fabric-loader-0.16.5-1.21.4'
    fake_internet.assert_no_requests()


def test_fabric_is_installed_if_no_loader_exists_for_the_version(fake_internet):
    write_launcher_profiles()
    (paths.VERSIONS_DIRECTORY / 'fabric-loader-0.16.5-1.20.1').mkdir(parents=True)  # Only for another version

    write_instance_data_to_profiles_file('Survival', instance(type='Fabric', version='1.21.4'))

    assert read_launcher_profiles()['profiles']['packedmc']['lastVersionId'] == 'fabric-loader-0.16.9-1.21.4'
    assert directory_listing(paths.VERSIONS_DIRECTORY / 'fabric-loader-0.16.9-1.21.4') == ['fabric-loader-0.16.9-1.21.4.jar', 'fabric-loader-0.16.9-1.21.4.json']
    assert sorted(fake_internet.urls()) == sorted([
        'https://meta.fabricmc.net/v2/versions/loader',
        'https://maven.fabricmc.net/net/fabricmc/fabric-loader/0.16.9/fabric-loader-0.16.9.jar',
        'https://meta.fabricmc.net/v2/versions/loader/1.21.4/0.16.9/profile/json',
    ])


@pytest.mark.xfail(reason='BUG: The newest loader is chosen with a plain string sort, so "0.16.9" is considered newer than "0.16.10".')
def test_the_newest_installed_fabric_loader_is_chosen_by_version_number(fake_internet):
    write_launcher_profiles()
    for loader_version in ('0.16.9', '0.16.10'):
        (paths.VERSIONS_DIRECTORY / f'fabric-loader-{loader_version}-1.21.4').mkdir(parents=True)

    write_instance_data_to_profiles_file('Survival', instance(type='Fabric', version='1.21.4'))

    assert read_launcher_profiles()['profiles']['packedmc']['lastVersionId'] == 'fabric-loader-0.16.10-1.21.4'


@pytest.mark.xfail(reason='SUSPECTED BUG: For Fabric with version "latest" the installed loaders are compared with the string "latest" instead of the resolved version, '
                          'so an existing loader is never found and Fabric is downloaded again every time.')
def test_fabric_latest_reuses_an_installed_loader(fake_internet):
    write_launcher_profiles()
    (paths.VERSIONS_DIRECTORY / 'fabric-loader-0.16.9-1.21.4').mkdir(parents=True)

    write_instance_data_to_profiles_file('Survival', instance(type='Fabric', version='latest'))

    assert read_launcher_profiles()['profiles']['packedmc']['lastVersionId'] == 'fabric-loader-0.16.9-1.21.4'
    fake_internet.assert_no_requests()
