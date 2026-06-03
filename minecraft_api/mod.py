import requests
import threading
from typing import Callable, Unpack, TypeVarTuple
import os
import json
import markdown

from .minecraft import ALL_RELEASE_VERSIONS


ACTUAL_FILE_DIRECTORY = os.path.dirname(__file__)

CURSEFORGE_BASE_URL = 'https://www.curseforge.com/minecraft/mc-mods/'
CURSEFORGE_API_BASE_URL = 'https://api.cfwidget.com/minecraft/mc-mods/'  # This is not the official API but instead an alternative which doesn't need an API key
CURSEFORGE_FILE_DOWNLOAD_BASE_URL = 'https://edge.forgecdn.net/files/'

MODRINTH_BASE_URL = 'https://modrinth.com/mod/'
MODRINTH_API_BASE_URL = 'https://api.modrinth.com/v2/project/'


PROJECT_OWN_HEADERS = {
    'User-Agent': 'shueppin/PackedMC (in development)'
}


class InvalidModBaseUrl(Exception):
    def __init__(self, url: str):
        message = f'The url "{url}" is not supported by this project. \nExamples for supported urls are: https://modrinth.com/mod/fabric-api or https://www.curseforge.com/minecraft/mc-mods/fabric-api'

        super().__init__(message)


class ModNotExisting(Exception):
    def __init__(self, upload_platform: str, mod_url_or_name: str):
        message = f'{upload_platform.capitalize()} does not have the mod {mod_url_or_name}. Try using the project ID.'

        super().__init__(message)


class TryAgainLater(Exception):
    def __init__(self):
        message = 'The data on the API does not exist yet. Try again in a moment.'

        super().__init__(message)


class EmptyArguments(Exception):
    def __init__(self, variable_name: str, upload_platform: str):
        message = f'{upload_platform.capitalize()} needs a value for the variable "{variable_name}" but the passed value was empty.'

        super().__init__(message)


class APICooldown(Exception):
    def __init__(self, upload_platform):
        message = f'Requests to the {upload_platform} API is on cooldown. Try again in a moment.'

        super().__init__(message)


class NoFileAvailable(Exception):
    def __init__(self, mod_url: str, loader: str, version: str):
        message = f'On "{mod_url}" there is no version available for {loader} {version}.'

        super().__init__(message)


def get_download_url(mod_url: str, game_version: str, mod_loader: str) -> tuple[str, str]:
    """
    Returns the mod download URL and file name.
    """
    if CURSEFORGE_BASE_URL in mod_url:
        return _get_curseforge_download_url(mod_url, game_version, mod_loader)

    elif MODRINTH_BASE_URL in mod_url:
        return _get_modrinth_download_url(mod_url, game_version, mod_loader)

    else:
        raise InvalidModBaseUrl(mod_url)


def _get_curseforge_download_url(curseforge_url: str, game_version: str, mod_loader: str) -> tuple[str, str]:
    try:
        url_for_version_data = CURSEFORGE_API_BASE_URL + curseforge_url[len(CURSEFORGE_BASE_URL):] + '?version=' + game_version + '&loader=' + mod_loader  # Remove the base curseforge url and add the api part and a version and a loader search
        response = requests.get(url_for_version_data)
    except requests.exceptions.ConnectionError:
        return '', ''

    if response.status_code != 200:
        if response.status_code == 202:
            raise TryAgainLater

        else:
            raise ModNotExisting('Curseforge', curseforge_url)

    version_data = response.json()

    try:
        file_data = version_data['download']
        project_id = str(file_data['id'])
        file_name = file_data['name']

        download_url = CURSEFORGE_FILE_DOWNLOAD_BASE_URL + '/' + project_id[:4] + '/' + project_id[4:] + '/' + file_name
        download_url = download_url.replace(' ', '%20')

        return download_url, file_name

    except KeyError:
        raise NoFileAvailable(curseforge_url, mod_loader, game_version)


def _get_modrinth_download_url(modrinth_url: str, game_version: str, mod_loader: str) -> tuple[str, str]:
    if not game_version:
        raise EmptyArguments('game_version', 'modrinth')

    if not mod_loader:
        raise EmptyArguments('mod_loader', 'modrinth')

    try:
        url_for_all_versions_data = MODRINTH_API_BASE_URL + modrinth_url[len(MODRINTH_BASE_URL):] + '/version'  # Remove the base modrinth url and add the api part
        response = requests.get(url_for_all_versions_data, headers=PROJECT_OWN_HEADERS)
    except requests.exceptions.ConnectionError:
        return '', ''

    if response.status_code != 200:
        raise ModNotExisting('Modrinth', modrinth_url)

    if 'x-ratelimit-remaining' in response.headers:
        if int(response.headers['X-Ratelimit-Remaining']) < 1:
            raise APICooldown('modrinth')

    all_versions_data = response.json()

    for version_data in all_versions_data:
        if game_version in version_data['game_versions'] and mod_loader in version_data['loaders']:
            download_url = version_data['files'][0]['url']
            file_name = version_data['files'][0]['filename']

            return download_url, file_name

    raise NoFileAvailable(modrinth_url, mod_loader, game_version)


def get_mod_icon_path(mod_url: str) -> str:
    if CURSEFORGE_BASE_URL in mod_url:
        mod_name = mod_url[len(CURSEFORGE_BASE_URL):]
        return os.path.join(ACTUAL_FILE_DIRECTORY, 'cache', 'curseforge_mods', mod_name + '.png')
    elif MODRINTH_BASE_URL in mod_url:
        mod_name = mod_url[len(MODRINTH_BASE_URL):]
        return os.path.join(ACTUAL_FILE_DIRECTORY, 'cache', 'modrinth_mods', mod_name + '.png')
    else:
        raise InvalidModBaseUrl(mod_url)


params = TypeVarTuple("params")


def get_mod_data(mod_url: str, callback_function: Callable[[str, list[str], list[str], Unpack[params]], None] = None, callback_function_args: tuple[Unpack[params]] = None) -> tuple[str, list[str], list[str]]:
    """
    Get the actual mod data from the API and cache it.
    It returns the cached description as HTML, the compatible mod loaders and the supported game versions (starting with the newest).
    If it could update the data from the API, then it will call the callback function.
    It is recommended to let the callback be a pyqtSignal.emit function, so the Thread can change things in the window.
    """
    if CURSEFORGE_BASE_URL in mod_url:
        mod_name = mod_url[len(CURSEFORGE_BASE_URL):]
        file_path = os.path.join(ACTUAL_FILE_DIRECTORY, 'cache', 'curseforge_mods', mod_name + '.json')
        data_update_function = _update_curseforge_mod
    elif MODRINTH_BASE_URL in mod_url:
        mod_name = mod_url[len(MODRINTH_BASE_URL):]
        file_path = os.path.join(ACTUAL_FILE_DIRECTORY, 'cache', 'modrinth_mods', mod_name + '.json')
        data_update_function = _update_modrinth_mod
    else:
        raise InvalidModBaseUrl(mod_url)

    # TODO: Add a timestamp, so it only checks this mod after a certain time again, otherwise just use the cached data

    # If the file exists, then just start a thread, otherwise run a blocking update
    if os.path.exists(file_path):
        update_thread = threading.Thread(target=data_update_function, args=(mod_name, callback_function, callback_function_args), daemon=True)
        update_thread.start()
    else:
        data_update_function(mod_name)

    # If it still does not exist, then just return nothing
    if not os.path.exists(file_path):
        return '', [], []

    # Return the data from the file
    with open(file_path, 'r') as f:
        mod_data = json.load(f)
        return mod_data['description'], mod_data['loaders'], mod_data['supported_versions']


def _update_curseforge_mod(mod_name: str, callback_function: Callable[[str, list[str], list[str], Unpack[params]], None] = None, callback_function_args: tuple[Unpack[params]] = None):
    try:
        url_for_mod_data = CURSEFORGE_API_BASE_URL + mod_name
        response = requests.get(url_for_mod_data, headers=PROJECT_OWN_HEADERS, timeout=10)
    except requests.exceptions.ConnectionError:
        return

    if response.status_code != 200:
        raise ModNotExisting('Curseforge', mod_name)

    mod_data = response.json()

    # Get the supported versions and the loaders
    loaders_and_versions = set()
    for file_data in mod_data['files']:
        loaders_and_versions.update(file_data['versions'])

    supported_versions = []
    for game_version in ALL_RELEASE_VERSIONS:  # Use the Release Versions
        if game_version in loaders_and_versions:
            supported_versions.append(game_version)
            loaders_and_versions.remove(game_version)

    # Add the leftover versions which don't contain "snapshot" as loader
    loaders = []
    for version in loaders_and_versions:
        if 'snapshot' not in version.lower():
            loaders.append(version)

    # Update the data
    data_file_path = os.path.join(ACTUAL_FILE_DIRECTORY, 'cache', 'curseforge_mods', mod_name + '.json')
    html_description = mod_data['description']
    with open(data_file_path, 'w') as f:
        json_data = {
            'description': html_description,
            'loaders': sorted(loaders),
            'supported_versions': supported_versions
        }
        json.dump(json_data, f)

    # Download the icon
    icon_url = mod_data['thumbnail']
    icon_file_path = os.path.join(ACTUAL_FILE_DIRECTORY, 'cache', 'curseforge_mods', mod_name + '.png')

    response = requests.get(icon_url)
    with open(icon_file_path, 'wb') as file:
        file.write(response.content)

    if callback_function is not None:
        callback_function(html_description, sorted(loaders), supported_versions, *callback_function_args)


def _update_modrinth_mod(mod_name: str, callback_function: Callable[[str, list[str], list[str], Unpack[params]], None] = None, callback_function_args: tuple[Unpack[params]] = None):
    try:
        url_for_mod_data = MODRINTH_API_BASE_URL + mod_name
        response = requests.get(url_for_mod_data, headers=PROJECT_OWN_HEADERS, timeout=10)
    except requests.exceptions.ConnectionError:
        return

    if response.status_code != 200:
        raise ModNotExisting('Modrinth', mod_name)

    if 'x-ratelimit-remaining' in response.headers:
        if int(response.headers['x-ratelimit-remaining']) < 1:
            raise APICooldown('modrinth')

    mod_data = response.json()

    # Get the releases
    supported_versions = []
    for version in reversed(mod_data['game_versions']):
        if version in ALL_RELEASE_VERSIONS:
            supported_versions.append(version)

    # Get the loaders
    loaders = [loader.capitalize() for loader in mod_data['loaders']]

    # Update the data
    data_file_path = os.path.join(ACTUAL_FILE_DIRECTORY, 'cache', 'modrinth_mods', mod_name + '.json')
    html_description = markdown.markdown(mod_data['body'])
    with open(data_file_path, 'w') as f:
        json_data = {
            'description': html_description,
            'loaders': sorted(loaders),
            'supported_versions': supported_versions
        }
        json.dump(json_data, f)

    # Download the icon
    icon_url = mod_data['icon_url']
    icon_file_path = os.path.join(ACTUAL_FILE_DIRECTORY, 'cache', 'modrinth_mods', mod_name + '.png')

    response = requests.get(icon_url)
    with open(icon_file_path, 'wb') as file:
        file.write(response.content)

    if callback_function is not None:
        callback_function(html_description, sorted(loaders), supported_versions, *callback_function_args)
