import os
from platform import platform
from pathlib import Path
import sys


# Most important file paths
MAIN_DIRECTORY = Path(sys.argv[0]).resolve().parent
UPDATER_FILE_PATH = MAIN_DIRECTORY / 'updater.py'
CACHE_DIRECTORY = MAIN_DIRECTORY / '.cache'
BACKUP_DIRECTORY = MAIN_DIRECTORY / "backup"

# Interface paths
INTERFACE_FILES_DIRECTORY = MAIN_DIRECTORY / 'interface'
UI_FILES_DIRECTORY = INTERFACE_FILES_DIRECTORY / 'ui_files'
INTERFACE_FILE_PATH = UI_FILES_DIRECTORY / 'interface.ui'
CUSTOM_STYLESHEET_FILE_PATH = INTERFACE_FILES_DIRECTORY / 'special_properties.cqss'
ICONS_FILE_PATH = MAIN_DIRECTORY / 'icons'

# User data file paths
DATA_FILE_PATH = MAIN_DIRECTORY / r'data.json'
PACKEDMC_MINECRAFT_DATA_DIRECTORY = (MAIN_DIRECTORY / 'minecraft_data').resolve()
PACKEDMC_OPTIONS_FILES_DIRECTORY = PACKEDMC_MINECRAFT_DATA_DIRECTORY / 'options_files'


# Minecraft Paths
if 'windows' in platform().lower():
    ROAMING_DIRECTORY = Path(os.getenv('Appdata'))
    MINECRAFT_DIRECTORY = ROAMING_DIRECTORY / '.minecraft'
    MINECRAFT_LAUNCHER_PROFILES_PATH = MINECRAFT_DIRECTORY / 'launcher_profiles.json'
    VERSIONS_DIRECTORY = MINECRAFT_DIRECTORY / 'versions'
else:
    raise OSError(f'This OS/platform ({platform()}) is not supported by PackedMC.')


def is_subdir_of_user_home(path: str) -> bool:
    # Expand ~ and normalize symlinks/relative parts
    p = os.path.realpath(os.path.expanduser(path))
    home = os.path.realpath(os.path.expanduser("~"))

    # True only if p is inside home, not equal to home
    rel = os.path.relpath(p, home)
    return rel != "." and not rel.startswith(".." + os.sep) and rel != ".."
