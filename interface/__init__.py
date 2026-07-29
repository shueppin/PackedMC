import logging
import os
import traceback
import requests
import time
import threading

# noinspection PyPackageRequirements
from PyQt6 import uic
# noinspection PyPackageRequirements
from PyQt6.QtCore import Qt
# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QMainWindow, QPushButton, QMessageBox, QVBoxLayout, QProgressDialog
from qt_material import apply_stylesheet, list_themes, get_theme, opacity

from .type_hinting import MainWindowElements, DataDictType
from .dynamic_widgets import FieldType, ScrollableGrid, InstanceFieldFunctions, ModFieldFunctions
from .utils import StoredDict, animate_transition, AnimationScrollDirection, create_buttons_in_scroll_area
from .file_paths import INTERFACE_FILE_PATH, CUSTOM_STYLESHEET_FILE_PATH, DATA_FILE_PATH, PACKEDMC_MINECRAFT_DATA_DIRECTORY
from .minecraft_launcher_integration import MinecraftLauncherIntegration
from .popups import ImportProfilesHandler

from minecraft_api.mod import get_mod_icon_path, InvalidModBaseUrl, ModNotExisting, get_download_url, NoModFileAvailable, APICooldown, TryAgainLater

from .mod_page import ModPageClass
from .instance_page import InstancePageClass, DEFAULT_INSTANCE_NAME


logger = logging.getLogger(__name__)


WINDOW_DEFAULT_SCALE = 3

DEFAULT_DATA = {
    # For the style of the App
    'settings': {
        'theme': 'dark_lightgreen.xml',
        'invert_secondary': False,
        'scale': 0,
        'close_packedmc': False
    },
    'last_played_instance': '',
    'instances': {},
    'mods': {}
}

# This is the amount of seconds it should wait before checking something like the mod data or the mod download url again.
SKIP_WHEN_LAST_CHECKED_BEFORE = 600


# Ensure correct directories exist
os.makedirs(os.path.join(PACKEDMC_MINECRAFT_DATA_DIRECTORY, 'options_files'), exist_ok=True)  # creates all missing parents; no error if exists


class MainWindow(QMainWindow, MainWindowElements):
    def __init__(self, application):
        super().__init__()
        uic.loadUi(INTERFACE_FILE_PATH, self)  # Load UI
        self.setWindowTitle("PackedMC")

        # Define variables which are mainly needed in this file
        self.data: DataDictType = StoredDict(DATA_FILE_PATH, DEFAULT_DATA)  # Initialize using Default Data as base
        self.application = application
        self.possible_stylesheet_file_names = list_themes()

        # Create the official launcher integration, pages and popups from their respective classes
        self.minecraft_launcher_integration = MinecraftLauncherIntegration(self)

        self.mods_page_class = ModPageClass(self)
        self.instance_page_class = InstancePageClass(self)

        self.import_profiles_popup_handler = ImportProfilesHandler(self)

        # "Collect" the functions for the clickable fields inside the scrollable grids
        instance_field_functions = InstanceFieldFunctions(self.instance_page_class.play_instance, self.instance_page_class.edit_instance, self.instance_page_class.create_instance, self.import_profiles_popup_handler.open_popup)
        mod_field_functions = ModFieldFunctions(self.mods_page_class.edit_mod, self.mods_page_class.create_mod, self.instance_page_class.clicked_displayed_mod)

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

        # Add a layout to the Instances Mod Container in the instances and add the scrollable grid to it
        layout = QVBoxLayout(self.INSTANCE_MODS_DISPLAY_CONTAINER)
        layout.setContentsMargins(0, 0, 0, 0)  # Remove padding around edges
        layout.setSpacing(0)  # Remove spacing between items
        self.INSTANCE_MODS_DISPLAY = ScrollableGrid(FieldType.MODS_DISPLAYED, mod_field_functions)
        layout.addWidget(self.INSTANCE_MODS_DISPLAY)
        self.INSTANCE_MODS_DISPLAY_CONTAINER.setLayout(layout)

        # If there are no instances, create the default one
        if not self.data['instances']:
            self.instance_page_class.create_instance(DEFAULT_INSTANCE_NAME, is_default=True, edit_afterwards=False)
            self.data['last_played_instance'] = DEFAULT_INSTANCE_NAME
            self.data.save()

        # Create the settings page
        available_stylesheet_filenames = self.possible_stylesheet_file_names
        all_style_names = []
        for filename in available_stylesheet_filenames:
            style_name = filename.replace('.xml', '').replace('500', '2').replace('_', ' ').title()  # Changes the name from light_green_500.xml to Light Green 2
            all_style_names.append(style_name)

        selected_style = self.data['settings']['theme'].replace('.xml', '').replace('500', '2').replace('_', ' ').title()

        create_buttons_in_scroll_area(self.STYLES_SELECTION_LIST, all_style_names, selected_style, self._stylesheet_selection)
        self.SWITCH_SECONDARY_COLOR.setChecked(self.data['settings']['invert_secondary'])
        self.SWITCH_SECONDARY_COLOR.clicked.connect(self._style_invert_button_clicked)
        self.SCALE_SELECTION.setValue(self.data['settings']['scale']+WINDOW_DEFAULT_SCALE)
        self.SCALE_SELECTION.valueChanged.connect(self._style_scale_changed)
        self.CLOSE_PACKEDMC_BUTTON.setChecked(self.data['settings']['close_packedmc'])
        self.CLOSE_PACKEDMC_BUTTON.clicked.connect(self.close_packedmc_button_clicked)

        # Show the initial page instantly and refresh whole window again
        self.show_page(0, show_instantly=True)

        self._style_scale_changed(self.data['settings']['scale'] + WINDOW_DEFAULT_SCALE)  # Use this to also resize the fields

        self.INSTANCES_PAGE.rebuild_grid()

        # Save the actual options file from the minecraft directory
        self.minecraft_launcher_integration.save_options_file_of_last_used_instance()

        # Update the mods of the last played instance in a thread
        last_played_instance = self.data['last_played_instance']
        instance_mods = self.data['instances'][last_played_instance]['mods']
        instance_version = self.data['instances'][last_played_instance]['version']
        instance_type = self.data['instances'][last_played_instance]['type']
        mod_update_thread = threading.Thread(target=self.update_mod_files, args=(last_played_instance, instance_mods, instance_version, instance_type, False), daemon=True)
        mod_update_thread.start()

        # TODO: Add a button to redownload/update a certain fabric version

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
    Settings Page
    '''
    def _stylesheet_selection(self, _button, style_name):
        # We don't need to fix the button here because we always have more than one stylesheet
        filename = style_name.replace('2', '500').replace(' ', '_').lower()  # Changes the name from "Light Green 2" to "light_green_500.xml"
        filename += '.xml'

        self.apply_stylesheet(filename, invert_secondary=self.data['settings']['invert_secondary'], density_scale=self.data['settings']['scale'])

    def _style_invert_button_clicked(self, button_state: bool):
        self.apply_stylesheet(self.data['settings']['theme'], invert_secondary=button_state, density_scale=self.data['settings']['scale'])

    def _style_scale_changed(self, scale_value: int):
        # We calculate minus the default scale, so we can use values between 1 and 5 in the UI
        self.apply_stylesheet(self.data['settings']['theme'], invert_secondary=self.data['settings']['invert_secondary'], density_scale=scale_value - WINDOW_DEFAULT_SCALE)

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
        self.data['settings']['theme'] = stylesheet_file_name
        self.data['settings']['invert_secondary'] = invert_secondary
        self.data['settings']['scale'] = density_scale
        self.data.save()

    @staticmethod
    def make_name_unique(name: str, already_existing_elements: list[str]):
        # Define the instance name
        original_name = name
        i = 2
        # If an instance with this name already exists then append a number to the end of the instance name
        while name in already_existing_elements:
            name = original_name + ' ' + str(i)
            i += 1

        return name

    def update_mod_files(self, instance_name: str, mods_data: dict[str, tuple[str, str, int]], mc_version: str, loader: str, output=True):
        """
        Go through all mods and try to get their download links (if they were not just checked recently).
        Then download the files if they don't already exist and remove the old mod versions.
        """
        if not output:
            logger.info(f'Start updating mods in the background for {instance_name}.')

        actual_time = round(time.time())

        packedmc_mods_directory = os.path.join(PACKEDMC_MINECRAFT_DATA_DIRECTORY, 'mods', instance_name)
        os.makedirs(packedmc_mods_directory, exist_ok=True)  # Ensure it exists
        unneeded_files = os.listdir(packedmc_mods_directory)

        mods_not_found_for_this_version = []

        progress_dialog = None  # Define it
        if output:
            progress_dialog = QProgressDialog("Downloading mods...", "", 0, len(mods_data), self)  # empty cancel text
            progress_dialog.setCancelButton(None)  # remove cancel button
            progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
            progress_dialog.setAutoClose(True)
            progress_dialog.setWindowTitle("Downloading mods...")
            progress_dialog.setAutoReset(True)
            progress_dialog.setMinimumDuration(0)

            progress_dialog.setFixedSize(300, 250)

        # Go through every mod and download it if needed
        for index, mod_name in enumerate(mods_data):
            if output:
                progress_dialog.setValue(index + 1)
                progress_dialog.setLabelText("Downloading mod: \n" + mod_name)

            try:
                old_download_url, old_filename, last_checked = mods_data[mod_name]
            except Exception:  # If there is a mistake in the data, then update it and use default values
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

                # Remove the filename from the unneeded files, so it is not removed.
                if filename in unneeded_files:
                    unneeded_files.remove(filename)
            except (InvalidModBaseUrl, NoModFileAvailable):
                # Mod unavailable, thus no possible download URL
                mods_not_found_for_this_version.append(mod_name)
                self.data['instances'][instance_name]['mods'][mod_name] = ('', '', last_checked)
                self.data.save()
            except (APICooldown, TryAgainLater):
                # Just do nothing. It will be tried again when playing this instance again.
                pass
            except Exception:
                traceback.print_exc()

        if output:
            progress_dialog.close()
            # If not all mods could be updated, show a message
            if len(mods_not_found_for_this_version) > 0:
                QMessageBox.information(self, 'Could not find all mods', f'Could not find a file for the following mods for {loader} {mc_version}: \n - {"\n - ".join(mods_not_found_for_this_version)}')

        # Delete all unneeded files (either from removed mods, or old versions of a mod)
        for unneeded_filename in unneeded_files:
            os.remove(os.path.join(packedmc_mods_directory, unneeded_filename))

        if not output:
            logger.info(f'Updated mods in the background for {instance_name}.')

    def close_packedmc_button_clicked(self, button_state: bool):
        self.data['settings']['close_packedmc'] = button_state
        self.data.save()
