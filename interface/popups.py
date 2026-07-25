# noinspection PyPackageRequirements
from PyQt6 import uic
# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QWidget, QDialog, QPushButton, QMainWindow, QTextEdit, QSpinBox

import os


ACTUAL_FILE_DIRECTORY = os.path.dirname(__file__)


class _PopupTemplate(QDialog):
    def __init__(self, file_path: str, parent: QMainWindow):
        """
        Initialises a dialog based on the passed ui file and adding a show_dialog function.
        This is created under the parent, so if the parent is closed, the popup closes too.
        """
        super().__init__(parent)

        # Load the UI file for the popup
        uic.loadUi(file_path, self)

    def show_popup(self, blocking=False):
        # Show the dialog, either with blocking the main application or without blocking the main application.
        if blocking:
            self.exec()
        else:
            self.show()


class ImportProfilesPopup(_PopupTemplate):
    PROFILES_SELECTION_LIST: QWidget
    IMPORT_BUTTON: QPushButton

    def __init__(self, parent: QMainWindow):
        file_path = os.path.join(ACTUAL_FILE_DIRECTORY, 'ui_files/import_profiles_popup.ui')
        super().__init__(file_path, parent)


class AdvancedOptionsPopup(_PopupTemplate):
    START_HEAP_SIZE: QSpinBox
    MAX_HEAP_SIZE: QSpinBox
    OTHER_ARGUMENTS: QTextEdit

    def __init__(self, parent: QMainWindow):
        file_path = os.path.join(ACTUAL_FILE_DIRECTORY, 'ui_files/advanced_options_popup.ui')
        super().__init__(file_path, parent)
