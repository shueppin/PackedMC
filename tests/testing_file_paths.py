"""
Replacement for ``utils/file_paths.py`` while running the tests.

``tests/conftest.py`` registers this module as ``sys.modules['utils.file_paths']`` BEFORE any PackedMC module is
imported. That means every ``from utils.file_paths import SOMETHING`` in the project transparently receives the value
from this file, without having to patch each module separately.

Rules for this file:
* It must define every name the real ``utils/file_paths.py`` defines (``test_environment.py`` checks that, so you notice
  when a path is added to the real file but not here).
* Everything the application WRITES to (data, cache, backups, the Minecraft directory...) points into
  ``TESTING_DIRECTORY``, which is wiped before every test.
* Files the application only READS and which ship with the project (the .ui files, the icons, the stylesheet) keep
  pointing at the real project directory.
"""
import os
from pathlib import Path


_TESTS_DIRECTORY = Path(__file__).resolve().parent
PROJECT_DIRECTORY = _TESTS_DIRECTORY.parent

# Everything below this directory is created / deleted by the tests. It is fine to look inside after a failed test.
TESTING_DIRECTORY = _TESTS_DIRECTORY / 'testing_directory'
# The conftest sets HOME / USERPROFILE to this directory, so that "is_subdir_of_user_home" behaves as on a real machine.
FAKE_HOME_DIRECTORY = TESTING_DIRECTORY / 'home'


# Most important file paths
MAIN_DIRECTORY = FAKE_HOME_DIRECTORY / 'PackedMC'
UPDATER_FILE_PATH = MAIN_DIRECTORY / 'updater.py'
CACHE_DIRECTORY = MAIN_DIRECTORY / '.cache'
BACKUP_DIRECTORY = MAIN_DIRECTORY / "backup"
VERSION_HISTORY = MAIN_DIRECTORY / "version_history.json"

# Interface paths. These are read-only resources of the project, so they stay at their real location.
INTERFACE_FILES_DIRECTORY = PROJECT_DIRECTORY / 'interface'
UI_FILES_DIRECTORY = INTERFACE_FILES_DIRECTORY / 'ui_files'
INTERFACE_FILE_PATH = UI_FILES_DIRECTORY / 'interface.ui'
CUSTOM_STYLESHEET_FILE_PATH = INTERFACE_FILES_DIRECTORY / 'special_properties.cqss'
ICONS_FILE_PATH = PROJECT_DIRECTORY / 'icons'

# User data file paths
DATA_FILE_PATH = MAIN_DIRECTORY / r'data.json'
PACKEDMC_MINECRAFT_DATA_DIRECTORY = (MAIN_DIRECTORY / 'minecraft_data').resolve()
PACKEDMC_OPTIONS_FILES_DIRECTORY = PACKEDMC_MINECRAFT_DATA_DIRECTORY / 'options_files'


# Minecraft Paths (the platform check of the real file is left out, so the tests can run anywhere)
ROAMING_DIRECTORY = FAKE_HOME_DIRECTORY / 'AppData' / 'Roaming'
MINECRAFT_DIRECTORY = ROAMING_DIRECTORY / '.minecraft'
MINECRAFT_LAUNCHER_PROFILES_PATH = MINECRAFT_DIRECTORY / 'launcher_profiles.json'
VERSIONS_DIRECTORY = MINECRAFT_DIRECTORY / 'versions'


def is_subdir_of_user_home(path: str) -> bool:
    # Expand ~ and normalize symlinks/relative parts
    p = os.path.realpath(os.path.expanduser(path))
    home = os.path.realpath(os.path.expanduser("~"))

    # True only if p is inside home, not equal to home
    rel = os.path.relpath(p, home)
    return rel != "." and not rel.startswith(".." + os.sep) and rel != ".."


'''
Additional values which only exist for the tests
'''
# Names from above that intentionally do NOT point into the testing directory.
REAL_RESOURCE_NAMES = frozenset({
    'INTERFACE_FILES_DIRECTORY',
    'UI_FILES_DIRECTORY',
    'INTERFACE_FILE_PATH',
    'CUSTOM_STYLESHEET_FILE_PATH',
    'ICONS_FILE_PATH',
})

# Directories which exist on a machine where PackedMC and the Minecraft Launcher were used before.
# They are recreated after each wipe of the testing directory. (Directories that the project creates itself at import
# time are detected automatically by the conftest.)
REQUIRED_DIRECTORIES = (
    MAIN_DIRECTORY,
    CACHE_DIRECTORY,
    BACKUP_DIRECTORY,  # Normally created by updater.py
    PACKEDMC_MINECRAFT_DATA_DIRECTORY,
    PACKEDMC_OPTIONS_FILES_DIRECTORY,
    MINECRAFT_DIRECTORY,
    VERSIONS_DIRECTORY,
)
