"""
This file will unify the data.json file and any changes / updates to the data will be ensured using this file.
"""
from typing import Any, ClassVar, Final
import logging
import json
import os
from dataclasses import dataclass, field, fields, asdict, InitVar

from file_paths import MINECRAFT_DIRECTORY
from minecraft_launcher_integration import DEFAULT_MAX_HEAP_SIZE, DEFAULT_START_HEAP_SIZE, DEFAULT_OTHER_JVM_ARGS


logger = logging.getLogger(__name__)


DEFAULT_INSTANCE_NAME: Final = 'Latest Release'


class _CompactListEncoder(json.JSONEncoder):
    def iterencode(self, obj, _one_shot=False):
        # Use custom separators for lists only
        return self._iterencode(obj, 0)

    def _iterencode(self, obj, level):
        indent = self.indent
        newline = "\n"
        space = " "

        if isinstance(obj, dict):
            if not obj:
                yield "{}"
                return

            yield "{"
            items = list(obj.items())
            for i, (key, value) in enumerate(items):
                yield newline + space * (indent * (level + 1))
                yield json.dumps(key)
                yield ": "
                yield from self._iterencode(value, level + 1)
                if i < len(items) - 1:
                    yield ","
            yield newline + space * (indent * level) + "}"

        elif isinstance(obj, list):
            # ALWAYS compact lists
            yield json.dumps(obj, separators=(", ", ":"), ensure_ascii=self.ensure_ascii)

        else:
            yield json.dumps(obj, ensure_ascii=self.ensure_ascii)


@dataclass
class _DataBase:
    """
    The base functionality to allow updating the data of the instances and their attributes using a dictionary
    """

    _dataclass_attributes: ClassVar[dict[str, type[_DataBase]]] = {}  # The attribute name and the corresponding dataclass
    _dictionary_dataclass_attributes: ClassVar[dict[str, type[_DataBase]]] = {}  # The attribute name and the corresponding dataclass

    def update_from_dict(self, data_dictionary: dict[str, Any]):
        all_attributes = set(class_field.name for class_field in fields(self))

        # Update complex attributes (they are a dataclass themselves)
        for attribute_name, corresponding_class in self._dataclass_attributes.items():
            all_attributes.remove(attribute_name)
            if attribute_name in data_dictionary:
                class_instance = corresponding_class()
                class_instance.update_from_dict(data_dictionary[attribute_name])
                setattr(self, attribute_name, class_instance)

        # Update attributes where the data is a dictionary with strings as keys and dataclasses as values
        for attribute_name, corresponding_class in self._dictionary_dataclass_attributes.items():
            all_attributes.remove(attribute_name)
            if attribute_name in data_dictionary:
                if not isinstance(data_dictionary[attribute_name], dict):
                    logger.warning(f'Attribute Warning: {attribute_name} attribute in data_dictionary is not a dictionary')
                    continue

                output_dict = {}
                for key, value in data_dictionary[attribute_name].items():
                    class_instance = corresponding_class()
                    class_instance.update_from_dict(value)
                    output_dict[key] = class_instance

                setattr(self, attribute_name, output_dict)

        # Update primitive attributes (like int, float, str or even simple lists or dictionaries)
        for attribute_name in all_attributes:  # This will go through all the remaining attributes
            if attribute_name in data_dictionary:
                setattr(self, attribute_name, data_dictionary[attribute_name])

        self.ensure_correct_data()  # Make sure the data is how it should be after updating it.

    def ensure_correct_data(self):
        """
        This function is for children who need to ensure correct data after it was updated. If not overridden, it has no effect.
        """
        pass


@dataclass
class SettingsData(_DataBase):
    theme: str = field(default='green')
    invert_secondary: bool = field(default=False)
    use_dark_theme: bool = field(default=True)
    scale: int = field(default=0)
    close_packedmc: bool = field(default=False)

    def ensure_correct_data(self):
        if '.xml' in self.theme:
            self.theme = 'green'


@dataclass
class SingleModData(_DataBase):
    url: str = field(default='')
    loaders: list[str] = field(default_factory=list)
    supported_versions: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class AdvancedArgumentsData(_DataBase):
    start_heap_size: int = field(default=DEFAULT_START_HEAP_SIZE)
    max_heap_size: int = field(default=DEFAULT_MAX_HEAP_SIZE)
    other_arguments: str = field(default=DEFAULT_OTHER_JVM_ARGS)


@dataclass
class SingleInstanceData(_DataBase):
    _dataclass_attributes: ClassVar = {'advanced_arguments': AdvancedArgumentsData}  # The attribute name and the corresponding dataclass

    type: str = field(default='')
    version: str = field(default='')
    is_default: bool = field(default=False)
    minecraft_directory: str = field(default=MINECRAFT_DIRECTORY)
    use_default_options_file: bool = field(default=False)
    advanced_arguments: AdvancedArgumentsData = field(default_factory=AdvancedArgumentsData)
    mods: dict[str, tuple[str, str, int]] = field(default_factory=dict)


@dataclass
class Data(_DataBase):
    filepath: InitVar[str]

    _dataclass_attributes: ClassVar = {'settings': SettingsData}  # The attribute name and the corresponding dataclass
    _dictionary_dataclass_attributes: ClassVar = {'mods': SingleModData, 'instances': SingleInstanceData}  # The attribute name and the corresponding dataclass

    settings: SettingsData = field(default_factory=SettingsData)
    last_played_instance: str = field(default='')
    instances: dict[str, SingleInstanceData] = field(default_factory=dict)
    mods: dict[str, SingleModData] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    # Special functionality to be able to save and load
    def __post_init__(self, filepath: str):  # This is run after the init from the dataclass
        # Store the filepath
        self._filepath = filepath

        # Load existing data if the file exists
        if os.path.exists(filepath):
            self.load()
            pass

        self.save()

    def load(self):
        try:
            with open(self._filepath, "r") as f:
                loaded_data = json.load(f)
                self.update_from_dict(loaded_data)
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Error loading dictionary: {e}")

    def save(self):
        output_dictionary = asdict(self)
        try:
            with open(self._filepath, "w") as f:
                json.dump(
                    output_dictionary,
                    f,
                    cls=_CompactListEncoder,
                    indent=4
                )
        except IOError as e:
            logger.error(f"Error saving dictionary: {e}")
