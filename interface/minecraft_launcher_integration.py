import os
import json
from datetime import datetime
import logging
import shutil
import subprocess

from .file_paths import PACKEDMC_MINECRAFT_DATA_DIRECTORY, MINECRAFT_DIRECTORY, MINECRAFT_LAUNCHER_PROFILES_PATH, ICONS_FILE_PATH
from .type_hinting import _SingleInstanceDictType

from minecraft_api.minecraft import ALL_RELEASE_VERSIONS
from minecraft_api.fabric import install_version


logger = logging.getLogger(__name__)


MINECRAFT_LAUNCHER_PACKEDMC_PROFILE_ID = 'packedmc'

MINECRAFT_LAUNCHER_APP = r"Microsoft.4297127D64EC6_8wekyb3d8bbwe!Minecraft"


def start_official_launcher():
    # Launch the official Launcher from the Microsoft Store
    try:
        subprocess.run(rf'explorer.exe shell:AppsFolder\{MINECRAFT_LAUNCHER_APP}', shell=True)
    except FileNotFoundError:
        logger.error("Could not find the Minecraft Launcher executable.")


def save_options_file_of_last_used_instance(last_played_instance_name: str, last_played_instance_data: _SingleInstanceDictType, default_instance_name: str):
    """Copy the options file of the last used instance to the folder of the corresponding instance. """
    packedmc_options_files_directory = os.path.join(PACKEDMC_MINECRAFT_DATA_DIRECTORY, 'options_files')

    last_played_profile_id, last_played_profile_data = get_last_played_minecraft_launcher_profile()

    if last_played_profile_id == MINECRAFT_LAUNCHER_PACKEDMC_PROFILE_ID:
        last_played_instance = last_played_instance_name

        # Either use the default instance or the last played one
        if last_played_instance_data['use_default_options_file']:
            output_file_path = os.path.join(packedmc_options_files_directory, default_instance_name + '.txt')
        else:
            output_file_path = os.path.join(packedmc_options_files_directory, last_played_instance + '.txt')

        # Create the options file path based on the last profile's minecraft directory
        minecraft_options_file_path = os.path.join(last_played_instance_data["minecraft_directory"], 'options.txt')

        try:
            shutil.copy2(minecraft_options_file_path, output_file_path)
            logger.info(f'Stored previous options file from "{minecraft_options_file_path}" under "{output_file_path}"')
        except FileNotFoundError:
            logger.warning(f'Options file not found at {minecraft_options_file_path}')

    else:
        # TODO: Maybe prompt the user whether he wants to replace the options file of the last played instance with this
        logger.warning('PackedMC was not the last played profile, thus only a backup of the newest options file was made.')
        backup_file_path = os.path.join(PACKEDMC_MINECRAFT_DATA_DIRECTORY, 'backup_options.txt')

        # Create the options file path based on the last profile's Game Directory
        last_played_profile_game_dir = last_played_profile_data.get('gameDir')
        if not last_played_profile_game_dir:
            logger.warning("Launcher profile data could not be found.")
            return
        minecraft_options_file_path = os.path.join(last_played_profile_id, 'options.txt')

        try:
            shutil.copy2(minecraft_options_file_path, backup_file_path)
            logger.info(f'Backed up options file from "{minecraft_options_file_path}" to "{backup_file_path}"')
        except FileNotFoundError:
            logger.warning(f'Options file not found at {minecraft_options_file_path}')


def load_options_file_from_packedmc(instance_name: str, actual_instance_data: _SingleInstanceDictType, default_instance_name: str):
    # Copy the options file from PackedMC (either default or the actual instance) to the minecraft directory
    packedmc_options_files_directory = os.path.join(PACKEDMC_MINECRAFT_DATA_DIRECTORY, 'options_files')
    if actual_instance_data['use_default_options_file']:
        packedmc_options_file = os.path.join(packedmc_options_files_directory, default_instance_name + '.txt')
    else:
        packedmc_options_file = os.path.join(packedmc_options_files_directory, instance_name + '.txt')

    # Create the options file path based on the game location of the new instance
    minecraft_options_file_path = os.path.join(actual_instance_data["minecraft_directory"], 'options.txt')

    # Trying to copy the options file of the instance.
    if os.path.exists(packedmc_options_file):
        if not os.path.exists(minecraft_options_file_path):
            logger.info("Options file to replace does not exist. Creating new one.")

        shutil.copy2(packedmc_options_file, minecraft_options_file_path)
        logger.info(f'Loaded options file from "{packedmc_options_file}" to "{minecraft_options_file_path}"')
    # Trying to copy the options file of the default instance.
    else:
        logger.warning(f'Options file not found at "{packedmc_options_file}". Trying to load from the options file from the default PackedMC instance.')
        packedmc_options_file = os.path.join(packedmc_options_files_directory, default_instance_name + '.txt')
        if os.path.exists(packedmc_options_file):
            if not os.path.exists(minecraft_options_file_path):
                logger.info("Options file to replace does not exist. Creating new one.")

            shutil.copy2(packedmc_options_file, minecraft_options_file_path)
            logger.info(f'Loaded options file from default instance from "{packedmc_options_file}" to "{minecraft_options_file_path}"')
        else:
            logger.info("No default instance options file found.")


def write_instance_data_to_profiles_file(instance_name: str, actual_instance_data: _SingleInstanceDictType):
    # Modify the launcher profiles file
    if not os.path.exists(MINECRAFT_LAUNCHER_PROFILES_PATH):
        logger.error("Could not find the Minecraft Launcher profiles file. Probably has the Minecraft Launcher never been started.")
        return

    with open(MINECRAFT_LAUNCHER_PROFILES_PATH, 'r') as f:
        profile_data = json.load(f)

    # Get the time for when the PackedMC profile was created. Either keep the existing value or set it to right now
    if MINECRAFT_LAUNCHER_PACKEDMC_PROFILE_ID in profile_data["profiles"] and profile_data["profiles"][MINECRAFT_LAUNCHER_PACKEDMC_PROFILE_ID].get("created"):

        created_time = profile_data["profiles"][MINECRAFT_LAUNCHER_PACKEDMC_PROFILE_ID]["created"]
    else:
        created_time = datetime.now().isoformat(timespec="milliseconds") + "Z"  # Time in this format: 2026-01-31T20:34:56.183Z

    # Set a default value for the version id
    version_id = actual_instance_data["version"]

    if version_id == "latest":
        version_id = ALL_RELEASE_VERSIONS[0]

    # Replace the version id for special types like fabric or forge
    if actual_instance_data['type'] == "Fabric":
        # Check what the newest fabric version for this Minecraft version is by looking at the directories
        versions_directory = os.path.join(MINECRAFT_DIRECTORY, 'versions')
        for directory_name in sorted(os.listdir(versions_directory), reverse=True):
            if not directory_name.startswith('fabric-loader'):
                continue

            split_name = directory_name.split('-')
            if split_name[-1] == actual_instance_data["version"]:
                version_id = directory_name
                break
        else:  # The for loop did not break, thus the fabric version does not exist. Then it is installed.
            version_id = install_version(versions_directory, minecraft_version=version_id)
            logger.info(f'Installed fabric "{version_id}"')

    # Set the java args
    java_args = ""
    if 'start_heap_size' in actual_instance_data['advanced_arguments']:
        java_args += " -Xms{}G".format(actual_instance_data['advanced_arguments']['start_heap_size'])
    else:
        java_args += " -Xms2G"
    if 'max_heap_size' in actual_instance_data['advanced_arguments']:
        java_args += " -Xmx{}G".format(actual_instance_data['advanced_arguments']['max_heap_size'])
    else:
        java_args += " -Xmx2G"
    if 'other_arguments' in actual_instance_data['advanced_arguments']:
        java_args += " " + actual_instance_data['advanced_arguments']['other_arguments']

    with open(os.path.join(ICONS_FILE_PATH, 'logo64.b64')) as f:
        base64_icon = f.read()

    # Overwrite or add the PackedMC profile with the most recent timestamp.
    profile_data["profiles"][MINECRAFT_LAUNCHER_PACKEDMC_PROFILE_ID] = {
        "created": created_time,
        "gameDir": actual_instance_data["minecraft_directory"],
        "icon": "data:image/png;base64," + base64_icon,
        "javaArgs": java_args,
        "lastUsed": datetime.now().isoformat(timespec="milliseconds") + "Z",  # Time in this format: 2026-01-31T20:34:56.183Z
        "lastVersionId": version_id,
        "name": "PackedMC - " + instance_name,
        "type": "custom"
    }

    # Writeback to the file
    with open(MINECRAFT_LAUNCHER_PROFILES_PATH, 'w') as f:
        json.dump(profile_data, f)


def get_last_played_minecraft_launcher_profile() -> tuple[str, dict[str, str]]:
    """ Returns the last played profile id and data """
    if os.path.exists(MINECRAFT_LAUNCHER_PROFILES_PATH):
        with open(MINECRAFT_LAUNCHER_PROFILES_PATH, 'r') as f:
            profile_data = json.load(f)

            # Find the last played profile
            newest_launch_time = -1
            last_used_profile_id = ''
            for profile_id in profile_data['profiles'].keys():
                # Get the time in seconds
                profile_last_used = profile_data['profiles'][profile_id]['lastUsed']
                profile_launch_time = datetime.fromisoformat(profile_last_used.replace("Z", "+00:00")).timestamp()

                if newest_launch_time < profile_launch_time:
                    newest_launch_time = profile_launch_time
                    last_used_profile_id = profile_id

            return last_used_profile_id, profile_data['profiles'][last_used_profile_id]

    return '', {}
