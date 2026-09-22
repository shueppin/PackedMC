import os
import logging
import json

# noinspection PyPackageRequirements
from PyQt6 import uic
# noinspection PyPackageRequirements
from PyQt6.QtCore import Qt
# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QWidget, QDialog, QPushButton, QMainWindow, QTextEdit, QSpinBox, QCheckBox, QFileDialog, QVBoxLayout, QListWidget, QLabel, QListWidgetItem, QInputDialog, QHBoxLayout, QMessageBox

from .utils import create_buttons_in_scroll_area, ScrollAreaButtonType
from .dynamic_widgets import DEFAULT_ALL_TAGS_NAME, DEFAULT_NO_TAGS_NAME

from data_file_helper import Data
from file_paths import MINECRAFT_LAUNCHER_PROFILES_PATH, MINECRAFT_DIRECTORY, UI_FILES_DIRECTORY
from minecraft_api.minecraft import ALL_RELEASE_VERSIONS, ALL_SNAPSHOT_VERSIONS

# Import the MainWindow for Type Checking
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from interface import MainWindow


logger = logging.getLogger(__name__)


'''
Popups using .ui files
'''


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
            create_buttons_in_scroll_area(self.import_profiles_popup.PROFILES_SELECTION_LIST, sorted(self.all_imported_launcher_profiles.keys()), [], lambda _s, _n: None, button_type=ScrollAreaButtonType.CHECKBOX)
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
        self.data: Data = parent.data

        # Create the popup and connect the widgets
        self.advanced_options_popup = _AdvancedOptionsPopupWindow(parent)
        self.advanced_options_popup.finished.connect(self._store_popup_values)

    def open_popup(self):
        print('open')
        # Set the values from the saved data when opening the popup
        arguments = self.data.instances[self.parent.instance_page_class.selected_instance_name].advanced_arguments
        self.advanced_options_popup.START_HEAP_SIZE.setValue(arguments.start_heap_size)
        self.advanced_options_popup.MAX_HEAP_SIZE.setValue(arguments.max_heap_size)
        self.advanced_options_popup.OTHER_ARGUMENTS.setText(arguments.other_arguments)

        self.advanced_options_popup.display(True)

    def _store_popup_values(self):
        # Store the values of the popup before closing
        self.data.instances[self.parent.instance_page_class.selected_instance_name].advanced_arguments.max_heap_size = self.advanced_options_popup.MAX_HEAP_SIZE.value()
        self.data.instances[self.parent.instance_page_class.selected_instance_name].advanced_arguments.start_heap_size = self.advanced_options_popup.START_HEAP_SIZE.value()
        self.data.instances[self.parent.instance_page_class.selected_instance_name].advanced_arguments.other_arguments = self.advanced_options_popup.OTHER_ARGUMENTS.toPlainText()

        self.data.save()


'''
Popups not using .ui file. They are dynamically created.
'''


class ModTagPopup(QDialog):
    def __init__(self, parent: MainWindow):
        super().__init__(parent)

        self.data: Data = parent.data

        self.setWindowTitle("Edit Mod Tags")
        self.setMinimumSize(400, 450)

        # Setup UI
        layout = QVBoxLayout(self)

        # Header
        title = QLabel("Mod Tags")
        title.setProperty('class', 'bigger_text colored_text')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # List
        self.tag_list = QListWidget()
        self.tag_list.setSpacing(4)
        layout.addWidget(self.tag_list)

        # Add button
        add_button = QPushButton("Add Tag")
        add_button.setMinimumHeight(38)
        # noinspection PyUnresolvedReferences
        add_button.clicked.connect(self._add_tag)

        layout.addWidget(add_button)

    def _refresh_tags(self):
        """Rebuild the list from self.tags."""
        self.tag_list.clear()

        for tag in self.data.tags:
            item = QListWidgetItem()
            self.tag_list.addItem(item)

            widget = self._create_tag_widget(tag)
            item.setSizeHint(widget.sizeHint())

            self.tag_list.setItemWidget(item, widget)

    def _create_tag_widget(self, tag):
        widget = QWidget()

        layout = QHBoxLayout(widget)
        layout.setContentsMargins(8, 5, 8, 5)

        # Tag name
        label = QLabel(tag)

        layout.addWidget(label)
        layout.addStretch()

        # Rename button
        rename_button = QPushButton("Rename")
        # noinspection PyUnresolvedReferences
        rename_button.clicked.connect(lambda: self._rename_tag(tag))

        # Delete button
        delete_button = QPushButton("Delete")
        # noinspection PyUnresolvedReferences
        delete_button.clicked.connect(lambda: self._delete_tag(tag))

        layout.addWidget(rename_button)
        layout.addWidget(delete_button)

        return widget

    def _add_tag(self):
        tag, ok = QInputDialog.getText(self, "Add Tag", "Tag name:")

        if ok and tag.strip():
            tag = tag.strip()

            if tag not in self.data.tags and tag.lower() != DEFAULT_ALL_TAGS_NAME.lower() and tag.lower() != DEFAULT_NO_TAGS_NAME.lower():
                self.data.tags.append(tag)
                self.data.tags.sort()
                self.data.save()
                self._refresh_tags()

    def _rename_tag(self, old_tag):
        new_tag, ok = QInputDialog.getText(self, "Rename Tag", "New name:", text=old_tag)

        if ok and new_tag.strip():
            new_tag = new_tag.strip()

            if new_tag != old_tag and new_tag not in self.data.tags and new_tag.lower() != DEFAULT_ALL_TAGS_NAME.lower() and new_tag.lower() != DEFAULT_NO_TAGS_NAME.lower():
                # Replace it in the tags
                index = self.data.tags.index(old_tag)
                self.data.tags[index] = new_tag

                # Replace the tag for every mod
                for mod_name in self.data.mods:
                    if old_tag in self.data.mods[mod_name].tags:
                        index = self.data.mods[mod_name].tags.index(old_tag)
                        self.data.mods[mod_name].tags[index] = new_tag

                self.data.tags.sort()
                self.data.save()
                self._refresh_tags()

    def _delete_tag(self, tag):
        reply = QMessageBox.question(self, 'Confirm deletion', f'Do you really want to delete the tag "{tag}"? \n\n(Enter = Yes, Escape = No)')

        if reply == 16384:  # Yes
            self.data.tags.remove(tag)

            # Delete the tag for every mod
            for mod_name in self.data.mods:
                if tag in self.data.mods[mod_name].tags:
                    self.data.mods[mod_name].tags.remove(tag)

            self.data.save()
            self._refresh_tags()

    def display(self):
        self._refresh_tags()
        # Show the dialog while blocking the main application
        self.exec()
