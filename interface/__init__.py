import logging
import os
from platform import platform

from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow, QPushButton, QFileDialog
from qt_material import apply_stylesheet, list_themes, get_theme, opacity

from .type_hinting import MainWindowElements
from .dynamic_widgets import ScrollableGrid, InstanceFieldFunctions, FieldType
from .utils import StoredDict, animate_transition, AnimationScrollDirection, create_buttons_in_scroll_area


ACTUAL_FILE_DIRECTORY = os.path.dirname(__file__)

INTERFACE_FILE_PATH = os.path.join(ACTUAL_FILE_DIRECTORY, 'interface.ui')
CUSTOM_STYLESHEET_FILE_PATH = os.path.join(ACTUAL_FILE_DIRECTORY, 'special_properties.cqss')
WINDOW_DEFAULT_SCALE = 3

DEFAULT_DATA_FILE_PATH = os.path.join(ACTUAL_FILE_DIRECTORY, r'..\data.json')
DEFAULT_DATA = {
    # For the style of the App
    'style': {
        'theme': 'dark_lightgreen.xml',
        'invert_secondary': False,
        'scale': 0
    },
    'instances': {}
}

if 'windows' in platform().lower():
    ROAMING_DIRECTORY = os.getenv('Appdata')
    STANDARD_MINECRAFT_DIRECTORY = os.path.join(ROAMING_DIRECTORY, r'\.minecraft')

else:
    STANDARD_MINECRAFT_DIRECTORY = 'UNKNOWN'

DEFAULT_INSTANCE_NAME = 'Latest Release'


logger = logging.getLogger('interface')


class MainWindow(QMainWindow, MainWindowElements):
    def __init__(self, application):
        super().__init__()
        uic.loadUi(INTERFACE_FILE_PATH, self)  # Load UI

        # Load non-UI variables
        self.data = StoredDict(DEFAULT_DATA_FILE_PATH, DEFAULT_DATA)  # Initialize using Default Data as base
        self.application = application
        self.possible_stylesheet_file_names = list_themes()
        self.selected_instance_name = ""

        # Create the new grid page and insert it where the placeholder was
        instance_field_functions = InstanceFieldFunctions(self._play_instance, self._edit_instance, self._create_instance)
        self.INSTANCES_PAGE = ScrollableGrid(FieldType.INSTANCES, instance_field_functions)

        index = self.PAGE_CONTAINER.indexOf(self.INSTANCES_PAGE_PLACEHOLDER)
        self.PAGE_CONTAINER.removeWidget(self.INSTANCES_PAGE_PLACEHOLDER)  # remove placeholder
        self.PAGE_CONTAINER.insertWidget(index, self.INSTANCES_PAGE)  # insert new page at same position
        self.INSTANCES_PAGE_PLACEHOLDER.deleteLater()  # Cleanup

        # Bind the page selection buttons
        self.INSTANCES_PAGE_BUTTON.pressed.connect(lambda: self._page_selection_button_on_press(self.INSTANCES_PAGE_BUTTON, 0))
        self.INSTANCES_PAGE_BUTTON.released.connect(lambda: self._page_selection_button_on_release(self.INSTANCES_PAGE_BUTTON))
        self.MODS_PAGE_BUTTON.pressed.connect(lambda: self._page_selection_button_on_press(self.MODS_PAGE_BUTTON, 2))
        self.MODS_PAGE_BUTTON.released.connect(lambda: self._page_selection_button_on_release(self.MODS_PAGE_BUTTON))
        self.SETTINGS_PAGE_BUTTON.pressed.connect(lambda: self._page_selection_button_on_press(self.SETTINGS_PAGE_BUTTON, 4))
        self.SETTINGS_PAGE_BUTTON.released.connect(lambda: self._page_selection_button_on_release(self.SETTINGS_PAGE_BUTTON))

        # Create the instance edit page
        self.BACK_BUTTON.clicked.connect(lambda: self._show_page(0, animation_direction=AnimationScrollDirection.HORIZONTAL))
        self.BROWSE_MINECRAFT_PATH_BUTTON.clicked.connect(self._set_minecraft_path)
        # TODO: Connect other buttons

        # If there are no instance, create the standard one
        if not self.data['instances']:
            self._create_instance(DEFAULT_INSTANCE_NAME)

        # Create the settings page
        available_stylesheet_filenames = self.possible_stylesheet_file_names
        all_style_names = []
        for filename in available_stylesheet_filenames:
            style_name = filename.replace('.xml', '').replace('500', '2').replace('_',
                                                                                  ' ').title()  # Changes the name from light_green_500.xml to Light Green 2
            all_style_names.append(style_name)

        selected_style = self.data['style']['theme'].replace('.xml', '').replace('500', '2').replace('_', ' ').title()

        create_buttons_in_scroll_area(self.STYLES_SELECTION_LIST, all_style_names, selected_style, self._stylesheet_selection)
        self.SWITCH_SECONDARY_COLOR.setChecked(self.data['style']['invert_secondary'])
        self.SWITCH_SECONDARY_COLOR.clicked.connect(self._style_invert_button_clicked)
        self.SCALE_SELECTION.setValue(self.data['style']['scale']+WINDOW_DEFAULT_SCALE)
        self.SCALE_SELECTION.valueChanged.connect(self._style_scale_changed)

        # Show the initial page instantly and refresh whole window again
        self._show_page(0, show_instantly=True)

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

        self._show_page(new_page_index, animation_direction)


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


    def _show_page(self, page_index: int, animation_direction: AnimationScrollDirection = AnimationScrollDirection.VERTICAL, show_instantly = False):
        # We don't care whether the page is still animating, because it doesn't matter if we execute the page function anyway.
        if show_instantly:
            animate_transition(self, self.PAGE_CONTAINER, page_index, animation_direction=animation_direction, animation_duration=0)
        else:
            animate_transition(self, self.PAGE_CONTAINER, page_index, animation_direction=animation_direction)

        # Page specific functions
        if page_index == 0:
            self.INSTANCES_PAGE.set_values(self.data['instances'].keys())
            #self.INSTANCES_PAGE.rebuild_grid(force=True)

    '''
    Instance page & Instance Edit page
    '''

    def _play_instance(self, instance_name: str):
        # TODO: Launch the official Launcher
        print('Play instance', instance_name)

    def _create_instance(self, instance_name = 'New instance'):
        # Define the instance name
        original_instance_name = instance_name
        i = 1
        # If an instance with this name already exists then append a number to the end of the instance name
        while instance_name in self.data['instances'].keys():
            instance_name = original_instance_name + ' ' + str(i)
            i += 1

        print('Create new instance', instance_name)

        # Set the data
        self.data['instances'][instance_name] = {
            'type': 'Release',
            'version': 'latest',
            'default': instance_name == DEFAULT_INSTANCE_NAME,  # Either set it as default or not
            'minecraft_directory': STANDARD_MINECRAFT_DIRECTORY,
            'usable_mods': False,
            'total_mods': False,
            'standard_options_file': False,
            'advanced_arguments': {}
        }

        self.data.save()

        self._edit_instance(instance_name)  # Show it in edit mode

    def _edit_instance(self, instance_name: str, skip_animation = False):
        if not skip_animation:
            self._show_page(1, animation_direction=AnimationScrollDirection.HORIZONTAL)

        print(instance_name)

    '''
        # Set the values for the edit page
        self.selected_instance_name = instance_name
        instance_data = self.data['instances'][instance_name]

        # Modify the name without triggering the changed_instance_data function (which triggers on text change)
        self.INSTANCE_NAME.blockSignals(True)
        self.INSTANCE_NAME.setText(instance_name)
        self.INSTANCE_NAME.blockSignals(False)

        self.MINECRAFT_DIRECTORY_PATH.setText(instance_data['minecraft_directory'])
        self.INSTANCE_TYPE_SELECTION.setCurrentText(instance_data['type'])
        # TODO: Set the Version ComboBox using combobox.clear() and combobox.addItems([]) based on the type and select the correct one (add also "latest")

        # TODO: Set the mods
        '''


    def _set_minecraft_path(self):
        actual_path = self.data['instances'][self.selected_instance_name]['minecraft_directory']

        new_path = QFileDialog.getExistingDirectory(self, 'Select Minecraft Directory', actual_path)

        # TODO: Allow the user only to use userdata paths

        self.data['instances'][self.selected_instance_name]['minecraft_directory'] = new_path

        self._edit_instance(self.selected_instance_name, True)  # Refresh the values
        # TODO: Maybe instead of "skip_animation=True" we can set the values here


    '''
    Settings Page
    '''
    def _stylesheet_selection(self, _button, style_name):
        # We don't need to fix the button here because we always have more than one stylesheet

        filename = style_name.replace('2', '500').replace(' ', '_').lower()  # Changes the name from "Light Green 2" to "light_green_500.xml"
        filename += '.xml'

        self._apply_stylesheet(filename, invert_secondary=self.data['style']['invert_secondary'], density_scale=self.data['style']['scale'])

    def _style_invert_button_clicked(self, button_state: bool):
        self._apply_stylesheet(self.data['style']['theme'], invert_secondary = button_state, density_scale = self.data['style']['scale'])

    def _style_scale_changed(self, scale_value: int):
        self._apply_stylesheet(self.data['style']['theme'], invert_secondary = self.data['style']['invert_secondary'], density_scale = scale_value-WINDOW_DEFAULT_SCALE)  # minus default scale, so we can use values between 1 and 5 in the UI

        # Change grid size
        self.INSTANCES_PAGE.set_size(100+50*scale_value, 60+20*scale_value)
        self.INSTANCES_PAGE.set_spacing(vertical_spacing=10*scale_value)


    '''
    General functions
    '''
    def _apply_stylesheet(self, stylesheet_file_name: str, invert_secondary=False, density_scale=0):
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
        os.environ['PACKEDMC_INSTANCE_LABEL_SIZE'] = str(20 + 4 * density_scale)
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
