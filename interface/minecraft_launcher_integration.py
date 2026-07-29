import os
import json
from datetime import datetime
import logging
import shutil

# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QCheckBox, QFileDialog

from .file_paths import PACKEDMC_MINECRAFT_DATA_DIRECTORY, MINECRAFT_DIRECTORY, MINECRAFT_LAUNCHER_PROFILES_PATH, ICONS_FILE_PATH
from .utils import create_buttons_in_scroll_area, ScrollAreaButtonType

from minecraft_api.minecraft import ALL_RELEASE_VERSIONS, ALL_SNAPSHOT_VERSIONS
from minecraft_api.fabric import install_version

# Import the MainWindow for Type Checking
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from interface import MainWindow


logger = logging.getLogger(__name__)


MINECRAFT_LAUNCHER_PACKEDMC_PROFILE_ID = 'packedmc'

MINECRAFT_LAUNCHER_APP = r"Microsoft.4297127D64EC6_8wekyb3d8bbwe!Minecraft"


class MinecraftLauncherIntegration:
    def __init__(self, window: MainWindow):
        self.window = window

    def configure_profile_import_popup(self):
        launcher_profiles_path, _ = QFileDialog.getOpenFileName(self.window, 'Select profiles file for the launcher', MINECRAFT_LAUNCHER_PROFILES_PATH, "JSON Files (*.json);;All Files (*)")

        logger.info(f'Importing profiles from {launcher_profiles_path}')

        try:
            with open(launcher_profiles_path) as file:
                self.window.imported_launcher_profiles_file_data = json.load(file)

                # Go through all profiles and save the display name and the profile id in a dictionary
                for profile_id, profile_data in self.window.imported_launcher_profiles_file_data['profiles'].items():
                    try:
                        # Set the profile name and what version (and launcher) it is running as the display name
                        name = profile_data['name']
                        version_id = profile_data['lastVersionId']
                        if name:
                            display = f'{name} (running {version_id})'
                        else:
                            display = version_id

                        if display not in self.window.all_imported_launcher_profiles.keys():
                            self.window.all_imported_launcher_profiles[display] = profile_id

                    except KeyError:
                        logger.warning(f'Skipping profile {profile_id} due to faulty profile data')
                        continue

            # If there was no error opening the file, create the checkboxes and display the popup
            create_buttons_in_scroll_area(self.window.import_profiles_popup.PROFILES_SELECTION_LIST, sorted(self.window.all_imported_launcher_profiles.keys()), [], lambda *args: None, button_type=ScrollAreaButtonType.CHECKBOX)
            self.window.import_profiles_popup.show_popup()

        except FileNotFoundError:
            logger.error("Profiles file not found.")
        except json.JSONDecodeError or KeyError:
            logger.error("There has been an error decoding the profiles JSON.")

    def import_selected_profiles(self):
        """
        Gets all selected profiles from the import_profiles_popup and creates an instance for them
        """
        # Go through all the selected profiles and create the data for them
        profile_checkbox_widget: QCheckBox
        for profile_checkbox_widget in self.window.import_profiles_popup.PROFILES_SELECTION_LIST.findChildren(QCheckBox):
            display_name = profile_checkbox_widget.text()

            if not profile_checkbox_widget.isChecked():
                continue

            # If it is checked get the profile ID from the display name and then the all the data
            profile_id = self.window.all_imported_launcher_profiles[display_name]
            profile_data = self.window.imported_launcher_profiles_file_data['profiles'][profile_id]

            # Define the instance name and remove the duplicates
            if profile_data['name']:
                original_instance_name = profile_data['name'].strip()
            else:
                original_instance_name = display_name.strip()

            instance_name = self.window.make_name_unique(original_instance_name, list(self.window.data['instances'].keys()))

            # Find out what type of instance it is
            if profile_data['lastVersionId'].startswith('latest'):
                instance_type = profile_data['lastVersionId'].replace('latest-', '').title()
            elif profile_data['lastVersionId'] in ALL_RELEASE_VERSIONS:
                instance_type = 'Release'
            elif profile_data['lastVersionId'] in ALL_SNAPSHOT_VERSIONS:
                instance_type = 'Snapshot'
            elif 'fabric' in profile_data['lastVersionId']:
                instance_type = 'Fabric'
            elif 'forge' in profile_data['lastVersionId']:
                instance_type = 'Forge'
            else:
                instance_type = 'Other'

            # Set the version depending on the type of the instance
            if 'latest' in profile_data['lastVersionId']:
                instance_version = 'latest'
            elif instance_type == 'Release' or instance_type == 'Latest':
                instance_version = profile_data['lastVersionId']
            elif instance_type == 'Fabric':
                instance_version = profile_data['lastVersionId'].split('-')[-1]
            elif instance_type == 'Forge':
                instance_version = profile_data['lastVersionId'].split('-')[0]
            else:
                instance_version = profile_data['lastVersionId']

            # Get the game directory and advanced java arguments
            if 'gameDir' in profile_data:
                minecraft_directory = profile_data['gameDir']
            else:
                minecraft_directory = MINECRAFT_DIRECTORY

            advanced_arguments = {}

            # Get the java path
            if 'javaDir' in profile_data:
                advanced_arguments['java.path'] = profile_data['javaDir']

            other_arguments = []
            # Go through all the java arguments and put them in a picomc format
            if 'javaArgs' in profile_data:
                java_arguments = profile_data['javaArgs'].split(' ')

                for argument in java_arguments:
                    if argument.startswith('-Xms'):
                        advanced_arguments['start_heap_size'] = argument.replace('-Xms', '').replace('G', '')
                    elif argument.startswith('-Xmx'):
                        advanced_arguments['max_heap_size'] = argument.replace('-Xmx', '').replace('G', '')
                    else:
                        other_arguments.append(argument)

            if other_arguments:
                advanced_arguments['other_arguments'] = other_arguments

            self.window.instance_page_class.create_instance(instance_name, edit_afterwards=False, instance_type=instance_type, instance_version=instance_version, minecraft_directory=minecraft_directory, advanced_arguments=advanced_arguments)

        # After all profiles were added refresh the list and close the dialog
        self.window.show_page(0, show_instantly=True)
        self.window.import_profiles_popup.close()

    def save_options_file_of_last_used_instance(self):
        """Copy the options file of the last used instance to the folder of the corresponding instance. """
        packedmc_options_files_directory = os.path.join(PACKEDMC_MINECRAFT_DATA_DIRECTORY, 'options_files')

        last_played_profile_id, last_played_profile_data = get_last_played_minecraft_launcher_profile()

        if last_played_profile_id == MINECRAFT_LAUNCHER_PACKEDMC_PROFILE_ID:
            last_played_instance = self.window.data['last_played_instance']

            # Either use the default instance or the last played one
            if self.window.data['instances'][last_played_instance]['use_default_options_file']:
                output_file_path = os.path.join(packedmc_options_files_directory, self.window.instance_page_class.get_default_instance_name() + '.txt')
            else:
                output_file_path = os.path.join(packedmc_options_files_directory, last_played_instance + '.txt')

            # Create the options file path based on the last profile's minecraft directory
            minecraft_options_file_path = os.path.join(self.window.data['instances'][last_played_instance]["minecraft_directory"], 'options.txt')

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

    def load_options_file_from_packedmc(self, instance_name: str):
        actual_instance_data = self.window.data['instances'][instance_name]

        # Copy the options file from PackedMC (either default or the actual instance) to the minecraft directory
        packedmc_options_files_directory = os.path.join(PACKEDMC_MINECRAFT_DATA_DIRECTORY, 'options_files')
        if actual_instance_data['use_default_options_file']:
            packedmc_options_file = os.path.join(packedmc_options_files_directory, self.window.instance_page_class.get_default_instance_name() + '.txt')
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
            packedmc_options_file = os.path.join(packedmc_options_files_directory, self.window.instance_page_class.get_default_instance_name() + '.txt')
            if os.path.exists(packedmc_options_file):
                if not os.path.exists(minecraft_options_file_path):
                    logger.info("Options file to replace does not exist. Creating new one.")

                shutil.copy2(packedmc_options_file, minecraft_options_file_path)
                logger.info(f'Loaded options file from default instance from "{packedmc_options_file}" to "{minecraft_options_file_path}"')
            else:
                logger.info("No default instance options file found.")

    def write_instance_data_to_profiles_file(self, instance_name: str):
        actual_instance_data = self.window.data['instances'][instance_name]

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
