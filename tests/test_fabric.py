import pytest

from minecraft_api import fabric
from minecraft_api.fabric import VersionException

from . import fake_file_paths as paths
from .fake_internet import RESPONSES_DIRECTORY
from .helpers import directory_listing

LOADER_VERSIONS_URL = 'https://meta.fabricmc.net/v2/versions/loader'
PROFILE_URL = 'https://meta.fabricmc.net/v2/versions/loader/1.21.4/0.16.9/profile/json'
JAR_URL = 'https://maven.fabricmc.net/net/fabricmc/fabric-loader/0.16.9/fabric-loader-0.16.9.jar'


def test_newest_fabric_version_is_the_first_stable_one(fake_internet):
    assert fabric.get_newest_fabric_version() == '0.16.9'  # 0.16.10 is listed first but unstable
    fake_internet.assert_requested(LOADER_VERSIONS_URL)


def test_newest_fabric_version_without_stable_version_raises(fake_internet):
    fake_internet.add_route(LOADER_VERSIONS_URL, json=[{'version': '1.0.0', 'stable': False}])
    with pytest.raises(VersionException):
        fabric.get_newest_fabric_version()


def test_get_json_file_returns_the_profile(fake_internet):
    content = fabric.get_json_file('1.21.4', '0.16.9')

    assert content == (RESPONSES_DIRECTORY / 'fabric_profile_0.16.9_1.21.4.json').read_bytes()
    fake_internet.assert_requested(PROFILE_URL)


def test_get_json_file_for_unsupported_minecraft_version_raises():
    with pytest.raises(VersionException, match='No Fabric JSON found for Minecraft 1.0.0-unknown'):
        fabric.get_json_file('1.0.0-unknown', '0.16.9')


def test_get_jar_file_returns_the_jar(fake_internet):
    assert fabric.get_jar_file('0.16.9') == (RESPONSES_DIRECTORY / 'fabric-loader-0.16.9.jar').read_bytes()
    fake_internet.assert_requested(JAR_URL)


def test_get_jar_file_for_unknown_fabric_version_raises():
    with pytest.raises(VersionException, match='9.9.9'):
        fabric.get_jar_file('9.9.9')


def test_install_version_creates_directory_jar_and_json(fake_internet):
    full_name = fabric.install_version(paths.VERSIONS_DIRECTORY, minecraft_version='1.21.4', fabric_version='0.16.9')

    assert full_name == 'fabric-loader-0.16.9-1.21.4'
    directory = paths.VERSIONS_DIRECTORY / full_name
    assert directory_listing(directory) == ['fabric-loader-0.16.9-1.21.4.jar', 'fabric-loader-0.16.9-1.21.4.json']
    assert (directory / f'{full_name}.jar').read_bytes() == (RESPONSES_DIRECTORY / 'fabric-loader-0.16.9.jar').read_bytes()
    assert (directory / f'{full_name}.json').read_bytes() == (RESPONSES_DIRECTORY / 'fabric_profile_0.16.9_1.21.4.json').read_bytes()
    assert sorted(fake_internet.urls()) == sorted([JAR_URL, PROFILE_URL])  # The Fabric version was given, so it is not looked up


def test_install_version_defaults_to_latest_release_and_newest_stable_fabric(fake_internet):
    full_name = fabric.install_version(paths.VERSIONS_DIRECTORY)

    assert full_name == 'fabric-loader-0.16.9-1.21.4'
    assert sorted(fake_internet.urls()) == sorted([LOADER_VERSIONS_URL, JAR_URL, PROFILE_URL])
    assert (paths.VERSIONS_DIRECTORY / full_name).is_dir()


def test_install_version_can_be_repeated_and_overwrites_the_files():
    fabric.install_version(paths.VERSIONS_DIRECTORY, minecraft_version='1.21.4', fabric_version='0.16.9')
    jar = paths.VERSIONS_DIRECTORY / 'fabric-loader-0.16.9-1.21.4' / 'fabric-loader-0.16.9-1.21.4.jar'
    jar.write_bytes(b'corrupted')

    fabric.install_version(paths.VERSIONS_DIRECTORY, minecraft_version='1.21.4', fabric_version='0.16.9')

    assert jar.read_bytes() == (RESPONSES_DIRECTORY / 'fabric-loader-0.16.9.jar').read_bytes()


def test_install_version_for_unsupported_minecraft_version_creates_nothing():
    with pytest.raises(VersionException):
        fabric.install_version(paths.VERSIONS_DIRECTORY, minecraft_version='1.0.0-unknown', fabric_version='0.16.9')

    assert directory_listing(paths.VERSIONS_DIRECTORY) == []
