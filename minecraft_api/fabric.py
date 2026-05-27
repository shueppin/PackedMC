import os
import requests

from .minecraft import LATEST_RELEASE


FABRIC_VERSIONS_URL = 'https://meta.fabricmc.net/v2/versions/loader'
JSON_FILE_URL = 'https://meta.fabricmc.net/v2/versions/loader/{minecraft_version}/{fabric_version}/profile/json'
JAR_FILE_URL = 'https://maven.fabricmc.net/net/fabricmc/fabric-loader/{fabric_version}/fabric-loader-{fabric_version}.jar'


class VersionException(Exception):
    def __init__(self, message):
        super().__init__(message)


def get_newest_fabric_version() -> str:  # Get the newest stable fabric.py version
    response = requests.get(FABRIC_VERSIONS_URL)
    for version_json in response.json():
        if version_json['stable']:
            return version_json['version']

    raise VersionException('No newest fabric version found')


def get_json_file(minecraft_version: str, fabric_version: str):
    json_file_url = JSON_FILE_URL.format(minecraft_version=minecraft_version, fabric_version=fabric_version)
    json_response = requests.get(json_file_url)
    json_file_content = json_response.content

    if str(json_file_content.decode()) == f'no mappings version found for {minecraft_version}':
        raise VersionException(f'No Fabric Version found for Minecraft {minecraft_version}')

    return json_file_content


def get_jar_file(fabric_version: str):
    jar_file_url = JAR_FILE_URL.format(fabric_version=fabric_version)
    jar_response = requests.get(jar_file_url)
    jar_file_content = jar_response.content

    if not jar_response:
        raise VersionException(f'No Fabric Version found for "{fabric_version}"')

    return jar_file_content


def install_version(versions_directory: str, minecraft_version='', fabric_version='') -> str:
    """ Install the fabric in the version directory and return the full name of the installed version. """
    if not minecraft_version:
        minecraft_version = LATEST_RELEASE

    if not fabric_version:
        fabric_version = get_newest_fabric_version()

    # Get the content
    jar_file_content = get_jar_file(fabric_version)
    json_file_content = get_json_file(minecraft_version, fabric_version)

    # Save the content
    full_instance_name = f'fabric-loader-{fabric_version}-{minecraft_version}'
    directory_path = os.path.join(versions_directory, full_instance_name)

    try:
        os.mkdir(directory_path)
    except FileExistsError:
        pass

    jar_file_path = os.path.join(directory_path, full_instance_name + '.jar')
    json_file_path = os.path.join(directory_path, full_instance_name + '.json')

    try:
        with open(jar_file_path, 'wb') as file:
            file.write(jar_file_content)
    except FileExistsError:
        pass

    try:
        with open(json_file_path, 'wb') as file:
            file.write(json_file_content)
    except FileExistsError:
        pass

    return full_instance_name
