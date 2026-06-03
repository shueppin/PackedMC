# noinspection PyPackageRequirements
from PyQt6.QtWidgets import QStackedWidget, QPushButton, QWidget, QSpinBox, QLineEdit, QComboBox, QFrame, QCheckBox, QTextBrowser

from typing import Literal, overload, Protocol


''' 
Type hints for interrace.ui
'''


class MainWindowElements:
    # Main Page
    PAGE_CONTAINER: QStackedWidget
    INSTANCES_PAGE_BUTTON: QPushButton
    MODS_PAGE_BUTTON: QPushButton
    SETTINGS_PAGE_BUTTON: QPushButton

    # Instances Page Placeholder (replaced by dynamic widget)
    INSTANCES_PAGE_PLACEHOLDER: QWidget

    # Instance edit page
    INSTANCES_BACK_BUTTON: QPushButton
    BROWSE_MINECRAFT_PATH_BUTTON: QPushButton
    INSTANCE_MODS_DISPLAY_CONTAINER: QFrame
    INSTANCE_NAME: QLineEdit
    DELETE_INSTANCE_BUTTON: QPushButton
    INSTANCE_TYPE_SELECTION: QComboBox
    MINECRAFT_DIRECTORY_PATH: QLineEdit
    INSTANCE_VERSION_SELECTION: QComboBox
    ADVANCED_SETTINGS_BUTTON: QPushButton
    USE_STANDARD_OPTIONS: QCheckBox

    # Mods Page Placeholder (replaced by dynamic widget)
    MODS_PAGE_PLACEHOLDER: QWidget

    # Mod edit page
    MOD_NAME: QLineEdit
    MODS_BACK_BUTTON: QPushButton
    MOD_URL: QLineEdit
    MOD_DESCRIPTION: QTextBrowser
    DELETE_MOD_BUTTON: QPushButton
    MOD_VERSIONS: QTextBrowser
    MOD_LOADER: QTextBrowser

    # Settings Page
    STYLES_SELECTION_LIST: QWidget
    SCALE_SELECTION: QSpinBox
    SWITCH_SECONDARY_COLOR: QPushButton


'''
Type hints for the data dictionary and all children
'''


class _StyleDictType(Protocol):
    @overload
    def __getitem__(self, key: Literal["theme"]) -> str: ...
    @overload
    def __setitem__(self, key: Literal["theme"], value: str): ...

    @overload
    def __getitem__(self, key: Literal["invert_secondary"]) -> bool: ...
    @overload
    def __setitem__(self, key: Literal["invert_secondary"], value: bool): ...

    @overload
    def __getitem__(self, key: Literal["scale"]) -> int: ...
    @overload
    def __setitem__(self, key: Literal["scale"], value: int): ...


class _SingleInstanceDictType(Protocol):
    @overload
    def __getitem__(self, key: Literal["type"]) -> str: ...
    @overload
    def __setitem__(self, key: Literal["type"], value: str): ...

    @overload
    def __getitem__(self, key: Literal["version"]) -> str: ...
    @overload
    def __setitem__(self, key: Literal["version"], value: str): ...

    @overload
    def __getitem__(self, key: Literal["is_default"]) -> bool: ...
    @overload
    def __setitem__(self, key: Literal["is_default"], value: bool): ...

    @overload
    def __getitem__(self, key: Literal["minecraft_directory"]) -> str: ...
    @overload
    def __setitem__(self, key: Literal["minecraft_directory"], value: str): ...

    @overload
    def __getitem__(self, key: Literal["use_default_options_file"]) -> bool: ...
    @overload
    def __setitem__(self, key: Literal["use_default_options_file"], value: bool): ...

    @overload
    def __getitem__(self, key: Literal["advanced_arguments"]) -> dict: ...
    @overload
    def __setitem__(self, key: Literal["advanced_arguments"], value: dict): ...

    @overload
    def __getitem__(self, key: Literal["mods"]) -> list[str]: ...
    @overload
    def __setitem__(self, key: Literal["mods"], value: list[str]): ...


class _InstancesDictType(dict[str, _SingleInstanceDictType]):
    ...


class _SingleModDictType(Protocol):
    @overload
    def __getitem__(self, key: Literal["url"]) -> str: ...
    @overload
    def __setitem__(self, key: Literal["url"], value: str): ...

    @overload
    def __getitem__(self, key: Literal["loaders"]) -> list[str]: ...
    @overload
    def __setitem__(self, key: Literal["loaders"], value: list[str]): ...

    @overload
    def __getitem__(self, key: Literal["supported_versions"]) -> list[str]: ...
    @overload
    def __setitem__(self, key: Literal["supported_versions"], value: list[str]): ...


class _ModsDictType(dict[str, _SingleModDictType]):
    ...


class DataDictType(Protocol):
    @overload
    def __getitem__(self, key: Literal["style"]) -> _StyleDictType: ...
    @overload
    def __setitem__(self, key: Literal["style"], value: _StyleDictType): ...

    @overload
    def __getitem__(self, key: Literal["last_played_instance"]) -> str: ...
    @overload
    def __setitem__(self, key: Literal["last_played_instance"], value: str): ...

    @overload
    def __getitem__(self, key: Literal["instances"]) -> _InstancesDictType: ...
    @overload
    def __setitem__(self, key: Literal["instances"], value: _InstancesDictType): ...

    @overload
    def __getitem__(self, key: Literal["mods"]) -> _ModsDictType: ...
    @overload
    def __setitem__(self, key: Literal["mods"], value: _ModsDictType): ...

    def save(self) -> None: ...
    def load(self) -> None: ...
