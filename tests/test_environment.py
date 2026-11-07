"""
Tests for the test environment itself. If one of these fails, the sandbox is broken and all other results are
untrustworthy, so they are worth a look first.
"""
import ast
import sys
from pathlib import Path

import pytest
import requests

from . import fake_file_paths as paths
from .fake_internet import FakeInternet, UnregisteredRequest


REAL_FILE_PATHS_SOURCE = Path(__file__).resolve().parent.parent / 'utils' / 'file_paths.py'


# ----------------------------------------------------------------------------------------------- file path override
def test_project_modules_use_the_testing_file_paths():
    import interface
    import utils.data_file_helper
    import utils.mod_files_handler
    import minecraft_api.minecraft
    import minecraft_api.minecraft_launcher_integration

    assert sys.modules['utils.file_paths'] is paths
    assert interface.DATA_FILE_PATH == paths.DATA_FILE_PATH
    assert interface.BACKUP_DIRECTORY == paths.BACKUP_DIRECTORY
    assert utils.mod_files_handler.PACKEDMC_MINECRAFT_DATA_DIRECTORY == paths.PACKEDMC_MINECRAFT_DATA_DIRECTORY
    assert utils.data_file_helper.MINECRAFT_DIRECTORY == paths.MINECRAFT_DIRECTORY
    assert minecraft_api.minecraft_launcher_integration.MINECRAFT_LAUNCHER_PROFILES_PATH == paths.MINECRAFT_LAUNCHER_PROFILES_PATH
    assert minecraft_api.minecraft._MINECRAFT_VERSIONS_CACHE_FILE.parent == paths.CACHE_DIRECTORY


def _names_defined_by_real_file_paths() -> set[str]:
    """ Public names of utils/file_paths.py, found by parsing it (importing it would raise an OSError on non-Windows). """
    tree = ast.parse(REAL_FILE_PATHS_SOURCE.read_text(encoding='utf-8'))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    names.add(target.id)
        elif isinstance(node, ast.FunctionDef) and node in tree.body:
            names.add(node.name)
    return names


def test_testing_file_paths_defines_everything_the_real_file_defines():
    """ If this fails, a path was added to utils/file_paths.py. Add it to tests/testing_file_paths.py as well. """
    missing = {name for name in _names_defined_by_real_file_paths() if not hasattr(paths, name)}
    assert not missing, f'tests/testing_file_paths.py is missing: {sorted(missing)}'


def test_all_user_data_paths_are_inside_the_testing_directory():
    checked = 0
    for name in _names_defined_by_real_file_paths():
        value = getattr(paths, name)
        if not isinstance(value, Path) or name in paths.REAL_RESOURCE_NAMES:
            continue
        checked += 1
        assert value.resolve().is_relative_to(paths.TESTING_DIRECTORY.resolve()), f'{name} = {value} is outside of the testing directory'

    assert checked > 5


def test_real_resources_still_exist():
    for name in paths.REAL_RESOURCE_NAMES:
        assert getattr(paths, name).exists(), f'{name} does not exist'


def test_minecraft_directory_counts_as_inside_the_user_home():
    assert paths.is_subdir_of_user_home(str(paths.MINECRAFT_DIRECTORY))
    assert not paths.is_subdir_of_user_home(str(paths.TESTING_DIRECTORY.parent))  # Outside of the fake home
    assert not paths.is_subdir_of_user_home(str(paths.FAKE_HOME_DIRECTORY))  # The home directory itself does not count


# --------------------------------------------------------------------------------------------------------- isolation
def test_isolation_part_1_writes_files():
    (paths.MAIN_DIRECTORY / 'leftover.txt').write_text('from test 1')
    (paths.CACHE_DIRECTORY / 'cache_leftover.txt').write_text('from test 1')
    assert (paths.MAIN_DIRECTORY / 'leftover.txt').exists()


def test_isolation_part_2_does_not_see_files_of_part_1():
    assert not (paths.MAIN_DIRECTORY / 'leftover.txt').exists()
    assert not (paths.CACHE_DIRECTORY / 'cache_leftover.txt').exists()


def test_directories_created_at_import_time_exist_in_every_test():
    from minecraft_api import mod
    assert mod._MODRINTH_CACHE_DIRECTORY.is_dir()
    assert mod._CURSEFORGE_CACHE_DIRECTORY.is_dir()
    assert paths.PACKEDMC_OPTIONS_FILES_DIRECTORY.is_dir()
    assert paths.BACKUP_DIRECTORY.is_dir()


# ------------------------------------------------------------------------------------------------- safety fixtures
def test_message_boxes_and_dialogs_do_not_block(dialogs):
    from PyQt6.QtWidgets import QMessageBox
    assert QMessageBox.question(None, 'Title', 'Text') == QMessageBox.StandardButton.No  # The safe default
    dialogs.answer_yes()
    assert QMessageBox.question(None, 'Title 2', 'Text 2') == QMessageBox.StandardButton.Yes
    assert [m.title for m in dialogs.messages] == ['Title', 'Title 2']


def test_subprocesses_are_recorded_and_not_executed(subprocesses):
    import subprocess
    subprocess.run('explorer.exe something', shell=True)
    subprocess.Popen(['explorer', 'path'])
    assert subprocesses.commands() == ['explorer.exe something', 'explorer path']


def test_real_process_list_is_not_used(running_processes):
    import psutil
    assert list(psutil.process_iter(['name'])) == []
    running_processes.append('MinecraftLauncher.exe')
    assert [p.info['name'] for p in psutil.process_iter(['name'])] == ['MinecraftLauncher.exe']


def test_project_threads_run_inline_and_errors_are_collected(inline_thread_errors):
    import threading
    from minecraft_api import mod
    ran = []

    thread = threading.Thread(target=lambda: ran.append(1))  # Not project code: a real thread
    thread.start()
    thread.join()
    assert ran == [1]

    # A project function which fails inside a thread: the error is collected instead of being lost
    def failing_function():
        raise ValueError('boom')
    failing_function.__module__ = 'minecraft_api.fake'
    threading.Thread(target=failing_function).start()

    assert len(inline_thread_errors) == 1 and isinstance(inline_thread_errors[0][1], ValueError)
    inline_thread_errors.clear()  # We expected it, so the fixture does not fail the test


# ------------------------------------------------------------------------------------------- the fake internet itself
def test_requests_are_answered_from_routes_and_recorded(fake_internet):
    response = requests.get('https://meta.fabricmc.net/v2/versions/loader', headers={'User-Agent': 'tests'}, timeout=5)

    assert response.status_code == 200
    assert response.json()[0]['version'] == '0.16.10'
    request = fake_internet.assert_requested('https://meta.fabricmc.net/v2/versions/loader')[0]
    assert request.method == 'GET' and request.header('user-agent') == 'tests' and request.timeout == 5


def test_unregistered_url_raises_and_is_remembered():
    internet = FakeInternet()
    with pytest.raises(UnregisteredRequest):
        internet._handle('GET', 'https://example.invalid/x', {}, None, None, 'requests')
    assert [str(r) for r in internet.unmatched] == ['GET https://example.invalid/x']


def test_routes_added_by_a_test_beat_the_defaults_and_specific_routes_beat_general_ones(fake_internet):
    # The default routes contain a plain jei route and a more specific one with a query
    plain = requests.get('https://api.cfwidget.com/minecraft/mc-mods/jei').json()
    specific = requests.get('https://api.cfwidget.com/minecraft/mc-mods/jei?version=1.21.4&loader=fabric').json()
    assert 'files' in plain and 'download' in specific

    # A route from a test wins, even though the default route with the query is more specific
    fake_internet.add_route('https://api.cfwidget.com/minecraft/mc-mods/jei', json={'overridden': True})
    assert requests.get('https://api.cfwidget.com/minecraft/mc-mods/jei').json() == {'overridden': True}
    assert requests.get('https://api.cfwidget.com/minecraft/mc-mods/jei?version=1.21.4&loader=fabric').json() == {'overridden': True}

    # Among the routes of a test, the specific one wins again
    fake_internet.add_route('https://api.cfwidget.com/minecraft/mc-mods/jei', match_query={'loader': 'fabric'}, json={'fabric': True})
    assert requests.get('https://api.cfwidget.com/minecraft/mc-mods/jei?version=1.21.4&loader=fabric').json() == {'fabric': True}
    assert requests.get('https://api.cfwidget.com/minecraft/mc-mods/jei').json() == {'overridden': True}


def test_wildcard_routes_and_status_codes(fake_internet):
    assert requests.get('https://cdn.modrinth.com/data/ANYTHING/icon.png').content.startswith(b'\x89PNG')

    fake_internet.add_route('https://example.com/missing', status=404, text='nope')
    response = requests.get('https://example.com/missing')
    assert response.status_code == 404 and response.text == 'nope' and not response


def test_offline_mode_raises_connection_errors(fake_internet):
    fake_internet.go_offline()
    with pytest.raises(requests.exceptions.ConnectionError):
        requests.get('https://meta.fabricmc.net/v2/versions/loader')
    assert len(fake_internet.requests) == 1  # Attempts are still recorded
    assert not fake_internet.unmatched
