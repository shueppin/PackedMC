"""
Tests for interface/__init__.py: starting the window, page navigation, the settings page and the data backups.
"""
import logging
import os
from datetime import datetime

import pytest
from PyQt6.QtWidgets import QApplication, QCheckBox, QRadioButton

import interface
from interface import MainWindow

from . import testing_file_paths as paths
from .helpers import (
    directory_listing, find_field, freeze_datetime, make_data_file_contents, make_instance_dict, make_launcher_profile, make_mod_dict,
    read_data_file, read_json, write_data_file, write_json, write_launcher_profiles, write_text,
)

DEFAULT = 'Latest Release'
SITECUSTOMIZE = paths.MAIN_DIRECTORY / 'python' / 'sitecustomize.py'


def radio_buttons(widget) -> dict[str, QRadioButton]:
    """
    The radio buttons inside of a scroll area content widget, in display order.
    The layout is used instead of findChildren(), because replaced buttons are only deleted later by Qt (deleteLater).
    """
    layout = widget.layout()
    items = [layout.itemAt(i).widget() for i in range(layout.count())]
    return {item.text(): item for item in items if isinstance(item, QRadioButton)}


@pytest.fixture
def sitecustomize(monkeypatch):
    """ repair.SITECUSTOMIZE_PATH points into the project, so it is redirected into the testing directory. """
    monkeypatch.setattr(interface, 'SITECUSTOMIZE_PATH', SITECUSTOMIZE)
    return SITECUSTOMIZE


# ======================================================================================================== startup
def test_first_start_creates_the_default_instance(main_window):
    stored = read_data_file()

    assert list(stored['instances']) == [DEFAULT]
    assert stored['instances'][DEFAULT]['is_default'] is True
    assert (stored['instances'][DEFAULT]['type'], stored['instances'][DEFAULT]['version']) == ('Release', 'latest')
    assert stored['last_played_instance'] == DEFAULT
    assert main_window.INSTANCES_PAGE.values == [DEFAULT]


def test_start_with_existing_data_does_not_create_another_instance(make_main_window):
    window = make_main_window(make_data_file_contents(instances={'Mine': make_instance_dict(is_default=True)}))

    assert list(window.data.instances) == ['Mine']
    assert window.INSTANCES_PAGE.values == ['Mine']


@pytest.mark.parametrize('history, expected', [
    (None, 'PackedMC Version: unknown'),
    (['v0.1', 'v0.3', 'v0.2'], 'PackedMC Version: v0.3'),
    (['v0.1', 'dev'], 'PackedMC Version: dev'),
])
def test_version_label(make_main_window, history, expected):
    if history is not None:
        write_json(paths.VERSION_HISTORY, history)
    assert make_main_window().PACKEDMC_VERSION.text() == expected


def test_start_saves_the_options_of_the_last_played_instance(make_main_window):
    write_launcher_profiles({'packedmc': make_launcher_profile(name='PackedMC - Mine', last_used='2026-05-05T10:00:00.000Z')})
    write_text(paths.MINECRAFT_DIRECTORY / 'options.txt', 'fov:80.0')

    make_main_window(make_data_file_contents(instances={'Mine': make_instance_dict(is_default=True)}))

    assert (paths.PACKEDMC_OPTIONS_FILES_DIRECTORY / 'Mine.txt').read_text() == 'fov:80.0'


def test_start_updates_the_mods_of_the_last_played_instance_in_the_background(make_main_window, fake_internet, dialogs):
    make_main_window(make_data_file_contents(
        instances={'Modded': make_instance_dict(type='Fabric', version='1.21.4', is_default=True, mods={'Sodium': ['', '', 0]})},
        mods={'Sodium': make_mod_dict('https://modrinth.com/mod/sodium', loaders=['Fabric'])},
    ))

    assert directory_listing(paths.PACKEDMC_MINECRAFT_DATA_DIRECTORY / 'mods' / 'Modded') == ['sodium-fabric-0.6.0-1.21.4.jar']
    fake_internet.assert_requested('https://api.modrinth.com/v2/project/sodium/version')
    fake_internet.assert_requested('https://cdn.modrinth.com/data/AANobbMI/versions/s1214/sodium-fabric-0.6.0-1.21.4.jar')
    assert not directory_listing(paths.MINECRAFT_DIRECTORY / 'mods')  # Only downloaded, the mods are moved when playing
    assert not dialogs.messages  # The background update does not show any dialog


def test_the_loaded_settings_are_shown_in_the_settings_page(make_main_window):
    window = make_main_window(make_data_file_contents(instances={'A': make_instance_dict(is_default=True)}, settings={'theme': 'blue', 'scale': 2, 'invert_secondary': True, 'use_dark_theme': False, 'close_packedmc': True}))

    assert window.SCALE_SELECTION.value() == 5
    assert window.SWITCH_SECONDARY_COLOR.isChecked() and not window.USE_DARK_THEME.isChecked() and window.CLOSE_PACKEDMC_BUTTON.isChecked()
    assert radio_buttons(window.STYLES_SELECTION_LIST)['Blue'].isChecked()
    assert sorted(radio_buttons(window.STYLES_SELECTION_LIST)) == ['Amber', 'Blue', 'Cyan', 'Green', 'Pink', 'Purple', 'Red', 'Teal']


# ============================================================================================================== pages
def test_instances_page_lists_favourites_first_and_sorts_case_insensitively(make_main_window):
    window = make_main_window(make_data_file_contents(instances={
        'zeta': make_instance_dict(is_default=True),
        'Beta': make_instance_dict(),
        'alpha': make_instance_dict(),
        'Gamma': make_instance_dict(is_favourite=True),
        'delta': make_instance_dict(is_favourite=True),
    }))

    window.show_page(0, show_instantly=True)

    assert window.INSTANCES_PAGE.values == ['★ delta', '★ Gamma', 'alpha', 'Beta', 'zeta']


def test_mods_page_lists_mods_with_their_icons(make_main_window, fake_internet, inline_thread_errors):
    window = make_main_window(make_data_file_contents(
        instances={'A': make_instance_dict(is_default=True)},
        mods={'sodium': make_mod_dict('https://modrinth.com/mod/sodium'), 'Fabric API': make_mod_dict('https://modrinth.com/mod/fabric-api'), 'Odd': make_mod_dict('https://example.com/odd'), 'Gone': make_mod_dict('https://modrinth.com/mod/does-not-exist')},
    ))

    window.show_page(2, show_instantly=True)

    icons = paths.CACHE_DIRECTORY / 'modrinth_mods'
    assert window.MODS_PAGE.values == [('Fabric API', icons / 'fabric-api.png'), ('Gone', icons / 'does-not-exist.png'), ('Odd', ''), ('sodium', icons / 'sodium.png')]
    assert (icons / 'fabric-api.png').exists() and (icons / 'sodium.png').exists()
    fake_internet.assert_requested('https://cdn.modrinth.com/data/P7dR8mSH/icon.png')
    # The icon download of the mod which does not exist on Modrinth fails inside of the background thread
    assert [type(error).__name__ for _, error in inline_thread_errors] == ['ModNotExisting']
    inline_thread_errors.clear()


def test_navigation_buttons_switch_pages(main_window, qtbot):
    window = main_window
    window.MODS_PAGE_BUTTON.pressed.emit()
    window.MODS_PAGE_BUTTON.released.emit()

    qtbot.waitUntil(lambda: window.PAGE_CONTAINER.currentIndex() == 2, timeout=3000)
    assert window.MODS_PAGE_BUTTON.isChecked() and not window.INSTANCES_PAGE_BUTTON.isChecked()

    window.SETTINGS_PAGE_BUTTON.pressed.emit()
    window.SETTINGS_PAGE_BUTTON.released.emit()
    qtbot.waitUntil(lambda: window.PAGE_CONTAINER.currentIndex() == 4, timeout=3000)
    assert window.SETTINGS_PAGE_BUTTON.isChecked() and not window.MODS_PAGE_BUTTON.isChecked()


def test_navigation_is_ignored_while_a_page_animation_runs(main_window, qtbot):
    window = main_window
    window.MODS_PAGE_BUTTON.pressed.emit()
    window.SETTINGS_PAGE_BUTTON.pressed.emit()  # Immediately, while the first animation is still running

    qtbot.waitUntil(lambda: window.PAGE_CONTAINER.currentIndex() == 2, timeout=3000)
    assert not window.SETTINGS_PAGE_BUTTON.isChecked()


def test_make_name_unique():
    assert MainWindow.make_name_unique('Name', []) == 'Name'
    assert MainWindow.make_name_unique('Name', ['Name']) == 'Name 2'
    assert MainWindow.make_name_unique('Name', ['Name', 'Name 2', 'Name 3']) == 'Name 4'
    assert MainWindow.make_name_unique('Name', ['Name 2']) == 'Name'


# =========================================================================================================== settings
def test_close_packedmc_setting_is_saved(main_window):
    before = main_window.CLOSE_PACKEDMC_BUTTON.isChecked()

    main_window.CLOSE_PACKEDMC_BUTTON.click()
    assert read_data_file()['settings']['close_packedmc'] is (not before)

    main_window.CLOSE_PACKEDMC_BUTTON.click()
    assert read_data_file()['settings']['close_packedmc'] is before


def test_choosing_a_theme_applies_and_saves_it(main_window, stylesheet_calls):
    radio_buttons(main_window.STYLES_SELECTION_LIST)['Teal'].click()

    assert stylesheet_calls[-1]['theme'] == 'dark_teal.xml'
    assert read_data_file()['settings']['theme'] == 'teal'


def test_dark_theme_switch(main_window, stylesheet_calls):
    main_window.data.settings.use_dark_theme = True
    main_window.USE_DARK_THEME.setChecked(True)

    main_window.USE_DARK_THEME.click()  # -> light

    assert stylesheet_calls[-1]['theme'] == 'light_lightgreen_500.xml'
    assert read_data_file()['settings']['use_dark_theme'] is False


def test_invert_secondary_switch(main_window, stylesheet_calls):
    main_window.SWITCH_SECONDARY_COLOR.setChecked(False)

    main_window.SWITCH_SECONDARY_COLOR.click()

    assert stylesheet_calls[-1]['invert_secondary'] is True
    assert read_data_file()['settings']['invert_secondary'] is True


def test_scale_changes_the_density_and_the_grid_sizes(main_window, stylesheet_calls):
    main_window.SCALE_SELECTION.setValue(5)

    assert stylesheet_calls[-1]['extra']['density_scale'] == 2  # 5 minus the default of 3
    assert read_data_file()['settings']['scale'] == 2
    assert (main_window.INSTANCES_PAGE.card_width, main_window.INSTANCES_PAGE.card_height) == (100 + 50 * 5, 60 + 20 * 5)
    assert os.environ['PACKEDMC_BIGGER_TEXT_SIZE'] == str(18 + 4 * 2)


def test_unknown_stylesheet_is_reported_and_nothing_is_saved(main_window, caplog):
    main_window.possible_stylesheet_file_names = []

    with caplog.at_level(logging.ERROR):
        main_window.apply_stylesheet(theme_name='blue')

    assert 'does not exist' in caplog.text
    assert read_data_file()['settings']['theme'] == 'green'


def test_apply_stylesheet_ignores_positional_arguments(main_window, caplog):
    with caplog.at_level(logging.WARNING):
        main_window.apply_stylesheet('blue')
    assert 'Ignored args' in caplog.text


def test_the_real_qt_material_stylesheet_can_be_applied(main_window, monkeypatch):
    """ All other tests use a recorder instead of qt_material, because applying a stylesheet is slow. """
    from qt_material import apply_stylesheet as real_apply_stylesheet
    application = QApplication.instance()
    old_style_sheet, old_style = application.styleSheet(), application.style().objectName()
    monkeypatch.setattr(interface, 'apply_stylesheet', real_apply_stylesheet)
    try:
        main_window.apply_stylesheet(theme_name='blue', use_dark_theme=True)

        assert 'QPushButton' in application.styleSheet()
        assert read_data_file()['settings']['theme'] == 'blue'
    finally:
        application.setStyleSheet(old_style_sheet)
        application.setStyle(old_style)


def test_open_packedmc_directory_opens_the_explorer(main_window, subprocesses):
    main_window.OPEN_PACKEDMC_DIRECTORY.click()

    assert subprocesses.commands() == [f'explorer "{paths.MAIN_DIRECTORY}"']


# ============================================================================================================ backups
@pytest.fixture
def backups(main_window):
    """ Helper to show the settings page and to access the backup list. """
    class Backups:
        window = main_window

        def show(self):
            main_window.show_page(4, show_instantly=True)
            return self.names()

        def names(self):
            return list(radio_buttons(main_window.DATA_BACKUP_LIST))

        def select(self, name):
            radio_buttons(main_window.DATA_BACKUP_LIST)[name].click()

    return Backups()


def test_the_settings_page_lists_backups_newest_first_and_marks_automatic_ones(main_window):
    write_text(paths.BACKUP_DIRECTORY / 'data_from_2026-01-01_10-00-00.json', '{}')
    write_text(paths.BACKUP_DIRECTORY / 'data_from_2026-02-01_10-00-00.json', '{}')
    write_text(paths.BACKUP_DIRECTORY / 'data_before_v0.2.json', '{}')

    main_window.show_page(4, show_instantly=True)

    labels = list(radio_buttons(main_window.DATA_BACKUP_LIST))
    assert labels == ['data from 2026-02-01 10-00-00', 'data from 2026-01-01 10-00-00', 'data before v0.2 (automatic)']
    assert not main_window.RESTORE_BACKUP_BUTTON.isEnabled() and not main_window.DELETE_BACKUP_BUTTON.isEnabled()


def test_selecting_a_backup_enables_the_buttons(main_window, backups):
    write_text(paths.BACKUP_DIRECTORY / 'data_from_2026-01-01_10-00-00.json', '{}')
    backups.show()

    backups.select('data from 2026-01-01 10-00-00')

    assert main_window.RESTORE_BACKUP_BUTTON.isEnabled() and main_window.DELETE_BACKUP_BUTTON.isEnabled()


def test_creating_a_backup_copies_data_json(main_window, backups, monkeypatch):
    freeze_datetime(monkeypatch, interface, datetime(2026, 2, 3, 4, 5, 6))

    main_window.CREATE_BACKUP_BUTTON.click()

    assert directory_listing(paths.BACKUP_DIRECTORY) == ['data_from_2026-02-03_04-05-06.json']
    assert read_json(paths.BACKUP_DIRECTORY / 'data_from_2026-02-03_04-05-06.json') == read_data_file()
    assert backups.names() == ['data from 2026-02-03 04-05-06']  # The list was refreshed


@pytest.mark.parametrize('file_name, label', [
    ('data_from_2026-01-01_10-00-00.json', 'data from 2026-01-01 10-00-00'),
    ('data_before_v0.2.json', 'data before v0.2 (automatic)'),
])
def test_restoring_a_backup_replaces_the_data(main_window, backups, dialogs, file_name, label):
    write_json(paths.BACKUP_DIRECTORY / file_name, make_data_file_contents(instances={'FromBackup': make_instance_dict(is_default=True)}))
    backups.show()
    backups.select(label)
    dialogs.answer_yes()

    main_window.RESTORE_BACKUP_BUTTON.click()

    assert list(main_window.data.instances) == ['FromBackup']
    assert list(read_data_file()['instances']) == ['FromBackup']
    assert 'Confirm restoring backup' in dialogs.last.title and label in dialogs.last.text


def test_declining_the_restore_keeps_the_data(main_window, backups, dialogs):
    write_json(paths.BACKUP_DIRECTORY / 'data_from_2026-01-01_10-00-00.json', make_data_file_contents(instances={'FromBackup': make_instance_dict()}))
    backups.show()
    backups.select('data from 2026-01-01 10-00-00')
    dialogs.answer_no()

    main_window.RESTORE_BACKUP_BUTTON.click()

    assert list(read_data_file()['instances']) == [DEFAULT]


def test_deleting_a_backup_removes_the_file(main_window, backups, dialogs):
    write_text(paths.BACKUP_DIRECTORY / 'data_from_2026-01-01_10-00-00.json', '{}')
    write_text(paths.BACKUP_DIRECTORY / 'data_from_2026-02-01_10-00-00.json', '{}')
    backups.show()
    backups.select('data from 2026-01-01 10-00-00')
    dialogs.answer_yes()

    main_window.DELETE_BACKUP_BUTTON.click()

    assert directory_listing(paths.BACKUP_DIRECTORY) == ['data_from_2026-02-01_10-00-00.json']
    assert backups.names() == ['data from 2026-02-01 10-00-00']
    assert dialogs.last.title == 'Confirm deleting backup'


def test_declining_the_deletion_keeps_the_backup(main_window, backups, dialogs):
    write_text(paths.BACKUP_DIRECTORY / 'data_from_2026-01-01_10-00-00.json', '{}')
    backups.show()
    backups.select('data from 2026-01-01 10-00-00')
    dialogs.answer_no()

    main_window.DELETE_BACKUP_BUTTON.click()

    assert directory_listing(paths.BACKUP_DIRECTORY) == ['data_from_2026-01-01_10-00-00.json']


@pytest.mark.xfail(reason='BUG: delete_backup strips the " (automatic)" suffix with rstrip("automatic"), which does not remove the closing parenthesis. '
                          'The computed file name is wrong, so deleting an automatic (pre-update) backup raises FileNotFoundError.')
def test_deleting_an_automatic_backup_removes_the_file(main_window, backups, dialogs):
    write_text(paths.BACKUP_DIRECTORY / 'data_before_v0.2.json', '{}')
    backups.show()
    backups.select('data before v0.2 (automatic)')
    dialogs.answer_yes()

    main_window.DELETE_BACKUP_BUTTON.click()

    assert directory_listing(paths.BACKUP_DIRECTORY) == []


# ================================================================================================== show console switch
def test_console_switch_is_disabled_without_sitecustomize(main_window, sitecustomize):
    main_window.show_page(4, show_instantly=True)
    assert not main_window.SHOW_CONSOLE_BUTTON.isEnabled() and main_window.SHOW_CONSOLE_BUTTON.isChecked()


@pytest.mark.parametrize('content, checked', [('SHOW_CONSOLE = True\n', True), ('SHOW_CONSOLE = False\n', False)])
def test_console_switch_reflects_sitecustomize(main_window, sitecustomize, content, checked):
    write_text(sitecustomize, content)

    main_window.show_page(4, show_instantly=True)

    assert main_window.SHOW_CONSOLE_BUTTON.isEnabled()
    assert main_window.SHOW_CONSOLE_BUTTON.isChecked() is checked


def test_console_switch_toggles_the_value_in_the_file(main_window, sitecustomize):
    write_text(sitecustomize, 'import x\nSHOW_CONSOLE = True\nimport y\n')
    main_window.show_page(4, show_instantly=True)

    main_window.SHOW_CONSOLE_BUTTON.click()
    assert sitecustomize.read_text() == 'import x\nSHOW_CONSOLE = False\nimport y\n'
    assert not main_window.SHOW_CONSOLE_BUTTON.isChecked()

    main_window.SHOW_CONSOLE_BUTTON.click()
    assert 'SHOW_CONSOLE = True' in sitecustomize.read_text()
    assert main_window.SHOW_CONSOLE_BUTTON.isChecked()


def test_console_switch_is_disabled_if_the_file_has_no_setting(main_window, sitecustomize, caplog):
    write_text(sitecustomize, 'nothing here\n')

    with caplog.at_level(logging.WARNING):
        main_window.show_page(4, show_instantly=True)

    assert not main_window.SHOW_CONSOLE_BUTTON.isEnabled()
    assert "doesn't contain the necessary settings" in caplog.text
