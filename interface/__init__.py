import logging
import os
import shutil
from platform import platform
import json
import traceback
import requests
import validators
import psutil
from datetime import datetime
import re
import time

# noinspection PyPackageRequirements
from PyQt6 import uic
# noinspection PyPackageRequirements
from PyQt6.QtCore import QTimer, QObject, pyqtSignal
# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QMainWindow, QPushButton, QFileDialog, QMessageBox, QCheckBox, QVBoxLayout
from qt_material import apply_stylesheet, list_themes, get_theme, opacity

from .type_hinting import MainWindowElements, DataDictType
from .dynamic_widgets import FieldType, ScrollableGrid, InstanceFieldFunctions, ModFieldFunctions
from .utils import StoredDict, animate_transition, AnimationScrollDirection, create_buttons_in_scroll_area, ScrollAreaButtonType
from .popups import ImportProfilesPopup

from minecraft_api.minecraft import ALL_RELEASE_VERSIONS, ALL_SNAPSHOT_VERSIONS, get_installed_versions
from minecraft_api.mod import get_mod_data, get_mod_icon_path, InvalidModBaseUrl, ModNotExisting, get_download_url, NoModFileAvailable, APICooldown, TryAgainLater
from minecraft_api.fabric import install_version


logger = logging.getLogger(__name__)


ACTUAL_FILE_DIRECTORY = os.path.dirname(__file__)

INTERFACE_FILE_PATH = os.path.join(ACTUAL_FILE_DIRECTORY, 'ui_files/interface.ui')
CUSTOM_STYLESHEET_FILE_PATH = os.path.join(ACTUAL_FILE_DIRECTORY, 'special_properties.cqss')
WINDOW_DEFAULT_SCALE = 3

DEFAULT_DATA_FILE_PATH = os.path.join(ACTUAL_FILE_DIRECTORY, r'../data.json')
PACKEDMC_MINECRAFT_DATA_DIRECTORY = os.path.abspath(os.path.join(ACTUAL_FILE_DIRECTORY, '../minecraft_data'))
DEFAULT_DATA = {
    # For the style of the App
    'style': {
        'theme': 'dark_lightgreen.xml',
        'invert_secondary': False,
        'scale': 0
    },
    'last_played_instance': '',
    'instances': {},
    'mods': {}
}

if 'windows' in platform().lower():
    ROAMING_DIRECTORY = os.getenv('Appdata')
    MINECRAFT_DIRECTORY = os.path.join(ROAMING_DIRECTORY, '.minecraft')
    MINECRAFT_LAUNCHER_PROFILES_PATH = os.path.join(MINECRAFT_DIRECTORY, 'launcher_profiles.json')
    MINECRAFT_LAUNCHER_EXECUTABLE = r"C:\Program Files\WindowsApps\Microsoft.4297127D64EC6_2.6.2.0_x64__8wekyb3d8bbwe\Minecraft.exe"  # TODO: Find the correct path via bruteforce. Sometimes the version number (here 2.6.2.0) changes
else:
    MINECRAFT_DIRECTORY = 'UNKNOWN'

DEFAULT_INSTANCE_NAME = 'Latest Release'
MINECRAFT_LAUNCHER_PACKEDMC_PROFILE_ID = 'packedmc'

# This is the amount of seconds it should wait before checking something like the mod data or the mod download url again.
SKIP_WHEN_LAST_CHECKED_BEFORE = 600


# Ensure correct directories exist
os.makedirs(os.path.join(PACKEDMC_MINECRAFT_DATA_DIRECTORY, 'options_files'), exist_ok=True)  # creates all missing parents; no error if exists


# Signal Emitter for when the data of a mod was loaded from the API
class ModDataConnector(QObject):
    updated = pyqtSignal(str, list, list, str, str)  # declared on class

    def emit_updated(self, description: str, loaders: list[str], supported_versions: list[str], mod_name: str, mod_url: str):
        # noinspection PyUnresolvedReferences
        self.updated.emit(description, loaders, supported_versions, mod_name, mod_url)


class MainWindow(QMainWindow, MainWindowElements):
    def __init__(self, application):
        super().__init__()
        uic.loadUi(INTERFACE_FILE_PATH, self)  # Load UI

        # Non-UI elements
        self.data: DataDictType = StoredDict(DEFAULT_DATA_FILE_PATH, DEFAULT_DATA)  # Initialize using Default Data as base
        self.application = application
        self.possible_stylesheet_file_names = list_themes()
        self.selected_instance_name = ''
        self.all_imported_launcher_profiles = {}
        self.imported_launcher_profiles_file_data = {}
        self.selected_mod_name = ''

        # Set general, but more complex variables
        instance_field_functions = InstanceFieldFunctions(self.play_instance, self.edit_instance, self.create_instance, self.import_profiles_from_launcher)
        mod_field_functions = ModFieldFunctions(self.edit_mod, self.create_mod, self.clicked_displayed_mod)

        self.import_profiles_popup = ImportProfilesPopup(self)
        self.import_profiles_popup.IMPORT_BUTTON.clicked.connect(self._import_selected_profiles)

        self.mod_url_timer = QTimer(self)  # Use a timer that is restarted on every text input, but the real function is only executed after the time has run out.
        self.mod_url_timer.setSingleShot(True)
        self.mod_url_timer.timeout.connect(self._changed_mod_url)  # noqa
        self.mod_data_connector = ModDataConnector()
        # noinspection PyUnresolvedReferences
        self.mod_data_connector.updated.connect(lambda description, loaders, supported_versions, mod_name, mod_url: self.set_mod_values(description, loaders, supported_versions, mod_name, mod_url))

        # Bind the page selection buttons
        self.INSTANCES_PAGE_BUTTON.pressed.connect(lambda: self._page_selection_button_on_press(self.INSTANCES_PAGE_BUTTON, 0))
        self.INSTANCES_PAGE_BUTTON.released.connect(lambda: self._page_selection_button_on_release(self.INSTANCES_PAGE_BUTTON))
        self.MODS_PAGE_BUTTON.pressed.connect(lambda: self._page_selection_button_on_press(self.MODS_PAGE_BUTTON, 2))
        self.MODS_PAGE_BUTTON.released.connect(lambda: self._page_selection_button_on_release(self.MODS_PAGE_BUTTON))
        self.SETTINGS_PAGE_BUTTON.pressed.connect(lambda: self._page_selection_button_on_press(self.SETTINGS_PAGE_BUTTON, 4))
        self.SETTINGS_PAGE_BUTTON.released.connect(lambda: self._page_selection_button_on_release(self.SETTINGS_PAGE_BUTTON))

        # Create the scrollable grid for the instance selection and insert it where the placeholder was
        self.INSTANCES_PAGE = ScrollableGrid(FieldType.INSTANCES, instance_field_functions)
        index = self.PAGE_CONTAINER.indexOf(self.INSTANCES_PAGE_PLACEHOLDER)
        self.PAGE_CONTAINER.removeWidget(self.INSTANCES_PAGE_PLACEHOLDER)  # remove placeholder
        self.PAGE_CONTAINER.insertWidget(index, self.INSTANCES_PAGE)  # insert new page at same position
        self.INSTANCES_PAGE_PLACEHOLDER.deleteLater()  # Cleanup

        # Create the scrollable grid for the mod selection and insert it where the placeholder was
        self.MODS_PAGE = ScrollableGrid(FieldType.MODS_EDITABLE, mod_field_functions)
        index = self.PAGE_CONTAINER.indexOf(self.MODS_PAGE_PLACEHOLDER)
        self.PAGE_CONTAINER.removeWidget(self.MODS_PAGE_PLACEHOLDER)  # remove placeholder
        self.PAGE_CONTAINER.insertWidget(index, self.MODS_PAGE)  # insert new page at same position
        self.MODS_PAGE_PLACEHOLDER.deleteLater()  # Cleanup

        # Create the instance edit page
        self.INSTANCES_BACK_BUTTON.clicked.connect(lambda: self.show_page(0, animation_direction=AnimationScrollDirection.HORIZONTAL))
        self.BROWSE_MINECRAFT_PATH_BUTTON.clicked.connect(self._set_minecraft_path)
        self.INSTANCE_NAME.textChanged.connect(self._changed_instance_name)
        self.DELETE_INSTANCE_BUTTON.clicked.connect(self._delete_instance)
        self.INSTANCE_TYPE_SELECTION.currentIndexChanged.connect(self._changed_instance_type)
        self.INSTANCE_VERSION_SELECTION.currentIndexChanged.connect(self._changed_instance_version)
        self.USE_STANDARD_OPTIONS.clicked.connect(self._changed_instance_use_default_options_file)
        # TODO: Connect advanced options button

        # Add a layout to the Instances Mod Container and add the scrollable grid to it
        layout = QVBoxLayout(self.INSTANCE_MODS_DISPLAY_CONTAINER)
        layout.setContentsMargins(0, 0, 0, 0)  # Remove padding around edges
        layout.setSpacing(0)  # Remove spacing between items
        self.INSTANCE_MODS_DISPLAY = ScrollableGrid(FieldType.MODS_DISPLAYED, mod_field_functions)
        layout.addWidget(self.INSTANCE_MODS_DISPLAY)
        self.INSTANCE_MODS_DISPLAY_CONTAINER.setLayout(layout)

        # Create the mod edit page
        self.MODS_BACK_BUTTON.clicked.connect(lambda: self.show_page(2, animation_direction=AnimationScrollDirection.HORIZONTAL))
        self.MOD_NAME.textChanged.connect(self._changed_mod_name)
        self.MOD_URL.textChanged.connect(lambda: self.mod_url_timer.start(500))
        self.DELETE_MOD_BUTTON.clicked.connect(self._delete_mod)

        # If there are no instance, create the default one
        if not self.data['instances']:
            self.create_instance(DEFAULT_INSTANCE_NAME, is_default=True, edit_afterwards=False)

        # Create the settings page
        available_stylesheet_filenames = self.possible_stylesheet_file_names
        all_style_names = []
        for filename in available_stylesheet_filenames:
            style_name = filename.replace('.xml', '').replace('500', '2').replace('_', ' ').title()  # Changes the name from light_green_500.xml to Light Green 2
            all_style_names.append(style_name)

        selected_style = self.data['style']['theme'].replace('.xml', '').replace('500', '2').replace('_', ' ').title()

        create_buttons_in_scroll_area(self.STYLES_SELECTION_LIST, all_style_names, selected_style, self._stylesheet_selection)
        self.SWITCH_SECONDARY_COLOR.setChecked(self.data['style']['invert_secondary'])
        self.SWITCH_SECONDARY_COLOR.clicked.connect(self._style_invert_button_clicked)
        self.SCALE_SELECTION.setValue(self.data['style']['scale']+WINDOW_DEFAULT_SCALE)
        self.SCALE_SELECTION.valueChanged.connect(self._style_scale_changed)

        # Show the initial page instantly and refresh whole window again
        self.show_page(0, show_instantly=True)

        self._style_scale_changed(self.data['style']['scale'] + WINDOW_DEFAULT_SCALE)  # Use this to also resize the fields

        self.INSTANCES_PAGE.rebuild_grid()

        # Save the actual options file from the minecraft directory
        self.save_options_file_of_last_used_instance()

        # TODO: Download all the mod data

    '''
    Main Page
    '''
    # Press function for the page selection button
    def _page_selection_button_on_press(self, clicked_button: QPushButton, new_page_index: int):
        old_index = self.PAGE_CONTAINER.currentIndex()

        # Set the old button. Page 1 is the instance edit page and page 3 is the mod edit page, thus they have the same selection button.
        if old_index == 0 or old_index == 1:
            old_button = self.INSTANCES_PAGE_BUTTON
        elif old_index == 2 or old_index == 3:
            old_button = self.MODS_PAGE_BUTTON
        elif old_index == 4:
            old_button = self.SETTINGS_PAGE_BUTTON
        else:
            return

        # Set the animation direction. Different "types" are changed vertically (using selection button) but the edit windows are changed horizontally
        if old_index == 0 and new_page_index == 1:
            animation_direction = AnimationScrollDirection.HORIZONTAL
        elif old_index == 1 and new_page_index == 0:
            animation_direction = AnimationScrollDirection.HORIZONTAL
        elif old_index == 2 and new_page_index == 3:
            animation_direction = AnimationScrollDirection.HORIZONTAL
        elif old_index == 3 and new_page_index == 2:
            animation_direction = AnimationScrollDirection.HORIZONTAL
        else:
            animation_direction = AnimationScrollDirection.VERTICAL

        # Check whether the page container is still animating, and if so exit the function
        if hasattr(self.PAGE_CONTAINER, 'is_animating'):
            if self.PAGE_CONTAINER.is_animating:
                return

        # Uncheck the old button
        old_button.setChecked(False)
        old_button.selected = False

        # Check the new button
        clicked_button.setChecked(True)
        clicked_button.selected = True

        self.show_page(new_page_index, animation_direction)

    # Release function for the selection button
    @staticmethod
    def _page_selection_button_on_release(clicked_button: QPushButton):
        # Test if the released button is selected. If it is then just check it again and if it isn't then uncheck it
        if hasattr(clicked_button, 'selected'):
            if clicked_button.selected:
                clicked_button.setChecked(True)
                return

        # Else:
        clicked_button.setChecked(False)

    def show_page(self, page_index: int, animation_direction: AnimationScrollDirection = AnimationScrollDirection.VERTICAL, show_instantly=False):
        # We don't care whether the page is still animating, because it doesn't matter if we execute the page function anyway.
        if show_instantly:
            animate_transition(self, self.PAGE_CONTAINER, page_index, animation_direction=animation_direction, animation_duration=0)
        else:
            animate_transition(self, self.PAGE_CONTAINER, page_index, animation_direction=animation_direction)

        # Page specific functions
        if page_index == 0:
            self.INSTANCES_PAGE.set_values(sorted(self.data['instances'].keys(), key=lambda x: x.lower()))
        elif page_index == 2:
            mod_page_values = []
            for mod_name in sorted(self.data['mods'].keys(), key=lambda x: x.lower()):
                icon_file_path = ''
                try:
                    icon_file_path = get_mod_icon_path(self.data['mods'][mod_name]['url'])
                except ModNotExisting:
                    pass
                except InvalidModBaseUrl:
                    pass
                except Exception as e:
                    logger.error('Uncaught exception when listing mod', exc_info=e)
                mod_page_values.append((mod_name, icon_file_path))  # It is important to add these as a tuple

            self.MODS_PAGE.set_values(mod_page_values)

    '''
    Instance page & Instance Edit page
    '''
    def import_profiles_from_launcher(self):
        launcher_profiles_path, _ = QFileDialog.getOpenFileName(self, 'Select profiles file for the launcher', MINECRAFT_LAUNCHER_PROFILES_PATH, "JSON Files (*.json);;All Files (*)")

        logger.info(f'Importing profiles from {launcher_profiles_path}')

        try:
            with open(launcher_profiles_path) as file:
                self.imported_launcher_profiles_file_data = json.load(file)

                # Go through all profiles and save the display name and the profile id in a dictionary
                for profile_id, profile_data in self.imported_launcher_profiles_file_data['profiles'].items():
                    try:
                        # Set the profile name and what version (and launcher) it is running as the display name
                        name = profile_data['name']
                        version_id = profile_data['lastVersionId']
                        if name:
                            display = f'{name} (running {version_id})'
                        else:
                            display = version_id

                        if display not in self.all_imported_launcher_profiles.keys():
                            self.all_imported_launcher_profiles[display] = profile_id

                    except KeyError:
                        logger.warning(f'Skipping profile {profile_id} due to faulty profile data')
                        continue

            # If there was no error opening the file, create the checkboxes and display the popup
            create_buttons_in_scroll_area(self.import_profiles_popup.PROFILES_SELECTION_LIST, sorted(self.all_imported_launcher_profiles.keys()), [], lambda *args: None, button_type=ScrollAreaButtonType.CHECKBOX)
            self.import_profiles_popup.show_popup()

        except FileNotFoundError:
            logger.error("Profiles file not found.")
        except json.JSONDecodeError or KeyError:
            logger.error("There has been an error decoding the profiles JSON.")

    def _import_selected_profiles(self):
        # Go through all the selected profiles and create the data for them
        profile_checkbox_widget: QCheckBox  # Type hint
        for profile_checkbox_widget in self.import_profiles_popup.PROFILES_SELECTION_LIST.findChildren(QCheckBox):
            display_name = profile_checkbox_widget.text()

            if not profile_checkbox_widget.isChecked():
                continue

            # If it is checked get the profile ID from the display name and then the all the data
            profile_id = self.all_imported_launcher_profiles[display_name]
            profile_data = self.imported_launcher_profiles_file_data['profiles'][profile_id]

            # Define the instance name and remove the duplicates
            if profile_data['name']:
                original_instance_name = profile_data['name'].strip()
            else:
                original_instance_name = display_name.strip()

            instance_name = self._make_name_unique(original_instance_name, list(self.data['instances'].keys()))

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

            # Go through all the java arguments and put them in a picomc format
            if 'javaArgs' in profile_data:
                java_arguments = profile_data['javaArgs'].split(' ')

                for argument in java_arguments:
                    if argument.startswith('-Xms'):
                        advanced_arguments['java.memory.min'] = argument.replace('-Xms', '')
                    elif argument.startswith('-Xmx'):
                        advanced_arguments['java.memory.max'] = argument.replace('-Xmx', '')
                    else:
                        if 'java.jvmargs' in advanced_arguments:
                            advanced_arguments['java.jvmargs'].append(argument)
                        else:
                            advanced_arguments['java.jvmargs'] = [argument]

            self.create_instance(instance_name, edit_afterwards=False, instance_type=instance_type, instance_version=instance_version, minecraft_directory=minecraft_directory, advanced_arguments=advanced_arguments)

        # After all profiles were added refresh the list and close the dialog
        self.show_page(0, show_instantly=True)
        self.import_profiles_popup.close()

    def play_instance(self, instance_name: str):
        actual_instance_data = self.data['instances'][instance_name]

        for proc in psutil.process_iter(['name', 'exe']):
            if proc.info['name'] and "Minecraft" in proc.info['name']:
                QMessageBox.information(self, 'Could not play', f'Found "{proc.info['name']}" running. Please close the Minecraft Launcher and the open Minecraft Instances. \nOtherwise PackedMC can not launch the game correctly.')
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

        # Overwrite or add the PackedMC profile with the most recent timestamp.
        profile_data["profiles"][MINECRAFT_LAUNCHER_PACKEDMC_PROFILE_ID] = {
            "created": created_time,
            "gameDir": actual_instance_data["minecraft_directory"],
            "icon": "Chest",  # TODO: Replace with the icon of PackedMC
            # TODO: Set the java Args
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
            os.startfile(MINECRAFT_LAUNCHER_EXECUTABLE)
        except FileNotFoundError:
            logger.error("Could not find the Minecraft Launcher executable.")

        # Go through all mods and check if try to get their download links (if they were not just checked recently). Then download the files if they don't already exist.
        mc_version = actual_instance_data["version"]
        loader = actual_instance_data['type']
        actual_time = round(time.time())

        packedmc_mods_directory = os.path.join(PACKEDMC_MINECRAFT_DATA_DIRECTORY, 'mods', instance_name)
        os.makedirs(packedmc_mods_directory, exist_ok=True)  # Ensure it exists
        unneeded_files = os.listdir(packedmc_mods_directory)

        for mod_name in actual_instance_data['mods']:
            try:
                old_download_url, old_filename, last_checked = actual_instance_data['mods'][mod_name]
            except Exception as e:  # If there is a mistake in the data, then update it and use default values
                print(e)
                self.data['instances'][instance_name]['mods'][mod_name] = ('', '', 0)
                self.data.save()
                old_download_url, old_filename, last_checked = ('', '', 0)

            # Skip when it was last checked before our waiting interval
            if actual_time < last_checked + SKIP_WHEN_LAST_CHECKED_BEFORE:
                # Remove the old filename from the unneeded files, so it is not removed. Because it is just skipped.
                if old_filename in unneeded_files:
                    unneeded_files.remove(old_filename)
                continue

            try:
                download_url, filename = get_download_url(self.data['mods'][mod_name]['url'], mc_version, loader)
                self.data['instances'][instance_name]['mods'][mod_name] = (download_url, filename, actual_time)

                # If the version is not already in the supported versions, then add it.
                if mc_version not in self.data['mods'][mod_name]['supported_versions']:
                    self.data['mods'][mod_name]['supported_versions'].append(mc_version)
                self.data.save()

                # If the download url has changed or the file does not exist, then download the file
                file_path = os.path.join(packedmc_mods_directory, filename)
                if not os.path.exists(file_path) or old_download_url != download_url:
                    response = requests.get(download_url)
                    file_data = response.content
                    with open(file_path, 'wb') as f:
                        f.write(file_data)
                    print(file_path)

                # Remove the filename from the unneeded files, so it is not removed.
                if filename in unneeded_files:
                    unneeded_files.remove(filename)
            except (InvalidModBaseUrl, NoModFileAvailable):
                # Mod unavailable, thus no possible download URL
                logger.info(f'No mod files found for mod "{mod_name}" for "{loader} {mc_version}"')
                self.data['instances'][instance_name]['mods'][mod_name] = ('', '', last_checked)
                self.data.save()
            except (APICooldown, TryAgainLater):
                # Just do nothing. It will be tried again when playing this instance again.
                pass
            except Exception:
                traceback.print_exc()

        try:
            # Delete all unneeded files (either from removed mods, or old versions of a mod)
            for unneeded_filename in unneeded_files:
                os.remove(os.path.join(packedmc_mods_directory, unneeded_filename))

            # Get all the files in the directory which were not copied by PackedMC
            mods_directory = os.path.join(MINECRAFT_DIRECTORY, 'mods')
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

        # TODO: Optionally: Update other mods in the background and also periodically save the options file until the game is closed.
        # TODO: Optionally: Close PackedMC

    def create_instance(self, instance_name='New instance', is_default=False, edit_afterwards=True, instance_type='Release', instance_version='latest', minecraft_directory=MINECRAFT_DIRECTORY, advanced_arguments: dict = None):
        instance_name = self._make_name_unique(instance_name, list(self.data['instances'].keys()))
        if advanced_arguments is None:
            advanced_arguments = {}

        # Set the data
        self.data['instances'][instance_name] = {
            'type': instance_type,
            'version': instance_version,
            'is_default': is_default,
            'minecraft_directory': minecraft_directory,
            'use_default_options_file': is_default,  # Use default options file for default instance (obviously), otherwise don't
            'advanced_arguments': advanced_arguments,
            'mods': []
        }
        self.data.save()

        if edit_afterwards:
            self.edit_instance(instance_name)  # Show it in edit mode

    def edit_instance(self, instance_name: str, only_refresh_values=False):
        """ This function is executed to show the edit page and configure the values for the given instance. """
        if not only_refresh_values:
            self.show_page(1, animation_direction=AnimationScrollDirection.HORIZONTAL)

        # Set the values for the edit page
        self.selected_instance_name = instance_name
        instance_data = self.data['instances'][instance_name]

        # Set the name without triggering the changed_instance_data function (which triggers on text change)
        self.INSTANCE_NAME.blockSignals(True)
        self.INSTANCE_NAME.setText(instance_name)
        self.INSTANCE_NAME.setFocus()  # Prevent highlighting
        self.INSTANCE_NAME.blockSignals(False)

        # Set the type
        self.INSTANCE_TYPE_SELECTION.blockSignals(True)
        self.INSTANCE_TYPE_SELECTION.setCurrentText(instance_data['type'])
        self.INSTANCE_TYPE_SELECTION.blockSignals(False)

        # Set the versions corresponding to the type
        all_versions = ['latest']
        if instance_data['type'] == 'Release' or instance_data['type'] == 'Fabric' or instance_data['type'] == 'Forge':
            all_versions.extend(ALL_RELEASE_VERSIONS)
        elif instance_data['type'] == 'Snapshot':
            all_versions.extend(ALL_SNAPSHOT_VERSIONS)
        elif instance_data['type'] == 'Other':
            all_versions = get_installed_versions(instance_data['minecraft_directory'])

        self.INSTANCE_VERSION_SELECTION.blockSignals(True)
        self.INSTANCE_VERSION_SELECTION.clear()
        self.INSTANCE_VERSION_SELECTION.addItems(all_versions)
        if instance_data['version'] in all_versions:
            self.INSTANCE_VERSION_SELECTION.setCurrentText(instance_data['version'])
        else:
            self.INSTANCE_VERSION_SELECTION.setCurrentText('latest')
        self.INSTANCE_VERSION_SELECTION.blockSignals(False)

        # Set the standard options button and the minecraft path
        self.USE_STANDARD_OPTIONS.blockSignals(True)
        self.USE_STANDARD_OPTIONS.setChecked(instance_data['use_default_options_file'])
        self.USE_STANDARD_OPTIONS.blockSignals(False)

        self.MINECRAFT_DIRECTORY_PATH.setText(instance_data['minecraft_directory'])

        # Enable or disable buttons, if we are using the default instance
        if instance_data['is_default']:
            self.DELETE_INSTANCE_BUTTON.setText('Reset')
            self.INSTANCE_TYPE_SELECTION.setEnabled(False)
            self.INSTANCE_VERSION_SELECTION.setEnabled(False)
            self.USE_STANDARD_OPTIONS.setEnabled(False)
        else:
            self.DELETE_INSTANCE_BUTTON.setText('Delete')
            self.INSTANCE_TYPE_SELECTION.setEnabled(True)
            self.INSTANCE_VERSION_SELECTION.setEnabled(True)
            self.USE_STANDARD_OPTIONS.setEnabled(True)

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
        self.INSTANCE_MODS_DISPLAY.set_values(mod_display_data)

    def _changed_instance_name(self):
        # Get the old and the new instance name
        old_instance_name = self.selected_instance_name
        new_instance_name = self.INSTANCE_NAME.text().strip()

        # If the clean new name is empty then it means it was cleared, which is allowed since the user can rewrite the whole name.
        if new_instance_name == '':
            new_instance_name = 'Instance Name'

        # First get the data and only then make the name unique, to avoid mistakes when the name already exists, because of itself
        instance_data = self.data['instances'].pop(old_instance_name)

        new_instance_name = self._make_name_unique(new_instance_name, list(self.data['instances'].keys()))

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

        new_path = QFileDialog.getExistingDirectory(self, 'Select Minecraft Directory', actual_path)

        # TODO: Allow the user only to use userdata paths

        self.data['instances'][self.selected_instance_name]['minecraft_directory'] = new_path

        self.data.save()

        self.MINECRAFT_DIRECTORY_PATH.setText(new_path)  # Refresh the values

    def _delete_instance(self):
        selected_instance = self.selected_instance_name

        # If it is the standard instance then just reset it.
        if self.data['instances'][selected_instance]['is_default']:
            reply = QMessageBox.question(self, 'Confirm resetting', f'''This is the default instance, which can't be deleted. \nDo you really want to reset the instance "{selected_instance}" to its standard values? \n\n(Enter = Yes, Escape = No)''')

            if reply == 16384:  # Yes
                del self.data['instances'][selected_instance]
                self.data.save()

                # Make a unique name here already, to be able to rename the options file
                new_instance_name = self._make_name_unique(DEFAULT_INSTANCE_NAME, list(self.data['instances'].keys()))

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
        reply = QMessageBox.question(self, 'Confirm deletion', f'Do you really want to delete the instance "{selected_instance}"? \n\n(Enter = Yes, Escape = No)')

        if reply == 16384:  # Yes
            del self.data['instances'][selected_instance]
            self.data.save()

            # Go to the instances page
            self.show_page(0, animation_direction=AnimationScrollDirection.HORIZONTAL)

    def _changed_instance_type(self, _new_index: int):
        # Ask the user to confirm the type change
        old_type = self.data['instances'][self.selected_instance_name]['type']
        new_type = self.INSTANCE_TYPE_SELECTION.currentText()

        additional_message = ""
        if old_type == 'Fabric' or old_type == 'Forge':
            if new_type == 'Fabric' or new_type == 'Forge':
                additional_message = 'Incompatible mods will be deselected.'
            else:
                additional_message = 'All mods will be deselected.'

        reply = QMessageBox.question(self, 'Confirm Instance Type change', f'Do you really want to change the type of this instance from {old_type} to {new_type}? \n{additional_message} \n\n(Enter = Yes, Escape = No)')

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
            self.INSTANCE_TYPE_SELECTION.blockSignals(True)
            self.INSTANCE_TYPE_SELECTION.setCurrentText(old_type)
            self.INSTANCE_TYPE_SELECTION.blockSignals(False)

    def _changed_instance_version(self, _new_index: int):
        version = self.INSTANCE_VERSION_SELECTION.currentText()
        self.data['instances'][self.selected_instance_name]['version'] = version
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

    '''
    Mods Page
    '''
    def create_mod(self, mod_name='New Mod', edit_afterwards=True):
        mod_name = self._make_name_unique(mod_name, list(self.data['mods'].keys()))

        # Set the data
        self.data['mods'][mod_name] = {
            'url': '',
            'loaders': [],
            'supported_versions': [],
        }
        self.data.save()

        if edit_afterwards:
            self.edit_mod(mod_name)  # Show it in edit mode

    def edit_mod(self, mod_name: str):
        """ This function is executed to show the edit page and configure the values for the given instance. """
        self.show_page(3, animation_direction=AnimationScrollDirection.HORIZONTAL)

        # Set the values for the edit page
        self.selected_mod_name = mod_name
        mod_url: str = self.data['mods'][mod_name]['url']

        # Set the name without triggering the changed_instance_data function (which triggers on text change)
        self.MOD_NAME.blockSignals(True)
        self.MOD_NAME.setText(mod_name)
        self.MOD_NAME.setFocus()  # Prevent highlighting
        self.MOD_NAME.blockSignals(False)

        self.MOD_URL.blockSignals(True)
        self.MOD_URL.setText(mod_url)
        self.MOD_URL.blockSignals(False)

        # Set the fields depending on the URL and also refresh the stored data
        try:
            description, loaders, supported_versions = get_mod_data(mod_url, self.mod_data_connector.emit_updated, (mod_name, mod_url))
            self.set_mod_values(description, loaders, supported_versions, mod_name, mod_url)
        except ModNotExisting:
            self.set_mod_values('', [], [], mod_name, mod_url)
        except InvalidModBaseUrl:
            self.set_mod_values('', [], [], mod_name, mod_url)
        except Exception as e:
            logger.error('Uncaught exception when changing editing mod', exc_info=e)

    def set_mod_values(self, description: str, loaders: list[str], supported_versions: list[str], mod_name: str, mod_url: str):
        """ If the URL of the given mod matches, then store the given values for said mod. Then display them, if it is the selected mod. """

        if self.data['mods'][mod_name]['url'] != mod_url:
            logger.info("Mod URL changed in the meantime. Callback is discarded.")
            return

        self.data['mods'][mod_name]['loaders'] = loaders
        self.data['mods'][mod_name]['supported_versions'] = supported_versions
        self.data.save()

        clean_description = re.sub(r'<img\b[^>]*>', '', description, flags=re.IGNORECASE)  # Remove the images from the HTML, so no need to load them.
        self.MOD_DESCRIPTION.setHtml(clean_description)
        self.MOD_LOADER.setText('\n'.join(loaders))
        self.MOD_VERSIONS.setText('\n'.join(supported_versions))

    def _changed_mod_name(self):
        # Get the old and the new mod name
        old_mod_name = self.selected_mod_name
        new_mod_name = self.MOD_NAME.text().strip()

        # If the clean new name is empty then it means it was cleared, which is allowed since the user can rewrite the whole name.
        if new_mod_name == '':
            new_mod_name = 'Mod Name'

        # First get the data and only then make the name unique, to avoid mistakes when the name already exists, because of itself
        mod_data = self.data['mods'].pop(old_mod_name)

        new_mod_name = self._make_name_unique(new_mod_name, list(self.data['mods'].keys()))

        # Update the mod name and data
        self.data['mods'][new_mod_name] = mod_data
        self.selected_mod_name = new_mod_name

        # Update the mod name in every instance
        for instance_name in self.data['instances']:
            if old_mod_name in self.data['instances'][instance_name]['mods']:
                mod_download_url = self.data['instances'][instance_name]['mods'].pop(old_mod_name)  # Load the old value and use it with the key of the new value
                self.data['instances'][instance_name]['mods'][new_mod_name] = mod_download_url
        self.data.save()

    def _changed_mod_url(self):
        # This function is only executed after a timer has run out, so after there were no keystrokes in 0.5 seconds.
        new_url = self.MOD_URL.text().strip()
        self.data['mods'][self.selected_mod_name]['url'] = new_url
        self.data.save()
        if validators.url(new_url):
            try:
                description, loaders, supported_versions = get_mod_data(new_url, self.mod_data_connector.emit_updated, (self.selected_mod_name, new_url))
                self.set_mod_values(description, loaders, supported_versions, self.selected_mod_name, new_url)
            except ModNotExisting:
                pass
            except InvalidModBaseUrl:
                pass
            except Exception as e:
                logger.error('Uncaught exception when changing mod URL', exc_info=e)
        else:
            pass
        # TODO: Maybe change color of input field when it is an invalid URL

    def _delete_mod(self):
        # Ask to delete it
        reply = QMessageBox.question(self, 'Confirm deletion', f'Do you really want to delete the mod "{self.selected_mod_name}"? \n\n(Enter = Yes, Escape = No)')

        if reply == 16384:  # Yes
            del self.data['mods'][self.selected_mod_name]
            # Remove the mod from every instance
            for instance_name in self.data['instances']:
                if self.selected_mod_name in self.data['instances'][instance_name]['mods']:
                    del self.data['instances'][instance_name]['mods'][self.selected_mod_name]
            self.data.save()

            # Go to the mods page
            self.show_page(2, animation_direction=AnimationScrollDirection.HORIZONTAL)

    '''
    Settings Page
    '''
    def _stylesheet_selection(self, _button, style_name):
        # We don't need to fix the button here because we always have more than one stylesheet
        filename = style_name.replace('2', '500').replace(' ', '_').lower()  # Changes the name from "Light Green 2" to "light_green_500.xml"
        filename += '.xml'

        self.apply_stylesheet(filename, invert_secondary=self.data['style']['invert_secondary'], density_scale=self.data['style']['scale'])

    def _style_invert_button_clicked(self, button_state: bool):
        self.apply_stylesheet(self.data['style']['theme'], invert_secondary=button_state, density_scale=self.data['style']['scale'])

    def _style_scale_changed(self, scale_value: int):
        # We calculate minus the default scale, so we can use values between 1 and 5 in the UI
        self.apply_stylesheet(self.data['style']['theme'], invert_secondary=self.data['style']['invert_secondary'], density_scale=scale_value - WINDOW_DEFAULT_SCALE)

        # Change grid size
        self.INSTANCES_PAGE.set_size(100+50*scale_value, 60+20*scale_value)
        self.INSTANCES_PAGE.set_spacing(vertical_spacing=10*scale_value)

        self.INSTANCE_MODS_DISPLAY.set_size(70 + 50 * scale_value, 60 + 20 * scale_value)
        self.INSTANCE_MODS_DISPLAY.set_spacing(vertical_spacing=10 * scale_value)

        self.MODS_PAGE.set_size(70 + 50 * scale_value, 60 + 20 * scale_value)
        self.MODS_PAGE.set_spacing(vertical_spacing=10 * scale_value)

    '''
    General functions
    '''
    def apply_stylesheet(self, stylesheet_file_name: str, invert_secondary=False, density_scale=0):
        """
        Add a custom stylesheet based on qt_material
        """

        if stylesheet_file_name not in self.possible_stylesheet_file_names:
            logger.error(f'Stylesheet called "{stylesheet_file_name}" does not exist. Possible themes are: {self.possible_stylesheet_file_names}')
            return

        extra = {
            # Button colors (use in designer with custom property called "class")
            'warning': '#dc3545',

            # Density Scale (for qt_material)
            'density_scale': density_scale,
        }

        # Set environment variables for text
        os.environ['PACKEDMC_BIGGER_TEXT_SIZE'] = str(18 + 4 * density_scale)
        os.environ['PACKEDMC_SELECTION_BUTTON_TEXT_SIZE'] = str(20 + 2 * density_scale)

        # Set environment variable for hover color, using opacity to get the format "rgba(...)", accepted by PyQT
        theme = get_theme(stylesheet_file_name, invert_secondary=invert_secondary)
        os.environ['PACKEDMC_FRAME_HOVER_COLOR'] = opacity(theme['secondaryLightColor'], 0.3)
        os.environ['PACKEDMC_FRAME_SELECTED_COLOR'] = opacity(theme['secondaryLightColor'], 0.7)
        os.environ['PACKEDMC_BUTTON_HOVER_COLOR'] = opacity(theme['primaryColor'], 0.1)
        os.environ['PACKEDMC_BUTTON_PRESSED_COLOR'] = opacity(theme['primaryColor'], 0.6)
        os.environ['PACKEDMC_PLAY_HOVER_COLOR'] = opacity(theme['primaryLightColor'], 0.9)

        # Apply the wanted stylesheet using custom special properties
        apply_stylesheet(self.application, theme=stylesheet_file_name, css_file=CUSTOM_STYLESHEET_FILE_PATH, extra=extra, invert_secondary=invert_secondary, style='windows11')

        # Set the variables and save them
        self.data['style']['theme'] = stylesheet_file_name
        self.data['style']['invert_secondary'] = invert_secondary
        self.data['style']['scale'] = density_scale
        self.data.save()

    @staticmethod
    def _make_name_unique(name: str, already_existing_elements: list[str]):
        # Define the instance name
        original_name = name
        i = 2
        # If an instance with this name already exists then append a number to the end of the instance name
        while name in already_existing_elements:
            name = original_name + ' ' + str(i)
            i += 1

        return name

    def save_options_file_of_last_used_instance(self):
        """ , and if so, copy the options file to the corresponding instance. """
        packedmc_options_files_directory = os.path.join(PACKEDMC_MINECRAFT_DATA_DIRECTORY, 'options_files')

        last_played_profile_id, last_played_profile_data = self.get_last_played_minecraft_launcher_profile()

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

    @staticmethod
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
