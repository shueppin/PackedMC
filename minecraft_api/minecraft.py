import os
import requests
import json
import threading
import logging


logger = logging.getLogger(__name__)


_ACTUAL_FILE_DIRECTORY = os.path.dirname(__file__)
_CACHE_FILE = os.path.join(_ACTUAL_FILE_DIRECTORY, 'cache/minecraft_versions.json')
_MINECRAFT_VERSIONS_URL = 'https://launchermeta.mojang.com/mc/game/version_manifest.json'


LATEST_RELEASE = ''
LATEST_SNAPSHOT = ''
ALL_RELEASE_VERSIONS = []
ALL_SNAPSHOT_VERSIONS = []


def _reload_data():
    global LATEST_RELEASE, LATEST_SNAPSHOT, ALL_RELEASE_VERSIONS, ALL_SNAPSHOT_VERSIONS

    try:
        response = requests.get(_MINECRAFT_VERSIONS_URL, timeout=10)
        json_data = response.json()
    except requests.exceptions.ConnectionError:
        return

    # Set the values from the JSON
    LATEST_RELEASE = json_data['latest']['release']
    LATEST_SNAPSHOT = json_data['latest']['snapshot']

    ALL_RELEASE_VERSIONS = []
    ALL_SNAPSHOT_VERSIONS = []

    for version in json_data['versions']:
        if version['type'] == 'release':
            ALL_RELEASE_VERSIONS.append(version['id'])
        else:
            ALL_SNAPSHOT_VERSIONS.append(version['id'])

    # Set the cache
    with open(_CACHE_FILE, 'w') as file:
        cached_data = {
            'latest_release': LATEST_RELEASE,
            'latest_snapshot': LATEST_SNAPSHOT,
            'all_release_versions': ALL_RELEASE_VERSIONS,
            'all_snapshot_versions': ALL_SNAPSHOT_VERSIONS
        }

        json.dump(cached_data, file)

        logger.info('Updated cached data')


def initialize_versions():
    """Call once at program startup."""
    global LATEST_RELEASE, LATEST_SNAPSHOT, ALL_RELEASE_VERSIONS, ALL_SNAPSHOT_VERSIONS

    # Load cached data first (fast startup)
    cached_data = {}

    if os.path.exists(_CACHE_FILE):
        with open(_CACHE_FILE, 'r') as file:
            cached_data = json.load(file)

    try:
        LATEST_RELEASE = cached_data['latest_release']
        LATEST_SNAPSHOT = cached_data['latest_snapshot']
        ALL_RELEASE_VERSIONS = cached_data['all_release_versions']
        ALL_SNAPSHOT_VERSIONS = cached_data['all_snapshot_versions']
    except KeyError:
        logger.warning('No cached minecraft versions found')
        _reload_data()

    # Start background updater
    threading.Thread(target=_reload_data, daemon=True).start()


def get_installed_versions(minecraft_directory: str) -> list[str]:
    try:
        versions_path = os.path.join(minecraft_directory, 'versions')
        content = os.listdir(versions_path)

        all_dirs = []
        for file_or_dir in content:
            if os.path.isdir(os.path.join(versions_path, file_or_dir)):
                all_dirs.append(file_or_dir)

        return sorted(all_dirs, reverse=True)
    except FileNotFoundError:
        return []


# Get the minecraft versions
initialize_versions()
