import os
from platform import platform


# PackedMC Paths
ACTUAL_FILE_DIRECTORY = os.path.dirname(__file__)

INTERFACE_FILE_PATH = os.path.join(ACTUAL_FILE_DIRECTORY, 'ui_files/interface.ui')
CUSTOM_STYLESHEET_FILE_PATH = os.path.join(ACTUAL_FILE_DIRECTORY, 'special_properties.cqss')
ICONS_FILE_PATH = os.path.join(ACTUAL_FILE_DIRECTORY, '../icons')

DATA_FILE_PATH = os.path.join(ACTUAL_FILE_DIRECTORY, r'../data.json')
PACKEDMC_MINECRAFT_DATA_DIRECTORY = os.path.abspath(os.path.join(ACTUAL_FILE_DIRECTORY, '../minecraft_data'))


# Minecraft Paths
if 'windows' in platform().lower():
    ROAMING_DIRECTORY = os.getenv('Appdata')
    MINECRAFT_DIRECTORY = os.path.join(ROAMING_DIRECTORY, '.minecraft')
    MINECRAFT_LAUNCHER_PROFILES_PATH = os.path.join(MINECRAFT_DIRECTORY, 'launcher_profiles.json')
else:
    # TODO: Show a message here and exit
    MINECRAFT_DIRECTORY = 'UNKNOWN'


def is_subdir_of_user_home(path: str) -> bool:
    # Expand ~ and normalize symlinks/relative parts
    p = os.path.realpath(os.path.expanduser(path))
    home = os.path.realpath(os.path.expanduser("~"))

    # True only if p is inside home, not equal to home
    rel = os.path.relpath(p, home)
    return rel != "." and not rel.startswith(".." + os.sep) and rel != ".."
