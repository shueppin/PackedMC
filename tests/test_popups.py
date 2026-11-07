"""
Tests for the popups opened from the UI: importing launcher profiles and the advanced instance options.
(The tag popup is tested in test_mod_page.py.)
"""
import pytest
from PyQt6.QtWidgets import QCheckBox

from . import fake_file_paths as paths
from .helpers import (
    directory_listing, make_data_file_contents, make_instance_dict, make_launcher_profile, read_data_file, write_json, write_text,
)

IMPORT_PROFILES_BUG = pytest.mark.xfail(reason="BUG: ImportProfilesHandler._import_selected_profiles uses self.parent.data['instances'], but Data is a dataclass without __getitem__, "
                                               "so importing any profile raises TypeError. (Use self.parent.data.instances.)")
JAVA_ARGUMENTS_BUG = pytest.mark.xfail(reason="BUG: Importing profiles passes advanced_arguments as a plain dict with string values and picomc style keys "
                                              "('java.path', a list for 'other_arguments'), but SingleInstanceData expects an AdvancedArgumentsData. "
                                              "Later attribute access (start_heap_size ...) raises AttributeError. Hidden behind the TypeError above until that one is fixed.")

IMPORT_FILE = paths.FAKE_HOME_DIRECTORY / 'import' / 'launcher_profiles.json'


@pytest.fixture
def window(make_main_window):
    return make_main_window(make_data_file_contents(
        instances={
            'Latest Release': make_instance_dict(is_default=True),
            'Survival': make_instance_dict(type='Release', version='1.20.1'),
            'Modded': make_instance_dict(type='Fabric', version='1.21.4'),
        },
        last_played_instance='Latest Release',
    ))


# ================================================================================================ import profiles
def write_import_file(profiles: dict):
    write_json(IMPORT_FILE, {'profiles': profiles, 'version': 3})


def profile_boxes(window) -> dict[str, QCheckBox]:
    layout = window.import_profiles_popup_handler.import_profiles_popup.PROFILES_SELECTION_LIST.layout()
    items = [layout.itemAt(i).widget() for i in range(layout.count())]
    return {item.text(): item for item in items if isinstance(item, QCheckBox)}


def open_import_popup(window, dialogs):
    dialogs.open_file_name = str(IMPORT_FILE)
    window.import_profiles_popup_handler.open_popup()


SAMPLE_PROFILES = {
    'a': make_launcher_profile(name='My Fabric', last_version_id='fabric-loader-0.16.9-1.21.4', game_dir=paths.FAKE_HOME_DIRECTORY / 'fabric_dir'),
    'b': make_launcher_profile(name='', last_version_id='1.20.1'),
    'c': make_launcher_profile(name='Newest', last_version_id='latest-release'),
    'd': {'name': 'Broken profile without version'},
}


def test_the_popup_lists_the_profiles_of_the_selected_file(window, dialogs):
    write_import_file(SAMPLE_PROFILES)

    open_import_popup(window, dialogs)

    assert list(profile_boxes(window)) == ['1.20.1', 'My Fabric (running fabric-loader-0.16.9-1.21.4)', 'Newest (running latest-release)']  # Sorted, the broken one is skipped
    assert window.import_profiles_popup_handler.import_profiles_popup.isVisible()
    call = dialogs.file_dialog_calls[0]
    assert call[0] == 'getOpenFileName' and str(paths.MINECRAFT_LAUNCHER_PROFILES_PATH) in call[1]  # Starts in the official launcher's directory


def test_cancelling_the_file_dialog_shows_no_popup(window, dialogs, caplog):
    dialogs.open_file_name = ''
    window.import_profiles_popup_handler.open_popup()
    assert not window.import_profiles_popup_handler.import_profiles_popup.isVisible()


def test_an_invalid_profiles_file_shows_no_popup(window, dialogs, caplog):
    write_text(IMPORT_FILE, '{ not json')
    open_import_popup(window, dialogs)
    assert not window.import_profiles_popup_handler.import_profiles_popup.isVisible()
    assert 'error decoding' in caplog.text


def import_profiles(window, dialogs, *display_names):
    write_import_file(SAMPLE_PROFILES)
    open_import_popup(window, dialogs)
    boxes = profile_boxes(window)
    for name in display_names:
        boxes[name].setChecked(True)
    window.import_profiles_popup_handler.import_profiles_popup.IMPORT_BUTTON.click()


FABRIC_NAME = 'My Fabric (running fabric-loader-0.16.9-1.21.4)'


@IMPORT_PROFILES_BUG
def test_importing_a_fabric_profile_creates_an_instance(window, dialogs):
    import_profiles(window, dialogs, FABRIC_NAME)

    instance = read_data_file()['instances']['My Fabric']
    assert (instance['type'], instance['version']) == ('Fabric', '1.21.4')
    assert instance['minecraft_directory'] == str(paths.FAKE_HOME_DIRECTORY / 'fabric_dir')


@IMPORT_PROFILES_BUG
def test_only_selected_profiles_are_imported_and_the_popup_closes(window, dialogs):
    import_profiles(window, dialogs, '1.20.1')

    assert sorted(read_data_file()['instances']) == ['1.20.1', 'Latest Release', 'Modded', 'Survival']
    assert not window.import_profiles_popup_handler.import_profiles_popup.isVisible()


@IMPORT_PROFILES_BUG
def test_importing_a_release_profile_without_a_name_uses_the_version(window, dialogs):
    import_profiles(window, dialogs, '1.20.1')

    instance = read_data_file()['instances']['1.20.1']
    assert (instance['type'], instance['version']) == ('Release', '1.20.1')
    assert instance['minecraft_directory'] == str(paths.MINECRAFT_DIRECTORY)  # No gameDir in the profile


@IMPORT_PROFILES_BUG
def test_importing_the_latest_release_profile(window, dialogs):
    import_profiles(window, dialogs, 'Newest (running latest-release)')

    instance = read_data_file()['instances']['Newest']
    assert (instance['type'], instance['version']) == ('Release', 'latest')


@IMPORT_PROFILES_BUG
def test_imported_names_are_made_unique(window, dialogs):
    write_import_file({'a': make_launcher_profile(name='Survival', last_version_id='1.20.1')})
    open_import_popup(window, dialogs)
    profile_boxes(window)['Survival (running 1.20.1)'].setChecked(True)

    window.import_profiles_popup_handler.import_profiles_popup.IMPORT_BUTTON.click()

    assert 'Survival 2' in read_data_file()['instances']


@IMPORT_PROFILES_BUG
def test_imported_instances_appear_on_the_instances_page(window, dialogs):
    import_profiles(window, dialogs, FABRIC_NAME)
    assert 'My Fabric' in window.INSTANCES_PAGE.values


@IMPORT_PROFILES_BUG
@JAVA_ARGUMENTS_BUG
def test_java_arguments_of_an_imported_profile_become_advanced_arguments(window, dialogs):
    write_import_file({'a': make_launcher_profile(name='Tuned', last_version_id='1.20.1', javaArgs='-Xmx4G -Xms1G -XX:+UseG1GC -Dfoo=bar')})
    open_import_popup(window, dialogs)
    profile_boxes(window)['Tuned (running 1.20.1)'].setChecked(True)

    window.import_profiles_popup_handler.import_profiles_popup.IMPORT_BUTTON.click()

    arguments = window.data.instances['Tuned'].advanced_arguments
    assert (arguments.start_heap_size, arguments.max_heap_size) == (1, 4)
    assert arguments.other_arguments == '-XX:+UseG1GC -Dfoo=bar'


# ================================================================================================ advanced options
@pytest.fixture
def advanced(window):
    window.instance_page_class.edit_instance('Modded')
    handler = window.instance_page_class.advanced_options_popup_handler
    return handler.advanced_options_popup


def test_the_advanced_popup_shows_the_stored_arguments(window, advanced, dialogs):
    window.data.instances['Modded'].advanced_arguments.start_heap_size = 3
    window.data.instances['Modded'].advanced_arguments.max_heap_size = 6
    window.data.instances['Modded'].advanced_arguments.other_arguments = '-Dfoo=bar'

    window.ADVANCED_SETTINGS_BUTTON.click()

    assert dialogs.executed_dialogs == [advanced]
    assert (advanced.START_HEAP_SIZE.value(), advanced.MAX_HEAP_SIZE.value(), advanced.OTHER_ARGUMENTS.toPlainText()) == (3, 6, '-Dfoo=bar')


def test_the_update_fabric_button_is_only_enabled_for_fabric(window, advanced):
    window.ADVANCED_SETTINGS_BUTTON.click()
    assert advanced.UPDATE_FABRIC_VERSION_BUTTON.isEnabled()
    assert advanced.UPDATE_FABRIC_VERSION_BUTTON.text() == 'Update to newest Fabric version'

    window.instance_page_class.edit_instance('Survival')
    window.ADVANCED_SETTINGS_BUTTON.click()
    assert not advanced.UPDATE_FABRIC_VERSION_BUTTON.isEnabled()


def test_closing_the_advanced_popup_stores_the_values(window, advanced):
    window.ADVANCED_SETTINGS_BUTTON.click()
    advanced.START_HEAP_SIZE.setValue(4)
    advanced.MAX_HEAP_SIZE.setValue(8)
    advanced.OTHER_ARGUMENTS.setText('-XX:+UseG1GC')

    advanced.done(0)

    arguments = read_data_file()['instances']['Modded']['advanced_arguments']
    assert arguments == {'start_heap_size': 4, 'max_heap_size': 8, 'other_arguments': '-XX:+UseG1GC'}


def test_the_update_fabric_button_installs_the_newest_loader(window, advanced, fake_internet):
    window.data.instances['Modded'].version = '1.21.4'
    window.ADVANCED_SETTINGS_BUTTON.click()

    advanced.UPDATE_FABRIC_VERSION_BUTTON.click()

    loader = 'fabric-loader-0.16.9-1.21.4'
    assert directory_listing(paths.VERSIONS_DIRECTORY / loader) == [f'{loader}.jar', f'{loader}.json']
    assert advanced.UPDATE_FABRIC_VERSION_BUTTON.text() == f'Installed Fabric version {loader}'
    assert sorted(fake_internet.urls()) == sorted([
        'https://meta.fabricmc.net/v2/versions/loader',
        'https://maven.fabricmc.net/net/fabricmc/fabric-loader/0.16.9/fabric-loader-0.16.9.jar',
        'https://meta.fabricmc.net/v2/versions/loader/1.21.4/0.16.9/profile/json',
    ])


@pytest.mark.xfail(reason='BUG: "Update to newest Fabric version" passes the instance version "latest" (the default!) to the Fabric API instead of resolving it to the newest '
                          'release first, so a VersionException is raised. write_instance_data_to_profiles_file does resolve "latest".')
def test_the_update_fabric_button_works_for_latest(window, advanced, fake_internet):
    # This is what the real Fabric meta API answers for the unknown version "latest"
    fake_internet.add_route('https://meta.fabricmc.net/v2/versions/loader/latest/0.16.9/profile/json', status=400, text='no mappings version found for latest')
    window.data.instances['Modded'].version = 'latest'
    window.ADVANCED_SETTINGS_BUTTON.click()

    advanced.UPDATE_FABRIC_VERSION_BUTTON.click()

    assert (paths.VERSIONS_DIRECTORY / 'fabric-loader-0.16.9-1.21.4').is_dir()
