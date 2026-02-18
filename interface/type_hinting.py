from PyQt6.QtWidgets import QStackedWidget, QPushButton, QWidget, QSpinBox, QLineEdit, QComboBox, QFrame, QCheckBox


class MainWindowElements:
    # Main Page
    PAGE_CONTAINER: QStackedWidget
    INSTANCES_PAGE_BUTTON: QPushButton
    MODS_PAGE_BUTTON: QPushButton
    SETTINGS_PAGE_BUTTON: QPushButton

    # Instances Page Placeholder (replaced by dynamic widget)
    INSTANCES_PAGE_PLACEHOLDER: QWidget

    # Instance edit page
    BACK_BUTTON: QPushButton
    BROWSE_MINECRAFT_PATH_BUTTON: QPushButton
    INSTANCE_MODS_PLACEHOLDER: QFrame
    INSTANCE_NAME: QLineEdit
    DELETE_INSTANCE_BUTTON: QPushButton
    INSTANCE_TYPE_SELECTION: QComboBox
    MINECRAFT_DIRECTORY_PATH: QLineEdit
    VERSION_SELECTION: QComboBox
    ADVANCED_SETTINGS_BUTTON: QPushButton
    USE_STANDARD_OPTIONS: QCheckBox

    # Settings Page
    STYLES_SELECTION_LIST: QWidget
    SCALE_SELECTION: QSpinBox
    SWITCH_SECONDARY_COLOR: QPushButton