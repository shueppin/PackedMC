import json
import logging

from minecraft_api import minecraft

from . import testing_file_paths as paths
from .helpers import read_json, write_json

MOJANG_URL = 'https://launchermeta.mojang.com/mc/game/version_manifest.json'
CACHE_FILE = paths.CACHE_DIRECTORY / 'minecraft_versions.json'


def test_versions_were_loaded_from_the_fake_internet_when_the_project_was_imported():
    assert minecraft.LATEST_RELEASE == '1.21.4'
    assert minecraft.LATEST_SNAPSHOT == '25w06a'
    assert minecraft.ALL_RELEASE_VERSIONS == ['1.21.4', '1.21.3', '1.20.1', '1.19.4']
    assert minecraft.ALL_SNAPSHOT_VERSIONS == ['25w06a', '24w14a']


def test_reload_data_requests_the_mojang_manifest_and_writes_the_cache(fake_internet):
    minecraft.LATEST_RELEASE = ''
    minecraft.ALL_RELEASE_VERSIONS = []

    minecraft._reload_data()

    request = fake_internet.assert_requested(MOJANG_URL)[0]
    assert request.timeout == 10
    assert minecraft.LATEST_RELEASE == '1.21.4'
    assert minecraft.ALL_RELEASE_VERSIONS == ['1.21.4', '1.21.3', '1.20.1', '1.19.4']
    assert read_json(CACHE_FILE) == {
        'latest_release': '1.21.4',
        'latest_snapshot': '25w06a',
        'all_release_versions': ['1.21.4', '1.21.3', '1.20.1', '1.19.4'],
        'all_snapshot_versions': ['25w06a', '24w14a'],
    }


def test_reload_data_picks_up_new_versions(fake_internet):
    fake_internet.add_route(MOJANG_URL, json={
        'latest': {'release': '1.22', 'snapshot': '26w01a'},
        'versions': [{'id': '26w01a', 'type': 'snapshot'}, {'id': '1.22', 'type': 'release'}, {'id': '1.21.4', 'type': 'release'}],
    })

    minecraft._reload_data()

    assert minecraft.LATEST_RELEASE == '1.22'
    assert minecraft.ALL_RELEASE_VERSIONS == ['1.22', '1.21.4']
    assert minecraft.ALL_SNAPSHOT_VERSIONS == ['26w01a']


def test_reload_data_while_offline_keeps_the_old_data_and_writes_no_cache(fake_internet):
    fake_internet.go_offline()

    minecraft._reload_data()  # Must not raise

    assert minecraft.LATEST_RELEASE == '1.21.4'
    assert not CACHE_FILE.exists()


def test_initialize_versions_without_cache_loads_synchronously_and_refreshes_in_the_background(fake_internet):
    minecraft.LATEST_RELEASE = ''
    minecraft.ALL_RELEASE_VERSIONS = []

    minecraft.initialize_versions()

    assert minecraft.LATEST_RELEASE == '1.21.4'
    assert CACHE_FILE.exists()
    assert len(fake_internet.requests_to(MOJANG_URL)) == 2  # Once because there was no cache, once for the background refresh


def test_initialize_versions_uses_the_cache_when_offline(fake_internet):
    write_json(CACHE_FILE, {'latest_release': '1.0', 'latest_snapshot': '1.0-pre', 'all_release_versions': ['1.0'], 'all_snapshot_versions': ['1.0-pre']})
    fake_internet.go_offline()

    minecraft.initialize_versions()

    assert minecraft.LATEST_RELEASE == '1.0'
    assert minecraft.ALL_RELEASE_VERSIONS == ['1.0']
    assert minecraft.ALL_SNAPSHOT_VERSIONS == ['1.0-pre']
    assert len(fake_internet.requests_to(MOJANG_URL)) == 1  # Only the background refresh, which failed silently


def test_initialize_versions_with_cache_refreshes_in_the_background(fake_internet):
    write_json(CACHE_FILE, {'latest_release': '1.0', 'latest_snapshot': 's', 'all_release_versions': ['1.0'], 'all_snapshot_versions': ['s']})

    minecraft.initialize_versions()

    assert len(fake_internet.requests_to(MOJANG_URL)) == 1
    assert minecraft.LATEST_RELEASE == '1.21.4'  # Refreshed by the (inline) background thread


def test_initialize_versions_with_incomplete_cache_reloads(fake_internet, caplog):
    write_json(CACHE_FILE, {'latest_release': '1.0'})

    with caplog.at_level(logging.WARNING):
        minecraft.initialize_versions()

    assert 'No cached minecraft versions found' in caplog.text
    assert minecraft.ALL_RELEASE_VERSIONS == ['1.21.4', '1.21.3', '1.20.1', '1.19.4']


def test_get_installed_versions_lists_only_directories_newest_name_first(tmp_path):
    versions = tmp_path / 'versions'
    for name in ('1.20.1', '1.21.4', 'fabric-loader-0.16.9-1.21.4'):
        (versions / name).mkdir(parents=True)
    (versions / 'notes.txt').write_text('not a version')

    assert minecraft.get_installed_versions(str(tmp_path)) == ['fabric-loader-0.16.9-1.21.4', '1.21.4', '1.20.1']


def test_get_installed_versions_without_versions_directory_is_empty(tmp_path):
    assert minecraft.get_installed_versions(str(tmp_path)) == []
