"""
This file will unify the data.json file and any changes / updates to the data will be ensured using this file.
"""
from .type_hinting import DataDictType
from .file_paths import MINECRAFT_DIRECTORY
from .minecraft_launcher_integration import DEFAULT_MAX_HEAP_SIZE, DEFAULT_START_HEAP_SIZE, DEFAULT_OTHER_JVM_ARGS


# It is important that the following functions are not replaced by constants, so we do not accidentally pass something by reference.
def get_default_data():
    """ The data with which the data.json is initialized """
    default_data = {
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
    return default_data


def get_default_instance_name():
    """ The PackedMC name of the default instance """
    default_instance_name = 'Latest Release'
    return default_instance_name


def get_new_instance_data(instance_type: str, instance_version: str, is_default: bool, minecraft_directory: str, advanced_arguments: dict):
    """ The data filled with values when creating a new instance """
    new_instance_data = {
        'type': instance_type,
        'version': instance_version,
        'is_default': is_default,
        'minecraft_directory': minecraft_directory,
        'use_default_options_file': is_default,  # Use default options file for default instance (obviously), otherwise don't
        'advanced_arguments': advanced_arguments,
        'mods': {}
    }
    return new_instance_data


def get_default_advanced_arguments():
    """ The advanced arguments for the instance """
    default_advanced_arguments = {
        "max_heap_size": DEFAULT_START_HEAP_SIZE,
        "start_heap_size": DEFAULT_MAX_HEAP_SIZE,
        "other_arguments": DEFAULT_OTHER_JVM_ARGS
    }
    return default_advanced_arguments


def get_new_mod_data():
    """ The empty data when adding a new mod """
    new_mod_data = {
        'url': '',
        'loaders': [],
        'supported_versions': [],
    }
    return new_mod_data


def _ensure_instances_data(data_dict: DataDictType):
    for instance_name in data_dict['instances']:
        # Ensure that all instances contain a minecraft directory (Bugfix from Commit 3711122)
        if data_dict['instances'][instance_name]['minecraft_directory'] == '':
            data_dict['instances'][instance_name]['minecraft_directory'] = MINECRAFT_DIRECTORY

        # Ensure that all instances contain at least the default advanced arguments
        if data_dict['instances'][instance_name]['advanced_arguments'] == {}:
            data_dict['instances'][instance_name]['advanced_arguments'] = get_default_advanced_arguments()
        else:
            if 'max_heap_size' not in data_dict['instances'][instance_name]['advanced_arguments']:
                data_dict['instances'][instance_name]['advanced_arguments']['max_heap_size'] = DEFAULT_MAX_HEAP_SIZE
            if 'start_heap_size' not in data_dict['instances'][instance_name]['advanced_arguments']:
                data_dict['instances'][instance_name]['advanced_arguments']['start_heap_size'] = DEFAULT_START_HEAP_SIZE
            if 'other_arguments' not in data_dict['instances'][instance_name]['advanced_arguments'] or data_dict['instances'][instance_name]['advanced_arguments']['other_arguments'] == '':
                data_dict['instances'][instance_name]['advanced_arguments']['other_arguments'] = DEFAULT_OTHER_JVM_ARGS


def ensure_correct_data(data_dict: DataDictType):
    """ This function ensures that every field of the data.json is up to date and correct. """
    _ensure_instances_data(data_dict)
