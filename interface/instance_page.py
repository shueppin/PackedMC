import logging
import json
import psutil
import os
import shutil
from datetime import datetime
import subprocess
import traceback

# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from .utils import AnimationScrollDirection, create_buttons_in_scroll_area, ScrollAreaButtonType
from .file_paths import ICONS_FILE_PATH, PACKEDMC_MINECRAFT_DATA_DIRECTORY, MINECRAFT_DIRECTORY, MINECRAFT_LAUNCHER_PROFILES_PATH

from minecraft_api.minecraft import ALL_RELEASE_VERSIONS, ALL_SNAPSHOT_VERSIONS, get_installed_versions
from minecraft_api.mod import get_mod_icon_path, InvalidModBaseUrl, ModNotExisting
from minecraft_api.fabric import install_version

# Import the MainWindow for Type Checking
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from interface import MainWindow


logger = logging.getLogger(__name__)


DEFAULT_INSTANCE_NAME = 'Latest Release'
MINECRAFT_LAUNCHER_PACKEDMC_PROFILE_ID = 'packedmc'

MINECRAFT_LAUNCHER_APP = r"Microsoft.4297127D64EC6_8wekyb3d8bbwe!Minecraft"


class InstancePageClass:
    def __init__(self, parent: MainWindow):
        self.parent: MainWindow = parent
        self.data = parent.data

        # Create intern variables
        self.selected_instance_name = ''

        # Create the instance edit page
        parent.INSTANCES_BACK_BUTTON.clicked.connect(lambda: self.parent.show_page(0, animation_direction=AnimationScrollDirection.HORIZONTAL))
        parent.BROWSE_MINECRAFT_PATH_BUTTON.clicked.connect(self._set_minecraft_path)
        parent.INSTANCE_NAME.textChanged.connect(self._changed_instance_name)
        parent.DELETE_INSTANCE_BUTTON.clicked.connect(self._delete_instance)
        parent.INSTANCE_TYPE_SELECTION.currentIndexChanged.connect(self._changed_instance_type)
        parent.INSTANCE_VERSION_SELECTION.currentIndexChanged.connect(self._changed_instance_version)
        parent.USE_STANDARD_OPTIONS.clicked.connect(self._changed_instance_use_default_options_file)
        parent.ADVANCED_SETTINGS_BUTTON.clicked.connect(self.open_advanced_instance_popup)

    def import_profiles_from_launcher(self):
        launcher_profiles_path, _ = QFileDialog.getOpenFileName(self.parent, 'Select profiles file for the launcher', MINECRAFT_LAUNCHER_PROFILES_PATH, "JSON Files (*.json);;All Files (*)")

        logger.info(f'Importing profiles from {launcher_profiles_path}')

        try:
            with open(launcher_profiles_path) as file:
                self.parent.imported_launcher_profiles_file_data = json.load(file)

                # Go through all profiles and save the display name and the profile id in a dictionary
                for profile_id, profile_data in self.parent.imported_launcher_profiles_file_data['profiles'].items():
                    try:
                        # Set the profile name and what version (and launcher) it is running as the display name
                        name = profile_data['name']
                        version_id = profile_data['lastVersionId']
                        if name:
                            display = f'{name} (running {version_id})'
                        else:
                            display = version_id

                        if display not in self.parent.all_imported_launcher_profiles.keys():
                            self.parent.all_imported_launcher_profiles[display] = profile_id

                    except KeyError:
                        logger.warning(f'Skipping profile {profile_id} due to faulty profile data')
                        continue

            # If there was no error opening the file, create the checkboxes and display the popup
            create_buttons_in_scroll_area(self.parent.import_profiles_popup.PROFILES_SELECTION_LIST, sorted(self.parent.all_imported_launcher_profiles.keys()), [], lambda *args: None, button_type=ScrollAreaButtonType.CHECKBOX)
            self.parent.import_profiles_popup.show_popup()

        except FileNotFoundError:
            logger.error("Profiles file not found.")
        except json.JSONDecodeError or KeyError:
            logger.error("There has been an error decoding the profiles JSON.")

    def play_instance(self, instance_name: str):
        actual_instance_data = self.data['instances'][instance_name]

        # Check if the Minecraft Launcher is already running
        for proc in psutil.process_iter(['name', 'exe']):
            if proc.info['name'] and "Minecraft" in proc.info['name']:
                QMessageBox.information(self.parent, 'Could not play', f'Found "{proc.info['name']}" running. Please close the Minecraft Launcher and the open Minecraft Instances. \nOtherwise PackedMC can not launch the game correctly.')
                return

        # Save the actual options file from the minecraft directory
        self.save_options_file_of_last_used_instance()

        # Copy the options file from PackedMC (either default or the actual instance) to the minecraft directory
        packedmc_options_files_directory = os.path.join(PACKEDMC_MINECRAFT_DATA_DIRECTORY, 'options_files')
        if actual_instance_data['use_default_options_file']:
            packedmc_options_file = os.path.join(packedmc_options_files_directory, self.get_default_instance_name() + '.txt')
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
            packedmc_options_file = os.path.join(packedmc_options_files_directory, self.get_default_instance_name() + '.txt')
            if os.path.exists(packedmc_options_file):
                if not os.path.exists(minecraft_options_file_path):
                    logger.info("Options file to replace does not exist. Creating new one.")

                shutil.copy2(packedmc_options_file, minecraft_options_file_path)
                logger.info(f'Loaded options file from default instance from "{packedmc_options_file}" to "{minecraft_options_file_path}"')
            else:
                logger.info("No default instance options file found.")

        # Set the last played instance
        self.data['last_played_instance'] = instance_name
        self.data.save()

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

        # Launch the official Launcher from the Microsoft Store
        try:
            subprocess.run(rf'explorer.exe shell:AppsFolder\{MINECRAFT_LAUNCHER_APP}', shell=True)
        except FileNotFoundError:
            logger.error("Could not find the Minecraft Launcher executable.")

        # Update the mods
        self.parent.update_mod_files(instance_name, actual_instance_data['mods'], actual_instance_data["version"], actual_instance_data['type'])
        packedmc_mods_directory = os.path.join(PACKEDMC_MINECRAFT_DATA_DIRECTORY, 'mods', instance_name)

        # Get all the files in the mods directory which were not copied by PackedMC
        try:
            mods_directory = os.path.join(self.data['instances'][instance_name]['minecraft_directory'], 'mods')
            packedmc_copied_mods_file = os.path.join(mods_directory, 'packedmc.json')
            if os.path.exists(packedmc_copied_mods_file):
                with open(packedmc_copied_mods_file, 'r') as f:
                    old_packedmc_copied_files: list[str] = json.load(f)
            else:
                old_packedmc_copied_files = []
            old_packedmc_copied_files.append('packedmc.json')

            with os.scandir(mods_directory) as it:
                actual_mod_files = [entry.name for entry in it if entry.is_file()]

            for filename in old_packedmc_copied_files:
                if filename in actual_mod_files:
                    actual_mod_files.remove(filename)

            # Store all the mods which were not copied by PackedMC in a backup folder
            if len(actual_mod_files) > 0:
                backup_directory_name = 'packedmc_backup_' + datetime.now().isoformat(timespec='seconds').replace('T', '_').replace(':', '-')
                backup_directory = os.path.join(mods_directory, backup_directory_name)
                os.mkdir(backup_directory)
                for filename in actual_mod_files:
                    shutil.move(os.path.join(mods_directory, filename), backup_directory)

            # Remove all the files which are not replaced soon with the files from the PackedMC mods directory
            new_mod_files = os.listdir(packedmc_mods_directory)
            for filename in old_packedmc_copied_files:
                if filename not in new_mod_files:
                    if os.path.exists(os.path.join(mods_directory, filename)):
                        os.remove(os.path.join(mods_directory, filename))

            # Copy all files from the packedmc mods folder to the minecraft mods folder and list them in the JSON file
            for filename in new_mod_files:
                shutil.copy2(os.path.join(packedmc_mods_directory, filename), mods_directory)

            with open(packedmc_copied_mods_file, 'w') as f:
                json.dump(new_mod_files, f)
        except Exception:
            traceback.print_exc()

        # Close PackedMC if the setting is selected
        if self.data['settings']['close_packedmc']:
            logger.info(f'Closing PackedMC')
            exit()

        # TODO: Optionally: Periodically save the options file until the game is closed if packedmc stays open.

    def create_instance(self, instance_name='New instance', is_default=False, edit_afterwards=True, instance_type='Release', instance_version='latest', minecraft_directory=MINECRAFT_DIRECTORY, advanced_arguments: dict = None):
        instance_name = self.parent.make_name_unique(instance_name, list(self.data['instances'].keys()))
        if advanced_arguments is None:
            advanced_arguments = {}

        # Set the data
        # noinspection PyTypeChecker
        self.data['instances'][instance_name] = {
            'type': instance_type,
            'version': instance_version,
            'is_default': is_default,
            'minecraft_directory': minecraft_directory,
            'use_default_options_file': is_default,  # Use default options file for default instance (obviously), otherwise don't
            'advanced_arguments': advanced_arguments,
            'mods': {}
        }
        self.data.save()

        if edit_afterwards:
            self.edit_instance(instance_name)  # Show it in edit mode

    def edit_instance(self, instance_name: str, only_refresh_values=False):
        """ This function is executed to show the edit page and configure the values for the given instance. """
        parent = self.parent

        if not only_refresh_values:
            parent.show_page(1, animation_direction=AnimationScrollDirection.HORIZONTAL)

        # Set the values for the edit page
        self.selected_instance_name = instance_name
        instance_data = self.data['instances'][instance_name]

        # Set the name without triggering the changed_instance_data function (which triggers on text change)
        parent.INSTANCE_NAME.blockSignals(True)
        parent.INSTANCE_NAME.setText(instance_name)
        parent.INSTANCE_NAME.setFocus()  # Prevent highlighting
        parent.INSTANCE_NAME.blockSignals(False)

        # Set the type
        parent.INSTANCE_TYPE_SELECTION.blockSignals(True)
        parent.INSTANCE_TYPE_SELECTION.setCurrentText(instance_data['type'])
        parent.INSTANCE_TYPE_SELECTION.blockSignals(False)

        # Set the versions corresponding to the type
        all_versions = ['latest']
        if instance_data['type'] == 'Release' or instance_data['type'] == 'Fabric' or instance_data['type'] == 'Forge':
            all_versions.extend(ALL_RELEASE_VERSIONS)
        elif instance_data['type'] == 'Snapshot':
            all_versions.extend(ALL_SNAPSHOT_VERSIONS)
        elif instance_data['type'] == 'Other':
            all_versions = get_installed_versions(instance_data['minecraft_directory'])

        parent.INSTANCE_VERSION_SELECTION.blockSignals(True)
        parent.INSTANCE_VERSION_SELECTION.clear()
        parent.INSTANCE_VERSION_SELECTION.addItems(all_versions)
        if instance_data['version'] in all_versions:
            parent.INSTANCE_VERSION_SELECTION.setCurrentText(instance_data['version'])
        else:
            parent.INSTANCE_VERSION_SELECTION.setCurrentText('latest')
        parent.INSTANCE_VERSION_SELECTION.blockSignals(False)

        # Set the standard options button and the minecraft path
        parent.USE_STANDARD_OPTIONS.blockSignals(True)
        parent.USE_STANDARD_OPTIONS.setChecked(instance_data['use_default_options_file'])
        parent.USE_STANDARD_OPTIONS.blockSignals(False)

        parent.MINECRAFT_DIRECTORY_PATH.setText(instance_data['minecraft_directory'])

        # Enable or disable buttons, if we are using the default instance
        if instance_data['is_default']:
            parent.DELETE_INSTANCE_BUTTON.setText('Reset')
            parent.INSTANCE_TYPE_SELECTION.setEnabled(False)
            parent.INSTANCE_VERSION_SELECTION.setEnabled(False)
            parent.USE_STANDARD_OPTIONS.setEnabled(False)
        else:
            parent.DELETE_INSTANCE_BUTTON.setText('Delete')
            parent.INSTANCE_TYPE_SELECTION.setEnabled(True)
            parent.INSTANCE_VERSION_SELECTION.setEnabled(True)
            parent.USE_STANDARD_OPTIONS.setEnabled(True)

        # Display the mods in their correct state
        # TODO: Check which mods are available for this version and which aren't and mark them. Then update the mod data for the ones that aren't.
        mod_display_data = []
        for mod_name in sorted(self.data['mods'].keys()):
            if instance_data['type'] in self.data['mods'][mod_name]['loaders']:
                icon_file_path = ''
                try:
                    icon_file_path = get_mod_icon_path(self.data['mods'][mod_name]['url'])
                except ModNotExisting:
                    pass
                except InvalidModBaseUrl:
                    pass
                except Exception as e:
                    logger.error('Uncaught exception when displaying mod', exc_info=e)

                # Add to the mods the name, the icon path and whether it is selected or not
                mod_display_data.append((
                    mod_name,
                    icon_file_path,
                    mod_name in instance_data['mods']
                ))
        parent.INSTANCE_MODS_DISPLAY.set_values(mod_display_data)

    def _changed_instance_name(self):
        # Get the old and the new instance name
        old_instance_name = self.selected_instance_name
        new_instance_name = self.parent.INSTANCE_NAME.text().strip()

        # If the clean new name is empty then it means it was cleared, which is allowed since the user can rewrite the whole name.
        if new_instance_name == '':
            new_instance_name = 'Instance Name'

        # First get the data and only then make the name unique, to avoid mistakes when the name already exists, because of itself
        instance_data = self.data['instances'].pop(old_instance_name)

        new_instance_name = self.parent.make_name_unique(new_instance_name, list(self.data['instances'].keys()))

        self.data['instances'][new_instance_name] = instance_data
        self.selected_instance_name = new_instance_name

        # Rename the last played instance if needed
        if self.data["last_played_instance"] == old_instance_name:
            self.data["last_played_instance"] = new_instance_name

        self.data.save()

        # Rename the options file in PackedMC if it exists
        packedmc_options_files_directory = os.path.join(PACKEDMC_MINECRAFT_DATA_DIRECTORY, 'options_files')
        old_options_file_path = os.path.join(packedmc_options_files_directory, old_instance_name + '.txt')
        if os.path.exists(old_options_file_path):
            os.rename(old_options_file_path, os.path.join(packedmc_options_files_directory, new_instance_name + '.txt'))
            logger.info(f'Renaming options file at "{old_options_file_path}" to new name "{new_instance_name}.txt"')

    def _set_minecraft_path(self):
        actual_path = self.data['instances'][self.selected_instance_name]['minecraft_directory']

        new_path = QFileDialog.getExistingDirectory(self.parent, 'Select Minecraft Directory', actual_path)

        # Allow only user data paths
        if self.parent.is_subdir_of_user_home(new_path):
            self.data['instances'][self.selected_instance_name]['minecraft_directory'] = new_path
            self.data.save()
            self.parent.MINECRAFT_DIRECTORY_PATH.setText(new_path)  # Refresh the values

    def _delete_instance(self):
        selected_instance = self.selected_instance_name

        # If it is the standard instance then just reset it.
        if self.data['instances'][selected_instance]['is_default']:
            reply = QMessageBox.question(self.parent, 'Confirm resetting', f'''This is the default instance, which can't be deleted. \nDo you really want to reset the instance "{selected_instance}" to its standard values? \n\n(Enter = Yes, Escape = No)''')

            if reply == 16384:  # Yes
                del self.data['instances'][selected_instance]
                self.data.save()

                # Make a unique name here already, to be able to rename the options file
                new_instance_name = self.parent.make_name_unique(DEFAULT_INSTANCE_NAME, list(self.data['instances'].keys()))

                # Rename the options file in PackedMC if it exists
                packedmc_options_files_directory = os.path.join(PACKEDMC_MINECRAFT_DATA_DIRECTORY, 'options_files')
                old_options_file_path = os.path.join(packedmc_options_files_directory, selected_instance + '.txt')
                if os.path.exists(old_options_file_path):
                    os.rename(old_options_file_path, os.path.join(packedmc_options_files_directory, new_instance_name + '.txt'))
                    logger.info(f'Renaming options file at "{old_options_file_path}" to new name "{new_instance_name}.txt"')

                # Create a default instance under the default name
                self.create_instance(new_instance_name, is_default=True)

            return

        # Otherwise just try to delete it
        reply = QMessageBox.question(self.parent, 'Confirm deletion', f'Do you really want to delete the instance "{selected_instance}"? \n\n(Enter = Yes, Escape = No)')

        if reply == 16384:  # Yes
            del self.data['instances'][selected_instance]
            self.data.save()

            # Go to the instances page
            self.parent.show_page(0, animation_direction=AnimationScrollDirection.HORIZONTAL)

    def _changed_instance_type(self, _new_index: int):
        # Ask the user to confirm the type change
        old_type = self.data['instances'][self.selected_instance_name]['type']
        new_type = self.parent.INSTANCE_TYPE_SELECTION.currentText()

        additional_message = ""
        if old_type == 'Fabric' or old_type == 'Forge':
            if new_type == 'Fabric' or new_type == 'Forge':
                additional_message = 'Incompatible mods will be deselected.'
            else:
                additional_message = 'All mods will be deselected.'

        reply = QMessageBox.question(self.parent, 'Confirm Instance Type change', f'Do you really want to change the type of this instance from {old_type} to {new_type}? \n{additional_message} \n\n(Enter = Yes, Escape = No)')

        if reply == 16384:  # Yes
            self.data['instances'][self.selected_instance_name]['type'] = new_type
            # Remove all mods incompatible with the selected type
            for mod_name in self.data['instances'][self.selected_instance_name]['mods'].copy():  # Use a copy of the list
                if new_type not in self.data['mods'][mod_name]['loaders']:
                    del self.data['instances'][self.selected_instance_name]['mods'][mod_name]
            self.data.save()

            self.edit_instance(self.selected_instance_name, only_refresh_values=True)
        else:
            # Reset the type
            self.parent.INSTANCE_TYPE_SELECTION.blockSignals(True)
            self.parent.INSTANCE_TYPE_SELECTION.setCurrentText(old_type)
            self.parent.INSTANCE_TYPE_SELECTION.blockSignals(False)

    def _changed_instance_version(self, _new_index: int):
        version = self.parent.INSTANCE_VERSION_SELECTION.currentText()
        self.data['instances'][self.selected_instance_name]['version'] = version

        # Change the timestamp of all the mods for this instance
        for mod_name in self.data['instances'][self.selected_instance_name]['mods']:
            mod_url, filename, last_checked = self.data['instances'][self.selected_instance_name]['mods'][mod_name]
            self.data['instances'][self.selected_instance_name]['mods'][mod_name] = (mod_url, filename, 0)
        self.data.save()

    def _changed_instance_use_default_options_file(self, new_state: bool):
        self.data['instances'][self.selected_instance_name]['use_default_options_file'] = new_state
        self.data.save()

    def clicked_displayed_mod(self, mod_name: str, is_selected: bool):
        if is_selected:
            self.data['instances'][self.selected_instance_name]['mods'][mod_name] = ('', '', 0)
        else:
            del self.data['instances'][self.selected_instance_name]['mods'][mod_name]
        self.data.save()

    def open_advanced_instance_popup(self):
        # Set the values from the saved data when opening the popup
        arguments = self.data['instances'][self.selected_instance_name]['advanced_arguments']
        if 'start_heap_size' in arguments:
            self.parent.advanced_options_popup.START_HEAP_SIZE.setValue(arguments['start_heap_size'])
        else:
            self.parent.advanced_options_popup.START_HEAP_SIZE.setValue(2)
        if 'max_heap_size' in arguments:
            self.parent.advanced_options_popup.MAX_HEAP_SIZE.setValue(arguments['max_heap_size'])
        else:
            self.parent.advanced_options_popup.MAX_HEAP_SIZE.setValue(2)
        if 'other_arguments' in arguments:
            self.parent.advanced_options_popup.OTHER_ARGUMENTS.setText(arguments['other_arguments'])

        self.parent.advanced_options_popup.show_popup(True)

    def save_options_file_of_last_used_instance(self):
        """Copy the options file of the last used instance to the folder of the corresponding instance. """
        packedmc_options_files_directory = os.path.join(PACKEDMC_MINECRAFT_DATA_DIRECTORY, 'options_files')

        last_played_profile_id, last_played_profile_data = self.parent.get_last_played_minecraft_launcher_profile()

        if last_played_profile_id == MINECRAFT_LAUNCHER_PACKEDMC_PROFILE_ID:
            last_played_instance = self.data['last_played_instance']

            # Either use the default instance or the last played one
            if self.data['instances'][last_played_instance]['use_default_options_file']:
                output_file_path = os.path.join(packedmc_options_files_directory, self.get_default_instance_name() + '.txt')
            else:
                output_file_path = os.path.join(packedmc_options_files_directory, last_played_instance + '.txt')

            # Create the options file path based on the last profile's minecraft directory
            minecraft_options_file_path = os.path.join(self.data['instances'][last_played_instance]["minecraft_directory"], 'options.txt')

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

    def get_default_instance_name(self) -> str:
        # Find the default instance name
        for instance_name in self.data['instances'].keys():
            if self.data['instances'][instance_name]['is_default']:
                return instance_name

        return ''
