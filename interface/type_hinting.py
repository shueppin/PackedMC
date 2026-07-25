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
    CLOSE_PACKEDMC_BUTTON: QPushButton


'''
Type hints for the data dictionary and all children
'''


class _SettingsDictType(Protocol):
    @overload
    def __getitem__(self, key: Literal["theme"]) -> str: ...
    @overload
    def __setitem__(self, key: Literal["theme"], value: str): ...

    @overload
    def __getitem__(self, key: Literal["invert_secondary", "close_packedmc"]) -> bool: ...
    @overload
    def __setitem__(self, key: Literal["invert_secondary", "close_packedmc"], value: bool): ...

    @overload
    def __getitem__(self, key: Literal["scale"]) -> int: ...
    @overload
    def __setitem__(self, key: Literal["scale"], value: int): ...


class _AdvancedArgumentsDictType(Protocol):
    @overload
    def __getitem__(self, key: Literal["start_heap_size", "max_heap_size"]) -> int: ...
    @overload
    def __setitem__(self, key: Literal["start_heap_size", "max_heap_size"], value: int): ...

    @overload
    def __getitem__(self, key: Literal["other_arguments"]) -> str: ...
    @overload
    def __setitem__(self, key: Literal["other_arguments"], value: str): ...


class _SingleInstanceDictType(Protocol):
    @overload
    def __getitem__(self, key: Literal["type", "version", "minecraft_directory"]) -> str: ...
    @overload
    def __setitem__(self, key: Literal["type", "version", "minecraft_directory"], value: str): ...

    @overload
    def __getitem__(self, key: Literal["is_default", "use_default_options_file"]) -> bool: ...
    @overload
    def __setitem__(self, key: Literal["is_default", "use_default_options_file"], value: bool): ...

    @overload
    def __getitem__(self, key: Literal["advanced_arguments"]) -> _AdvancedArgumentsDictType: ...
    @overload
    def __setitem__(self, key: Literal["advanced_arguments"], value: _AdvancedArgumentsDictType): ...

    @overload
    def __getitem__(self, key: Literal["mods"]) -> dict[str, tuple[str, str, int]]: ...  # This is a dictionary where all the keys are the version names and the values are the download url, the filename and the timestamp it was last checked
    @overload
    def __setitem__(self, key: Literal["mods"], value: dict[str, tuple[str, str, int]]): ...


class _InstancesDictType(dict[str, _SingleInstanceDictType]):
    ...


class _SingleModDictType(Protocol):
    @overload
    def __getitem__(self, key: Literal["url"]) -> str: ...
    @overload
    def __setitem__(self, key: Literal["url"], value: str): ...

    @overload
    def __getitem__(self, key: Literal["loaders", "supported_versions"]) -> list[str]: ...
    @overload
    def __setitem__(self, key: Literal["loaders", "supported_versions"], value: list[str]): ...


class _ModsDictType(dict[str, _SingleModDictType]):
    ...


class DataDictType(Protocol):
    @overload
    def __getitem__(self, key: Literal["settings"]) -> _SettingsDictType: ...
    @overload
    def __setitem__(self, key: Literal["settings"], value: _SettingsDictType): ...

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
