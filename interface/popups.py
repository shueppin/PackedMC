import os
import logging
import json

# noinspection PyPackageRequirements
from PyQt6 import uic
# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QWidget, QDialog, QPushButton, QMainWindow, QTextEdit, QSpinBox, QCheckBox, QFileDialog

from .file_paths import MINECRAFT_LAUNCHER_PROFILES_PATH, MINECRAFT_DIRECTORY, UI_FILES_DIRECTORY
from .utils import create_buttons_in_scroll_area, ScrollAreaButtonType

from minecraft_api.minecraft import ALL_RELEASE_VERSIONS, ALL_SNAPSHOT_VERSIONS

# Import the MainWindow for Type Checking
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from interface import MainWindow


logger = logging.getLogger(__name__)


class _PopupTemplate(QDialog):
    def __init__(self, file_path: str, parent: QMainWindow):
        """
        Initialises a dialog based on the passed ui file and adding a show_dialog function.
        This is created under the parent, so if the parent is closed, the popup closes too.
        """
        super().__init__(parent)

        # Load the UI file for the popup
        uic.loadUi(file_path, self)

    def display(self, blocking=False):
        # Show the dialog, either with blocking the main application or without blocking the main application.
        if blocking:
            self.exec()
        else:
            self.show()


class _ImportProfilesPopupWindow(_PopupTemplate):
    PROFILES_SELECTION_LIST: QWidget
    IMPORT_BUTTON: QPushButton

    def __init__(self, parent: QMainWindow):
        file_path = os.path.join(UI_FILES_DIRECTORY, 'import_profiles_popup.ui')
        super().__init__(file_path, parent)


class _AdvancedOptionsPopupWindow(_PopupTemplate):
    START_HEAP_SIZE: QSpinBox
    MAX_HEAP_SIZE: QSpinBox
    OTHER_ARGUMENTS: QTextEdit

    def __init__(self, parent: QMainWindow):
        file_path = os.path.join(UI_FILES_DIRECTORY, 'advanced_options_popup.ui')
        super().__init__(file_path, parent)


class ImportProfilesHandler:
    def __init__(self, parent: MainWindow):
        self.parent = parent

        # Define some local variables
        self.all_imported_launcher_profiles = {}
        self.imported_launcher_profiles_file_data = {}

        # Create the popup and connect the widgets
        self.import_profiles_popup = _ImportProfilesPopupWindow(parent)
        self.import_profiles_popup.IMPORT_BUTTON.clicked.connect(self._import_selected_profiles)

    def open_popup(self):
        launcher_profiles_path, _ = QFileDialog.getOpenFileName(self.parent, 'Select profiles file for the launcher', MINECRAFT_LAUNCHER_PROFILES_PATH, "JSON Files (*.json);;All Files (*)")

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
            self.import_profiles_popup.display()

        except FileNotFoundError:
            logger.error("Profiles file not found.")
        except json.JSONDecodeError or KeyError:
            logger.error("There has been an error decoding the profiles JSON.")

    def _import_selected_profiles(self):
        """
        Gets all selected profiles from the import_profiles_popup and creates an instance for them
        """
        # Go through all the selected profiles and create the data for them
        profile_checkbox_widget: QCheckBox
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

            instance_name = self.parent.make_name_unique(original_instance_name, list(self.parent.data['instances'].keys()))

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

            self.parent.instance_page_class.create_instance(instance_name, edit_afterwards=False, instance_type=instance_type, instance_version=instance_version, minecraft_directory=minecraft_directory, advanced_arguments=advanced_arguments)

        # After all profiles were added refresh the list and close the dialog
        self.parent.show_page(0, show_instantly=True)
        self.import_profiles_popup.close()


class AdvancedOptionsHandler:
    def __init__(self, parent: MainWindow):
        self.parent = parent
        self.data = parent.data

        # Create the popup and connect the widgets
        self.advanced_options_popup = _AdvancedOptionsPopupWindow(parent)
        self.advanced_options_popup.finished.connect(self._store_popup_values)

    def open_popup(self):
        # Set the values from the saved data when opening the popup
        arguments = self.data['instances'][self.parent.instance_page_class.selected_instance_name]['advanced_arguments']
        if 'start_heap_size' in arguments:
            self.advanced_options_popup.START_HEAP_SIZE.setValue(arguments['start_heap_size'])
        else:
            self.advanced_options_popup.START_HEAP_SIZE.setValue(2)
        if 'max_heap_size' in arguments:
            self.advanced_options_popup.MAX_HEAP_SIZE.setValue(arguments['max_heap_size'])
        else:
            self.advanced_options_popup.MAX_HEAP_SIZE.setValue(2)
        if 'other_arguments' in arguments:
            self.advanced_options_popup.OTHER_ARGUMENTS.setText(arguments['other_arguments'])

        self.advanced_options_popup.display(True)

    def _store_popup_values(self):
        # Store the values of the popup before closing
        self.data['instances'][self.parent.instance_page_class.selected_instance_name]['advanced_arguments']['max_heap_size'] = self.advanced_options_popup.MAX_HEAP_SIZE.value()
        self.data['instances'][self.parent.instance_page_class.selected_instance_name]['advanced_arguments']['start_heap_size'] = self.advanced_options_popup.START_HEAP_SIZE.value()
        self.data['instances'][self.parent.instance_page_class.selected_instance_name]['advanced_arguments']['other_arguments'] = self.advanced_options_popup.OTHER_ARGUMENTS.toPlainText()

        self.data.save()
