import sys
import logging
import os

from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow, QApplication
from qt_material import apply_stylesheet, list_themes

from type_hinting import MainWindowElements
from dynamic_widgets import ScrollableGrid, FieldType
from utils import StoredDict


ACTUAL_FILE_DIRECTORY = os.path.dirname(__file__)

INTERFACE_FILE_PATH = os.path.join(ACTUAL_FILE_DIRECTORY, 'interface.ui')
CUSTOM_STYLESHEET_FILE_PATH = os.path.join(ACTUAL_FILE_DIRECTORY, 'special_properties.cqss')

DEFAULT_DATA_FILE_PATH = os.path.join(ACTUAL_FILE_DIRECTORY, os.path.abspath('../data.json'))
DEFAULT_DATA = {
    # For the style of the App
    'style': {
        'theme': 'dark_lightgreen.xml',
        'invert_secondary': False,
        'scale': 0
    }
}


logger = logging.getLogger('interface')


class MainWindow(QMainWindow, MainWindowElements):
    def __init__(self, application):
        super().__init__()
        uic.loadUi(INTERFACE_FILE_PATH, self)  # Load UI

        # Load non-UI variables
        self.data = StoredDict(DEFAULT_DATA_FILE_PATH, DEFAULT_DATA)  # Initialize using Default Data as base
        self.application = application
        self.possible_stylesheet_file_names = list_themes()

        # Example instance names
        instances = [
            "Survival World", "Creative World", "Modpack 1", "Modpack 2",
            "Adventure Map", "Test Instance", "Extra World 1", "Extra World 2",
            "Extra World 3", "Extra World 4", "Extra World 5",
        ]

        # Create the new grid page and insert it where the placeholder was
        self.INSTANCES_PAGE = ScrollableGrid(FieldType.INSTANCES)

        index = self.PAGE_CONTAINER.indexOf(self.INSTANCES_PAGE_PLACEHOLDER)
        self.PAGE_CONTAINER.removeWidget(self.INSTANCES_PAGE_PLACEHOLDER)  # remove placeholder
        self.PAGE_CONTAINER.insertWidget(index, self.INSTANCES_PAGE)  # insert new page at same position

        self.apply_stylesheet(self.data['style']['theme'], self.data['style']['invert_secondary'], self.data['style']['scale'])
        self.INSTANCES_PAGE.rebuild_grid()

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

            # Density Scale
            'density_scale': density_scale,
        }

        # Apply the wanted stylesheet using custom special properties
        apply_stylesheet(self.application, theme=stylesheet_file_name, css_file=CUSTOM_STYLESHEET_FILE_PATH, extra=extra, invert_secondary=invert_secondary, style='windows11')

        # Set the variables and save them
        self.data['style']['theme'] = stylesheet_file_name
        self.data['style']['invert_secondary'] = invert_secondary
        self.data['style']['scale'] = density_scale

        self.data.save()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow(app)
    window.show()
    sys.exit(app.exec())
