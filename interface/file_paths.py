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
