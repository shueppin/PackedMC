"""
Tests for everything the instance pages of the UI call (interface/instance_page.py), executed through the real MainWindow.
"""
import json
import sys

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton

from . import testing_file_paths as paths
from .helpers import (
    click_button_in, directory_listing, find_field, make_data_file_contents, make_instance_dict, make_launcher_profile, make_mod_dict,
    read_data_file, read_launcher_profiles, write_launcher_profiles, write_text,
)

DEFAULT = 'Latest Release'
OPTIONS_DIRECTORY = paths.PACKEDMC_OPTIONS_FILES_DIRECTORY
MODS_DIRECTORY = paths.PACKEDMC_MINECRAFT_DATA_DIRECTORY / 'mods'
MINECRAFT_OPTIONS = paths.MINECRAFT_DIRECTORY / 'options.txt'

FABRIC_API = make_mod_dict('https://modrinth.com/mod/fabric-api', loaders=['Fabric', 'Forge'], supported_versions=['1.21.4'])
SODIUM = make_mod_dict('https://modrinth.com/mod/sodium', loaders=['Fabric'])
JEI = make_mod_dict('https://www.curseforge.com/minecraft/mc-mods/jei', loaders=['Forge'])
OLD_MOD = make_mod_dict('https://modrinth.com/mod/old-mod', loaders=['Fabric'])


@pytest.fixture
def window(make_main_window):
    """ A window with the default instance, a normal release instance and a Fabric instance with two mods. """
    return make_main_window(make_data_file_contents(
        instances={
            DEFAULT: make_instance_dict(is_default=True),
            'Survival': make_instance_dict(type='Release', version='1.20.1'),
            'Modded': make_instance_dict(type='Fabric', version='1.21.4', mods={'Fabric API': ['', '', 0], 'Sodium': ['', '', 0]}),
        },
        mods={'Fabric API': FABRIC_API, 'Sodium': SODIUM, 'JEI': JEI},
        last_played_instance=DEFAULT,
    ))


@pytest.fixture
def pages(window):
    return window.instance_page_class


# ======================================================================================================= play_instance
def test_playing_a_release_instance_prepares_the_official_launcher(window, pages, subprocesses, fake_internet, dialogs):
    write_launcher_profiles()
    write_text(OPTIONS_DIRECTORY / 'Survival.txt', 'fov:100.0')

    pages.play_instance('Survival')

    profile = read_launcher_profiles()['profiles']['packedmc']
    assert (profile['name'], profile['lastVersionId'], profile['gameDir']) == ('PackedMC - Survival', '1.20.1', str(paths.MINECRAFT_DIRECTORY))
    assert MINECRAFT_OPTIONS.read_text() == 'fov:100.0'
    assert subprocesses.commands() == [r'explorer.exe shell:AppsFolder\Microsoft.4297127D64EC6_8wekyb3d8bbwe!Minecraft']
    assert window.data.last_played_instance == 'Survival'
    assert read_data_file()['last_played_instance'] == 'Survival'
    assert not dialogs.messages
    fake_internet.assert_no_requests()  # Release instances need no mods and no downloads
    assert not (MODS_DIRECTORY / 'Survival').exists()


def test_playing_saves_the_options_of_the_previously_played_instance(window, pages):
    write_launcher_profiles({'packedmc': make_launcher_profile(name='PackedMC - Latest Release', last_used='2026-01-01T00:00:00.000Z')})
    write_text(MINECRAFT_OPTIONS, 'options of the default instance')

    pages.play_instance('Survival')

    assert (OPTIONS_DIRECTORY / f'{DEFAULT}.txt').read_text() == 'options of the default instance'


def test_the_favourite_star_in_the_name_is_ignored(window, pages):
    write_launcher_profiles()
    pages.play_instance('★ Survival')
    assert window.data.last_played_instance == 'Survival'


def test_playing_a_fabric_instance_downloads_and_moves_the_mods(window, pages, fake_internet, subprocesses, dialogs):
    write_launcher_profiles()

    pages.play_instance('Modded')

    # Fabric loader is installed for the launcher
    profile = read_launcher_profiles()['profiles']['packedmc']
    assert profile['lastVersionId'] == 'fabric-loader-0.16.9-1.21.4'
    assert (paths.VERSIONS_DIRECTORY / 'fabric-loader-0.16.9-1.21.4' / 'fabric-loader-0.16.9-1.21.4.jar').exists()
    # Mods are downloaded to PackedMC and copied to Minecraft
    packedmc_files = ['fabric-api-0.115.0-1.21.4.jar', 'sodium-fabric-0.6.0-1.21.4.jar']
    assert directory_listing(MODS_DIRECTORY / 'Modded') == packedmc_files
    assert directory_listing(paths.MINECRAFT_DIRECTORY / 'mods') == sorted(packedmc_files + ['packedmc.json'])
    assert sorted(json.loads((paths.MINECRAFT_DIRECTORY / 'mods' / 'packedmc.json').read_text())) == packedmc_files
    # Exactly these URLs were requested
    for url in ('https://api.modrinth.com/v2/project/fabric-api/version', 'https://api.modrinth.com/v2/project/sodium/version',
                'https://cdn.modrinth.com/data/P7dR8mSH/versions/v1214/fabric-api-0.115.0-1.21.4.jar',
                'https://cdn.modrinth.com/data/AANobbMI/versions/s1214/sodium-fabric-0.6.0-1.21.4.jar'):
        fake_internet.assert_requested(url)
    fake_internet.assert_not_requested('https://api.modrinth.com/v2/project/jei/version')
    assert len(subprocesses.calls) == 1
    assert not dialogs.messages  # All mods were found


def test_mods_without_file_for_the_version_are_listed_in_a_message(window, pages, dialogs):
    window.data.mods['Old Mod'] = __import__('utils.data_file_helper', fromlist=['SingleModData']).SingleModData(url=OLD_MOD['url'], loaders=['Fabric'])
    window.data.instances['Modded'].mods['Old Mod'] = ('', '', 0)
    write_launcher_profiles()

    pages.play_instance('Modded')

    assert [m.title for m in dialogs.of_kind('information')] == ['Could not find all mods']
    assert 'Old Mod' in dialogs.last.text and 'Fabric 1.21.4' in dialogs.last.text
    assert 'Sodium' not in dialogs.last.text


def test_an_error_in_one_mod_download_does_not_prevent_the_other_mods(window, pages, fake_internet):
    write_launcher_profiles()
    fake_internet.add_route('https://api.modrinth.com/v2/project/sodium/version', file='modrinth_versions_sodium.json', headers={'X-Ratelimit-Remaining': '0'})

    pages.play_instance('Modded')

    assert directory_listing(paths.MINECRAFT_DIRECTORY / 'mods') == ['fabric-api-0.115.0-1.21.4.jar', 'packedmc.json']


def test_playing_is_refused_while_the_minecraft_launcher_runs(window, pages, running_processes, subprocesses, dialogs):
    write_launcher_profiles()
    running_processes.extend(['explorer.exe', 'MinecraftLauncher.exe'])

    pages.play_instance('Survival')

    assert dialogs.last.kind == 'warning' and dialogs.last.title == 'Could not play'
    assert 'MinecraftLauncher.exe' in dialogs.last.text
    assert subprocesses.calls == []
    assert window.data.last_played_instance == DEFAULT
    assert 'packedmc' not in read_launcher_profiles()['profiles']


@pytest.mark.parametrize('directory', [
    paths.FAKE_HOME_DIRECTORY / 'does-not-exist',  # Inside of home but missing
    paths.TESTING_DIRECTORY,  # Exists but outside of the (fake) home directory
], ids=['missing', 'outside_home'])
def test_playing_is_refused_for_an_invalid_minecraft_directory(window, pages, subprocesses, dialogs, directory):
    write_launcher_profiles()
    window.data.instances['Survival'].minecraft_directory = str(directory)

    pages.play_instance('Survival')

    assert dialogs.last.kind == 'warning' and dialogs.last.title == 'Could not play'
    assert subprocesses.calls == []
    assert 'packedmc' not in read_launcher_profiles()['profiles']


def test_packedmc_closes_after_playing_if_the_setting_is_enabled(window, pages, subprocesses):
    write_launcher_profiles()
    window.data.settings.close_packedmc = True

    with pytest.raises(SystemExit):
        pages.play_instance('Survival')

    assert len(subprocesses.calls) == 1  # Everything was done before closing
    assert read_data_file()['last_played_instance'] == 'Survival'


def test_pressing_play_on_an_instance_card_starts_the_game(window, subprocesses):
    write_launcher_profiles()
    window.show_page(0, show_instantly=True)

    click_button_in(find_field(window.INSTANCES_PAGE, 'Survival'), 'Play')

    assert read_launcher_profiles()['profiles']['packedmc']['name'] == 'PackedMC - Survival'
    assert len(subprocesses.calls) == 1


@pytest.mark.xfail(reason='BUG: last_played_instance is not reset when its instance is deleted. The next "Play" then crashes with a KeyError, '
                          'because the options of the last played instance are saved first.')
def test_playing_after_deleting_the_last_played_instance_works(window, pages, dialogs):
    write_launcher_profiles()
    pages.play_instance('Survival')
    pages.edit_instance('Survival')
    dialogs.answer_yes()
    window.DELETE_INSTANCE_BUTTON.click()
    assert 'Survival' not in window.data.instances

    pages.play_instance('Modded')

    assert window.data.last_played_instance == 'Modded'


@pytest.mark.xfail(reason='BUG: Same cause as above. If the last played instance was deleted, the next start of PackedMC raises a KeyError in MainWindow.__init__.')
def test_starting_packedmc_after_deleting_the_last_played_instance_works(window, pages, dialogs, make_main_window):
    write_launcher_profiles()
    pages.play_instance('Survival')
    pages.edit_instance('Survival')
    dialogs.answer_yes()
    window.DELETE_INSTANCE_BUTTON.click()

    restarted = make_main_window()  # Reads the existing data.json

    assert restarted.data.instances


# ===================================================================================================== create_instance
def test_create_instance_uses_sensible_defaults_and_saves(window, pages):
    pages.create_instance(edit_afterwards=False)

    instance = read_data_file()['instances']['New instance']
    assert (instance['type'], instance['version'], instance['is_default']) == ('Release', 'latest', False)
    assert instance['minecraft_directory'] == str(paths.MINECRAFT_DIRECTORY)
    assert instance['mods'] == {} and instance['is_favourite'] is False


def test_create_instance_makes_names_unique(window, pages):
    pages.create_instance(edit_afterwards=False)
    pages.create_instance(edit_afterwards=False)
    pages.create_instance('New instance', edit_afterwards=False)

    names = [name for name in window.data.instances if name.startswith('New instance')]
    assert names == ['New instance', 'New instance 2', 'New instance 3']


def test_create_instance_with_custom_values(window, pages):
    custom_directory = paths.FAKE_HOME_DIRECTORY / 'elsewhere'

    pages.create_instance('Custom', is_default=True, edit_afterwards=False, instance_type='Fabric', instance_version='1.20.1', minecraft_directory=str(custom_directory))

    instance = window.data.instances['Custom']
    assert (instance.type, instance.version, instance.is_default, instance.minecraft_directory) == ('Fabric', '1.20.1', True, str(custom_directory))


def test_create_instance_opens_the_edit_page_by_default(window, pages, qtbot):
    pages.create_instance('Fresh')

    assert pages.selected_instance_name == 'Fresh'
    assert window.INSTANCE_NAME.text() == 'Fresh'
    qtbot.waitUntil(lambda: window.PAGE_CONTAINER.currentIndex() == 1, timeout=3000)


def test_the_create_new_instance_card_creates_an_instance(window, qtbot):
    window.show_page(0, show_instantly=True)
    buttons = [f for f in window.INSTANCES_PAGE.fields if isinstance(f, QPushButton) and f.text().startswith('Create new')]

    buttons[0].click()

    assert 'New instance' in window.data.instances


# ======================================================================================================= edit_instance
def test_edit_instance_shows_the_values_of_the_instance(window, pages):
    window.data.instances['Survival'].is_favourite = True
    window.data.instances['Survival'].use_default_options_file = True

    pages.edit_instance('Survival')

    assert window.INSTANCE_NAME.text() == 'Survival'
    assert window.INSTANCE_TYPE_SELECTION.currentText() == 'Release'
    assert window.INSTANCE_VERSION_SELECTION.currentText() == '1.20.1'
    assert window.USE_STANDARD_OPTIONS.isChecked()
    assert window.MINECRAFT_DIRECTORY_PATH.text() == str(paths.MINECRAFT_DIRECTORY)
    assert window.INSTANCE_FAVOURITE_BUTTON.isChecked()
    assert window.DELETE_INSTANCE_BUTTON.text() == 'Delete'
    assert all(widget.isEnabled() for widget in (window.INSTANCE_TYPE_SELECTION, window.INSTANCE_VERSION_SELECTION, window.USE_STANDARD_OPTIONS))
    assert pages.selected_instance_name == 'Survival'


def test_edit_instance_offers_the_versions_of_the_type(window, pages):
    def versions():
        return [window.INSTANCE_VERSION_SELECTION.itemText(i) for i in range(window.INSTANCE_VERSION_SELECTION.count())]

    pages.edit_instance('Survival')
    assert versions() == ['latest', '1.21.4', '1.21.3', '1.20.1', '1.19.4']

    window.data.instances['Survival'].type = 'Snapshot'
    pages.edit_instance('Survival')
    assert versions() == ['latest', '25w06a', '24w14a']

    (paths.MINECRAFT_DIRECTORY / 'versions' / '1.8.9-custom').mkdir(parents=True)
    window.data.instances['Survival'].type = 'Other'
    pages.edit_instance('Survival')
    assert versions() == ['1.8.9-custom']


def test_unknown_version_falls_back_to_latest(window, pages):
    window.data.instances['Survival'].version = '0.0.1'
    pages.edit_instance('Survival')
    assert window.INSTANCE_VERSION_SELECTION.currentText() == 'latest'


def test_the_default_instance_is_reset_instead_of_deleted_and_cannot_change_type(window, pages):
    pages.edit_instance(DEFAULT)

    assert window.DELETE_INSTANCE_BUTTON.text() == 'Reset'
    assert not window.INSTANCE_TYPE_SELECTION.isEnabled()
    assert not window.INSTANCE_VERSION_SELECTION.isEnabled()
    assert not window.USE_STANDARD_OPTIONS.isEnabled()


def test_edit_instance_lists_the_mods_matching_the_type_and_downloads_their_icons(window, pages, fake_internet):
    pages.edit_instance('Modded')

    icon = paths.CACHE_DIRECTORY / 'modrinth_mods'
    assert window.INSTANCE_MODS_DISPLAY.values == [
        ('Fabric API', icon / 'fabric-api.png', True),
        ('Sodium', icon / 'sodium.png', True),
    ]  # JEI only supports Forge
    assert (icon / 'fabric-api.png').exists() and (icon / 'sodium.png').exists()
    fake_internet.assert_requested('https://cdn.modrinth.com/data/P7dR8mSH/icon.png')
    fake_internet.assert_requested('https://cdn.modrinth.com/data/AANobbMI/icon.png')


def test_edit_instance_marks_only_selected_mods(window, pages):
    del window.data.instances['Modded'].mods['Sodium']
    pages.edit_instance('Modded')
    assert [(name, selected) for name, _, selected in window.INSTANCE_MODS_DISPLAY.values] == [('Fabric API', True), ('Sodium', False)]


def test_edit_instance_survives_mods_from_unsupported_websites(window, pages):
    window.data.mods['Weird'] = __import__('utils.data_file_helper', fromlist=['SingleModData']).SingleModData(url='https://example.com/x', loaders=['Fabric'])
    pages.edit_instance('Modded')
    assert ('Weird', '', False) in window.INSTANCE_MODS_DISPLAY.values


def test_clicking_a_displayed_mod_selects_and_deselects_it(window, pages, qtbot):
    pages.edit_instance('Survival')
    window.data.instances['Survival'].type = 'Fabric'
    pages.edit_instance('Survival')
    window.INSTANCE_MODS_DISPLAY.resize(900, 500)

    qtbot.mouseClick(find_field(window.INSTANCE_MODS_DISPLAY, 'Sodium'), Qt.MouseButton.LeftButton)
    assert read_data_file()['instances']['Survival']['mods'] == {'Sodium': ['', '', 0]}

    qtbot.mouseClick(find_field(window.INSTANCE_MODS_DISPLAY, 'Sodium'), Qt.MouseButton.LeftButton)
    assert read_data_file()['instances']['Survival']['mods'] == {}


# =================================================================================================== renaming (name field)
def test_renaming_an_instance_moves_its_data_and_options_file(window, pages):
    write_text(OPTIONS_DIRECTORY / 'Survival.txt', 'fov:100.0')
    pages.edit_instance('Survival')

    window.INSTANCE_NAME.setText('Creative')

    stored = read_data_file()
    assert 'Survival' not in stored['instances'] and stored['instances']['Creative']['version'] == '1.20.1'
    assert pages.selected_instance_name == 'Creative'
    assert directory_listing(OPTIONS_DIRECTORY) == ['Creative.txt']


def test_renaming_the_last_played_instance_updates_the_last_played_name(window, pages):
    window.data.last_played_instance = 'Survival'
    pages.edit_instance('Survival')

    window.INSTANCE_NAME.setText('Creative')

    assert read_data_file()['last_played_instance'] == 'Creative'


@pytest.mark.parametrize('typed, expected', [
    ('★ Cre?ative:*', 'Creative'),  # Characters the explorer or the favourite marker could not handle
    ('', 'Instance Name'),
    ('???', 'Instance Name'),
    ('Modded', 'Modded 2'),  # Already taken
])
def test_instance_names_are_cleaned_and_made_unique(window, pages, typed, expected):
    pages.edit_instance('Survival')

    window.INSTANCE_NAME.setText(typed)

    assert expected in window.data.instances and 'Survival' not in window.data.instances


# ========================================================================================================== deleting
def test_deleting_an_instance_asks_and_removes_it(window, pages, dialogs):
    pages.edit_instance('Survival')
    dialogs.answer_yes()

    window.DELETE_INSTANCE_BUTTON.click()

    assert dialogs.last.title == 'Confirm deletion' and '"Survival"' in dialogs.last.text
    assert 'Survival' not in read_data_file()['instances']
    assert 'Survival' not in window.INSTANCES_PAGE.values  # Back on the instances page


def test_declining_the_deletion_keeps_the_instance(window, pages, dialogs):
    pages.edit_instance('Survival')
    dialogs.answer_no()

    window.DELETE_INSTANCE_BUTTON.click()

    assert 'Survival' in read_data_file()['instances']


def test_resetting_the_default_instance_recreates_it_with_default_values(window, pages, dialogs):
    window.data.instances['My Default'] = window.data.instances.pop(DEFAULT)
    window.data.instances['My Default'].version = '1.19.4'
    write_text(OPTIONS_DIRECTORY / 'My Default.txt', 'default options')
    pages.edit_instance('My Default')
    dialogs.answer_yes()

    window.DELETE_INSTANCE_BUTTON.click()

    instances = read_data_file()['instances']
    assert 'My Default' not in instances
    assert (instances[DEFAULT]['is_default'], instances[DEFAULT]['version']) == (True, 'latest')
    assert directory_listing(OPTIONS_DIRECTORY) == [f'{DEFAULT}.txt']  # The options moved to the new name
    assert 'Confirm resetting' in dialogs.last.title


def test_declining_the_reset_keeps_the_default_instance(window, pages, dialogs):
    window.data.instances[DEFAULT].version = '1.19.4'
    window.data.save()
    pages.edit_instance(DEFAULT)
    dialogs.answer_no()

    window.DELETE_INSTANCE_BUTTON.click()

    assert read_data_file()['instances'][DEFAULT]['version'] == '1.19.4'


# ===================================================================================================== type and version
def test_changing_the_type_deselects_incompatible_mods(window, pages, dialogs):
    window.data.instances['Modded'].mods['Fabric API'] = ('', '', 0)
    pages.edit_instance('Modded')
    dialogs.answer_yes()

    window.INSTANCE_TYPE_SELECTION.setCurrentText('Forge')

    instance = read_data_file()['instances']['Modded']
    assert instance['type'] == 'Forge'
    assert list(instance['mods']) == ['Fabric API']  # Fabric API supports Fabric and Forge, Sodium only Fabric
    assert 'from Fabric to Forge' in dialogs.last.text and 'Incompatible mods will be deselected.' in dialogs.last.text


def test_changing_from_a_loader_to_vanilla_deselects_all_mods(window, pages, dialogs):
    pages.edit_instance('Modded')
    dialogs.answer_yes()

    window.INSTANCE_TYPE_SELECTION.setCurrentText('Release')

    assert read_data_file()['instances']['Modded']['mods'] == {}
    assert 'All mods will be deselected.' in dialogs.last.text


def test_changing_the_type_refreshes_the_version_list(window, pages, dialogs):
    pages.edit_instance('Survival')
    dialogs.answer_yes()

    window.INSTANCE_TYPE_SELECTION.setCurrentText('Snapshot')

    assert [window.INSTANCE_VERSION_SELECTION.itemText(i) for i in range(window.INSTANCE_VERSION_SELECTION.count())] == ['latest', '25w06a', '24w14a']


def test_declining_the_type_change_restores_the_old_type(window, pages, dialogs):
    pages.edit_instance('Modded')
    dialogs.answer_no()

    window.INSTANCE_TYPE_SELECTION.setCurrentText('Release')

    assert window.INSTANCE_TYPE_SELECTION.currentText() == 'Fabric'
    stored = read_data_file()['instances']['Modded']
    assert stored['type'] == 'Fabric' and set(stored['mods']) == {'Fabric API', 'Sodium'}


def test_changing_the_version_is_saved_and_forces_a_mod_recheck(window, pages):
    window.data.instances['Modded'].mods['Sodium'] = ['https://x/s.jar', 's.jar', 1234567]
    pages.edit_instance('Modded')

    window.INSTANCE_VERSION_SELECTION.setCurrentText('1.20.1')

    stored = read_data_file()['instances']['Modded']
    assert stored['version'] == '1.20.1'
    assert stored['mods']['Sodium'] == ['https://x/s.jar', 's.jar', 0]


def test_the_default_options_checkbox_is_saved(window, pages):
    pages.edit_instance('Survival')

    window.USE_STANDARD_OPTIONS.click()
    assert read_data_file()['instances']['Survival']['use_default_options_file'] is True

    window.USE_STANDARD_OPTIONS.click()
    assert read_data_file()['instances']['Survival']['use_default_options_file'] is False


def test_the_favourite_button_toggles_and_saves(window, pages):
    pages.edit_instance('Survival')

    window.INSTANCE_FAVOURITE_BUTTON.click()
    assert read_data_file()['instances']['Survival']['is_favourite'] is True

    window.INSTANCE_FAVOURITE_BUTTON.click()
    assert read_data_file()['instances']['Survival']['is_favourite'] is False


# ============================================================================================================== path
@pytest.mark.skipif(sys.platform != 'win32', reason='The code converts "/" to "\\" in the selected path, which is only meaningful on Windows.')
def test_browsing_for_a_minecraft_directory(window, pages, dialogs):
    new_directory = paths.FAKE_HOME_DIRECTORY / 'other_minecraft'
    new_directory.mkdir()
    dialogs.existing_directory = str(new_directory).replace('\\', '/')  # Qt returns forward slashes
    pages.edit_instance('Survival')

    window.BROWSE_MINECRAFT_PATH_BUTTON.click()

    assert read_data_file()['instances']['Survival']['minecraft_directory'] == str(new_directory)
    assert window.MINECRAFT_DIRECTORY_PATH.text() == str(new_directory)
    assert dialogs.file_dialog_calls[0][0] == 'getExistingDirectory'


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows path handling.')
def test_browsing_for_a_directory_outside_of_home_is_ignored(window, pages, dialogs):
    dialogs.existing_directory = str(paths.TESTING_DIRECTORY.parent).replace('\\', '/')
    pages.edit_instance('Survival')

    window.BROWSE_MINECRAFT_PATH_BUTTON.click()

    assert read_data_file()['instances']['Survival']['minecraft_directory'] == str(paths.MINECRAFT_DIRECTORY)


def test_cancelling_the_directory_dialog_changes_nothing(window, pages, dialogs):
    dialogs.existing_directory = ''  # What Qt returns on cancel
    pages.edit_instance('Survival')

    window.BROWSE_MINECRAFT_PATH_BUTTON.click()

    assert read_data_file()['instances']['Survival']['minecraft_directory'] == str(paths.MINECRAFT_DIRECTORY)


def test_resetting_the_minecraft_path(window, pages, dialogs):
    window.data.instances['Survival'].minecraft_directory = str(paths.FAKE_HOME_DIRECTORY / 'elsewhere')
    pages.edit_instance('Survival')
    dialogs.answer_yes()

    window.RESET_MINECRAFT_PATH_BUTTON.click()

    assert read_data_file()['instances']['Survival']['minecraft_directory'] == str(paths.MINECRAFT_DIRECTORY)
    assert window.MINECRAFT_DIRECTORY_PATH.text() == str(paths.MINECRAFT_DIRECTORY)


def test_declining_the_path_reset_keeps_the_path(window, pages, dialogs):
    elsewhere = str(paths.FAKE_HOME_DIRECTORY / 'elsewhere')
    window.data.instances['Survival'].minecraft_directory = elsewhere
    pages.edit_instance('Survival')
    dialogs.answer_no()

    window.RESET_MINECRAFT_PATH_BUTTON.click()

    assert window.data.instances['Survival'].minecraft_directory == elsewhere


def test_get_default_instance_name(window, pages):
    assert pages.get_default_instance_name() == DEFAULT
    window.data.instances[DEFAULT].is_default = False
    assert pages.get_default_instance_name() == ''
