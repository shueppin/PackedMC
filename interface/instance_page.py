import logging
import psutil
import os
import traceback

# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from .utils import AnimationScrollDirection
from .file_paths import PACKEDMC_MINECRAFT_DATA_DIRECTORY, MINECRAFT_DIRECTORY, is_subdir_of_user_home
from .minecraft_launcher_integration import save_options_file_of_last_used_instance, load_options_file_from_packedmc, write_instance_data_to_profiles_file, start_official_launcher
from .popups import AdvancedOptionsHandler
from .mod_files_handler import update_mod_files, move_mods_from_packedmc_to_minecraft

from minecraft_api.minecraft import ALL_RELEASE_VERSIONS, ALL_SNAPSHOT_VERSIONS, get_installed_versions
from minecraft_api.mod import get_mod_icon_path, InvalidModBaseUrl, ModNotExisting

# Import the MainWindow for Type Checking
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from interface import MainWindow


logger = logging.getLogger(__name__)


DEFAULT_INSTANCE_NAME = 'Latest Release'


class InstancePageClass:
    def __init__(self, parent: MainWindow):
        self.parent: MainWindow = parent
        self.data = parent.data

        # Create intern variables
        self.selected_instance_name = ''

        # Create the advanced options popup
        self.advanced_options_popup_handler = AdvancedOptionsHandler(parent)

        # Create the instance edit page
        parent.INSTANCES_BACK_BUTTON.clicked.connect(lambda: self.parent.show_page(0, animation_direction=AnimationScrollDirection.HORIZONTAL))
        parent.BROWSE_MINECRAFT_PATH_BUTTON.clicked.connect(self._set_minecraft_path)
        parent.INSTANCE_NAME.textChanged.connect(self._changed_instance_name)
        parent.DELETE_INSTANCE_BUTTON.clicked.connect(self._delete_instance)
        parent.INSTANCE_TYPE_SELECTION.currentIndexChanged.connect(self._changed_instance_type)
        parent.INSTANCE_VERSION_SELECTION.currentIndexChanged.connect(self._changed_instance_version)
        parent.USE_STANDARD_OPTIONS.clicked.connect(self._changed_instance_use_default_options_file)
        parent.ADVANCED_SETTINGS_BUTTON.clicked.connect(self.advanced_options_popup_handler.open_popup)

    def play_instance(self, instance_name: str):
        actual_instance_data = self.data['instances'][instance_name]

        # Check if the Minecraft Launcher is already running
        for proc in psutil.process_iter(['name', 'exe']):
            if proc.info['name'] and "Minecraft" in proc.info['name']:
                QMessageBox.warning(self.parent, 'Could not play', f'Found "{proc.info['name']}" running. Please close the Minecraft Launcher and the open Minecraft Instances. \nOtherwise PackedMC can not launch the game correctly. \nIf you are unable to close the Launcher normally, try closing it via the Task Manager.')
                return

        # Check if the minecraft directory is valid
        minecraft_directory = self.data['instances'][instance_name]['minecraft_directory']
        if not is_subdir_of_user_home(minecraft_directory) or not os.path.isdir(minecraft_directory):
            QMessageBox.warning(self.parent, 'Could not play', f'A correct Minecraft directory could not be found. \nPlease use a directory that exists and is inside your home folder.')
            return

        # Save the actual options file from the minecraft directory
        last_played_instance = self.data['last_played_instance']
        save_options_file_of_last_used_instance(last_played_instance, self.data['instances'][last_played_instance], self.get_default_instance_name())

        # Load the instance file from packedmc for the selected instance
        load_options_file_from_packedmc(instance_name, actual_instance_data, self.get_default_instance_name())

        # Set the last played instance
        self.data['last_played_instance'] = instance_name
        self.data.save()

        # Create a profile in the official Minecraft Launcher with the correct data and then start it
        write_instance_data_to_profiles_file(instance_name, actual_instance_data)
        start_official_launcher()

        try:
            # Update and download the mods
            update_mod_files(self.parent, instance_name, actual_instance_data['mods'], actual_instance_data["version"], actual_instance_data['type'])

            # Move the mods to the minecraft folder
            move_mods_from_packedmc_to_minecraft(instance_name, minecraft_directory)

            # Close PackedMC if the setting is selected
            if self.data['settings']['close_packedmc']:
                logger.info(f'Closing PackedMC')
                exit()
        except Exception:
            traceback.print_exc()

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

        # Allow only user data paths which actually exist
        if is_subdir_of_user_home(new_path) and os.path.exists(new_path):
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

    def get_default_instance_name(self) -> str:
        # Find the default instance name
        for instance_name in self.data['instances'].keys():
            if self.data['instances'][instance_name]['is_default']:
                return instance_name

        return ''
