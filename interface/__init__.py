import logging
import os
from platform import platform
import json

from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow, QPushButton, QFileDialog, QMessageBox, QCheckBox, QVBoxLayout
from qt_material import apply_stylesheet, list_themes, get_theme, opacity

from .type_hinting import MainWindowElements
from .dynamic_widgets import FieldType, ScrollableGrid, InstanceFieldFunctions, ModFieldFunctions
from .utils import StoredDict, animate_transition, AnimationScrollDirection, create_buttons_in_scroll_area, ScrollAreaButtonType
from .popups import ImportProfilesPopup

from minecraft_api.minecraft import ALL_RELEASE_VERSIONS, ALL_SNAPSHOT_VERSIONS, get_installed_versions


ACTUAL_FILE_DIRECTORY = os.path.dirname(__file__)

INTERFACE_FILE_PATH = os.path.join(ACTUAL_FILE_DIRECTORY, 'ui_files/interface.ui')
CUSTOM_STYLESHEET_FILE_PATH = os.path.join(ACTUAL_FILE_DIRECTORY, 'special_properties.cqss')
WINDOW_DEFAULT_SCALE = 3

DEFAULT_DATA_FILE_PATH = os.path.join(ACTUAL_FILE_DIRECTORY, r'../data.json')
DEFAULT_DATA = {
    # For the style of the App
    'style': {
        'theme': 'dark_lightgreen.xml',
        'invert_secondary': False,
        'scale': 0
    },
    'instances': {},
    'mods': {}
}

if 'windows' in platform().lower():
    ROAMING_DIRECTORY = os.getenv('Appdata')
    STANDARD_MINECRAFT_DIRECTORY = os.path.join(ROAMING_DIRECTORY, '.minecraft')

else:
    STANDARD_MINECRAFT_DIRECTORY = 'UNKNOWN'

DEFAULT_INSTANCE_NAME = 'Latest Release'


class MainWindow(QMainWindow, MainWindowElements):
    def __init__(self, application):
        super().__init__()
        uic.loadUi(INTERFACE_FILE_PATH, self)  # Load UI

        # Non-UI elements
        self.data = StoredDict(DEFAULT_DATA_FILE_PATH, DEFAULT_DATA)  # Initialize using Default Data as base
        self.application = application
        self.possible_stylesheet_file_names = list_themes()
        self.selected_instance_name = ""
        self.all_imported_launcher_profiles = {}
        self.imported_launcher_profiles_file_data = {}

        instance_field_functions = InstanceFieldFunctions(self.play_instance, self.edit_instance, self.create_instance, self.import_profiles_from_launcher)
        mod_field_functions = ModFieldFunctions(self.edit_mod, self.create_mod, self.display_mods)

        self.import_profiles_popup = ImportProfilesPopup(self)
        self.import_profiles_popup.IMPORT_BUTTON.clicked.connect(self._import_selected_profiles)

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
        self.BACK_BUTTON.clicked.connect(lambda: self.show_page(0,animation_direction=AnimationScrollDirection.HORIZONTAL))
        self.BROWSE_MINECRAFT_PATH_BUTTON.clicked.connect(self._set_minecraft_path)
        self.INSTANCE_NAME.textChanged.connect(self._changed_instance_name)
        self.DELETE_INSTANCE_BUTTON.clicked.connect(self._delete_instance)
        self.INSTANCE_TYPE_SELECTION.currentIndexChanged.connect(self._changed_instance_type)
        self.INSTANCE_VERSION_SELECTION.currentIndexChanged.connect(self._changed_instance_version)
        self.USE_STANDARD_OPTIONS.clicked.connect(self._changed_instance_use_standard_options)
        # TODO: Connect advanced options button

        # Add a layout to the Instances Mod Container and add the scrollable grid to it
        layout = QVBoxLayout(self.INSTANCE_MODS_DISPLAY_CONTAINER)
        layout.setContentsMargins(0, 0, 0, 0)  # Remove padding around edges
        layout.setSpacing(0)  # Remove spacing between items
        self.INSTANCE_MODS_DISPLAY = ScrollableGrid(FieldType.MODS_DISPLAYED, mod_field_functions)
        layout.addWidget(self.INSTANCE_MODS_DISPLAY)
        self.INSTANCE_MODS_DISPLAY_CONTAINER.setLayout(layout)

        # If there are no instance, create the default one
        if not self.data['instances']:
            self.create_instance(DEFAULT_INSTANCE_NAME, is_default=True)

        # Create the settings page
        available_stylesheet_filenames = self.possible_stylesheet_file_names
        all_style_names = []
        for filename in available_stylesheet_filenames:
            style_name = filename.replace('.xml', '').replace('500', '2').replace('_', ' ').title()  # Changes the name from light_green_500.xml to Light Green 2
            all_style_names.append(style_name)

        selected_style = self.data['style']['theme'].replace('.xml', '').replace('500', '2').replace('_', ' ').title()

        create_buttons_in_scroll_area(self.STYLES_SELECTION_LIST, all_style_names, selected_style,self._stylesheet_selection)
        self.SWITCH_SECONDARY_COLOR.setChecked(self.data['style']['invert_secondary'])
        self.SWITCH_SECONDARY_COLOR.clicked.connect(self._style_invert_button_clicked)
        self.SCALE_SELECTION.setValue(self.data['style']['scale']+WINDOW_DEFAULT_SCALE)
        self.SCALE_SELECTION.valueChanged.connect(self._style_scale_changed)

        # Show the initial page instantly and refresh whole window again
        self.show_page(0, show_instantly=True)

        self._style_scale_changed(self.data['style']['scale'] + WINDOW_DEFAULT_SCALE)  # Use this to also resize the fields

        self.INSTANCES_PAGE.rebuild_grid()


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


    def show_page(self, page_index: int, animation_direction: AnimationScrollDirection = AnimationScrollDirection.VERTICAL, show_instantly = False):
        # We don't care whether the page is still animating, because it doesn't matter if we execute the page function anyway.
        if show_instantly:
            animate_transition(self, self.PAGE_CONTAINER, page_index, animation_direction=animation_direction, animation_duration=0)
        else:
            animate_transition(self, self.PAGE_CONTAINER, page_index, animation_direction=animation_direction)

        # Page specific functions
        if page_index == 0:
            self.INSTANCES_PAGE.set_values(sorted(self.data['instances'].keys()))
        elif page_index == 2:
            mod_page_values = []
            for mod_name in sorted(self.data['mods'].keys()):
                mod_page_values.append((
                    mod_name,
                    os.path.join(ACTUAL_FILE_DIRECTORY, '../icon.png'),  # TODO: Replace the placeholder with the icon function
                ))
            self.MODS_PAGE.set_values(mod_page_values)

    '''
    Instance page & Instance Edit page
    '''
    def import_profiles_from_launcher(self):
        standard_launcher_profiles_path = STANDARD_MINECRAFT_DIRECTORY + r'\launcher_profiles.json'

        launcher_profiles_path, _ = QFileDialog.getOpenFileName(self, 'Select profiles file for the launcher', standard_launcher_profiles_path, "JSON Files (*.json);;All Files (*)")

        logging.info(f'Importing profiles from {launcher_profiles_path}')

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
                        logging.warning(f'Skipping profile {profile_id} due to faulty profile data')
                        continue

            # If there was no error opening the file, create the checkboxes and display the popup
            create_buttons_in_scroll_area(self.import_profiles_popup.PROFILES_SELECTION_LIST, sorted(self.all_imported_launcher_profiles.keys()), [], lambda *args: None, button_type=ScrollAreaButtonType.CHECKBOX)
            self.import_profiles_popup.show_popup()

        except FileNotFoundError:
            logging.error("Profiles file not found.")
        except json.JSONDecodeError or KeyError:
            logging.error("There has been an error decoding the profiles JSON.")

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

            instance_name = self._make_name_unique(original_instance_name, self.data['instances'].keys())

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
                minecraft_directory = STANDARD_MINECRAFT_DIRECTORY

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
        # TODO: Launch the official Launcher
        print('Play instance', instance_name)

    def create_instance(self, instance_name = 'New instance', is_default = False, edit_afterwards = True, instance_type = 'Release', instance_version = 'latest', minecraft_directory = STANDARD_MINECRAFT_DIRECTORY, advanced_arguments: dict = None):
        instance_name = self._make_name_unique(instance_name, self.data['instances'].keys())
        if advanced_arguments is None:
            advanced_arguments = {}

        # Set the data
        self.data['instances'][instance_name] = {
            'type': instance_type,
            'version': instance_version,
            'is_default': is_default,
            'minecraft_directory': minecraft_directory,
            'standard_options_file': is_default,  # Use standard options file for default, otherwise don't
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
        self.USE_STANDARD_OPTIONS.setChecked(instance_data['standard_options_file'])
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
        mod_display_data = []
        for mod_name in sorted(self.data['mods'].keys()):
            # Add to the mods the name, the icon path and whether it is selected or not
            mod_display_data.append((
                mod_name,
                os.path.join(ACTUAL_FILE_DIRECTORY, '../icon.png'),  # TODO: Replace the placeholder with the icon function
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

        new_instance_name = self._make_name_unique(new_instance_name, self.data['instances'].keys())

        self.data['instances'][new_instance_name] = self.data['instances'].pop(old_instance_name)
        self.selected_instance_name = new_instance_name

        self.data.save()

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

                # Create a default instance under the default name
                self.create_instance(DEFAULT_INSTANCE_NAME, is_default=True)

            return

        # Otherwise just try to delete it
        reply = QMessageBox.question(self, 'Confirm deletion', f'Do you really want to delete the instance "{selected_instance}"? \n\n(Enter = Yes, Escape = No)')

        if reply == 16384:  # Yes
            del self.data['instances'][selected_instance]
            self.data.save()

            # Go to the instances page
            self.show_page(0, animation_direction=AnimationScrollDirection.HORIZONTAL)

    def _changed_instance_type(self, _new_index: int):
        type_name = self.INSTANCE_TYPE_SELECTION.currentText()
        self.data['instances'][self.selected_instance_name]['type'] = type_name
        self.data.save()

        self.edit_instance(self.selected_instance_name, only_refresh_values=True)

    def _changed_instance_version(self, _new_index: int):
        version = self.INSTANCE_VERSION_SELECTION.currentText()
        self.data['instances'][self.selected_instance_name]['version'] = version
        self.data.save()

    def _changed_instance_use_standard_options(self, new_state: bool):
        self.data['instances'][self.selected_instance_name]['standard_options_file'] = new_state
        self.data.save()

    def display_mods(self, mod_name: str, is_selected: bool):
        print('Displaying mod', mod_name, is_selected)


    '''
    Mods Page
    '''
    def create_mod(self, mod_name = 'New Mod', edit_afterwards=True):
        mod_name = self._make_name_unique(mod_name, self.data['mods'].keys())

        # Set the data
        self.data['mods'][mod_name] = {
            'url': '',
            'description': '',
            'icon': '',
            'mod_loaders': [],
            'supported_versions': [],
        }
        self.data.save()

        if edit_afterwards:
            self.edit_mod(mod_name)  # Show it in edit mode

    def edit_mod(self, mod_name: str):
        print('Editing mod', mod_name)


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
            logging.error(f'Stylesheet called "{stylesheet_file_name}" does not exist. Possible themes are: {self.possible_stylesheet_file_names}')
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
        os.environ['PACKEDMC_FRAME_HOVER_COLOR'] = opacity(theme['secondaryLightColor'], 0.5)
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

        os.environ['QTMATERIAL_PRIMARYCOLOR'] = "#000000"

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
