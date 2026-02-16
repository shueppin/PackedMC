from PyQt6.QtWidgets import QStackedWidget, QPushButton, QWidget, QSpinBox


class MainWindowElements:
    # Main Page
    PAGE_CONTAINER: QStackedWidget
    INSTANCES_PAGE_BUTTON: QPushButton
    MODS_PAGE_BUTTON: QPushButton
    SETTINGS_PAGE_BUTTON: QPushButton

    # Instances Page Placeholder (replaced by dynamic widget)
    INSTANCES_PAGE_PLACEHOLDER: QWidget

    # Settings Page
    STYLES_SELECTION_LIST: QWidget
    SCALE_SELECTION: QSpinBox
    SWITCH_SECONDARY_COLOR: QPushButton