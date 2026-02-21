import requests
import os


MINECRAFT_VERSIONS_URL = 'https://launchermeta.mojang.com/mc/game/version_manifest.json'


# Get all minecraft versions
_response = requests.get(MINECRAFT_VERSIONS_URL)
_json_data = _response.json()
# TODO: Cache this for offline use
# TODO: Maybe actualize this data every once in a while

LATEST_RELEASE = _json_data['latest']['release']
LATEST_SNAPSHOT = _json_data['latest']['snapshot']

# Create a list for the names and a tuple for the corresponding type (release/snapshot)
ALL_RELEASE_VERSIONS = []
ALL_SNAPSHOT_VERSIONS = []
for _version in _json_data['versions']:
    if _version['type'] == 'release':
        ALL_RELEASE_VERSIONS.append(_version['id'])
    else:
        ALL_SNAPSHOT_VERSIONS.append(_version['id'])


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