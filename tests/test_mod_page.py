"""
Tests for everything the mod pages of the UI call (interface/mod_page.py and the tag popup in interface/popups.py).
"""
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QPushButton, QLabel

from . import fake_file_paths as paths
from .helpers import find_field, make_data_file_contents, make_instance_dict, make_mod_dict, read_data_file

MODRINTH_CACHE = paths.CACHE_DIRECTORY / 'modrinth_mods'


@pytest.fixture
def window(make_main_window):
    return make_main_window(make_data_file_contents(
        instances={
            'Latest Release': make_instance_dict(is_default=True),
            'Modded': make_instance_dict(type='Fabric', version='1.21.4', mods={'Fabric API': ['', '', 0], 'Sodium': ['u', 'f', 5]}),
        },
        mods={
            'Fabric API': make_mod_dict('https://modrinth.com/mod/fabric-api', loaders=['Stale'], tags=['Library']),
            'Sodium': make_mod_dict('https://modrinth.com/mod/sodium', loaders=['Fabric']),
            'Empty': make_mod_dict(''),
        },
        tags=['Library', 'Performance'],
        last_played_instance='Latest Release',
    ))


@pytest.fixture
def pages(window):
    return window.mods_page_class


def selected_tag_boxes(window) -> dict[str, QCheckBox]:
    layout = window.MOD_TAG_SELECTION_LIST.layout()
    items = [layout.itemAt(i).widget() for i in range(layout.count())]
    return {item.text(): item for item in items if isinstance(item, QCheckBox)}


# ======================================================================================================== create_mod
def test_create_mod_with_defaults(window, pages):
    pages.create_mod(edit_afterwards=False)

    assert read_data_file()['mods']['New Mod'] == {'url': '', 'loaders': [], 'supported_versions': [], 'tags': []}


def test_create_mod_makes_the_name_unique(window, pages):
    pages.create_mod('Sodium', edit_afterwards=False)
    pages.create_mod('Sodium', edit_afterwards=False)
    assert [name for name in window.data.mods if name.startswith('Sodium')] == ['Sodium', 'Sodium 2', 'Sodium 3']


def test_create_mod_with_url_shows_it_in_the_edit_page_and_requests_its_data(window, pages, fake_internet):
    pages.create_mod('Another Sodium', url='https://modrinth.com/mod/sodium')

    assert read_data_file()['mods']['Another Sodium']['url'] == 'https://modrinth.com/mod/sodium'
    assert pages.selected_mod_name == 'Another Sodium'
    assert window.MOD_NAME.text() == 'Another Sodium' and window.MOD_URL.text() == 'https://modrinth.com/mod/sodium'
    assert sorted(fake_internet.urls()) == sorted(['https://api.modrinth.com/v2/project/sodium', 'https://cdn.modrinth.com/data/AANobbMI/icon.png'])


def test_the_create_new_mod_card_creates_a_mod(window, qtbot):
    window.show_page(2, show_instantly=True)
    card = [f for f in window.MODS_PAGE.fields if isinstance(f, QPushButton) and f.text().startswith('Create new')][0]

    card.click()

    assert 'New Mod' in window.data.mods


# ========================================================================================================== edit_mod
def test_edit_mod_shows_and_stores_the_data_from_modrinth(window, pages, fake_internet):
    pages.edit_mod('Fabric API')

    assert window.MOD_NAME.text() == 'Fabric API' and window.MOD_URL.text() == 'https://modrinth.com/mod/fabric-api'
    assert window.MOD_LOADER.toPlainText() == 'Fabric\nQuilt'
    assert window.MOD_VERSIONS.toPlainText() == '1.21.4\n1.21.3\n1.20.1\n1.19.4'
    assert 'Essential' in window.MOD_DESCRIPTION.toPlainText()
    assert 'banner.png' not in window.MOD_DESCRIPTION.toHtml()  # Images of the description are removed
    stored = read_data_file()['mods']['Fabric API']
    assert stored['loaders'] == ['Fabric', 'Quilt'] and stored['supported_versions'] == ['1.21.4', '1.21.3', '1.20.1', '1.19.4']  # The stale loaders were replaced
    assert sorted(fake_internet.urls()) == sorted(['https://api.modrinth.com/v2/project/fabric-api', 'https://cdn.modrinth.com/data/P7dR8mSH/icon.png'])
    assert (MODRINTH_CACHE / 'fabric-api.png').exists()


def test_edit_mod_for_a_mod_without_url_requests_nothing(window, pages, fake_internet):
    pages.edit_mod('Empty')

    assert window.MOD_LOADER.toPlainText() == '' and window.MOD_VERSIONS.toPlainText() == ''
    fake_internet.assert_no_requests()


def test_edit_mod_for_a_mod_that_does_not_exist_shows_nothing(window, pages, inline_thread_errors):
    window.data.mods['Gone'] = window.data.mods['Empty'].__class__(url='https://modrinth.com/mod/does-not-exist')

    pages.edit_mod('Gone')

    assert window.MOD_LOADER.toPlainText() == ''
    assert [type(error).__name__ for _, error in inline_thread_errors] == ['ModNotExisting']  # Raised by the background thread
    inline_thread_errors.clear()


def test_edit_mod_selects_the_tags_of_the_mod(window, pages):
    pages.edit_mod('Fabric API')

    boxes = selected_tag_boxes(window)
    assert {name: box.isChecked() for name, box in boxes.items()} == {'Library': True, 'Performance': False}


def test_set_mod_values_ignores_outdated_callbacks(window, pages):
    pages.edit_mod('Empty')

    pages.set_mod_values('description', ['X'], ['1.0'], 'Empty', 'https://modrinth.com/mod/something-else')  # The URL changed in the meantime

    assert window.data.mods['Empty'].loaders == []
    assert window.MOD_LOADER.toPlainText() == ''


def test_set_mod_values_after_a_rename_uses_the_selected_mod(window, pages):
    pages.edit_mod('Empty')
    window.MOD_NAME.setText('Renamed')  # Data callbacks of the old name arrive later

    pages.set_mod_values('<p>d</p>', ['Fabric'], ['1.21.4'], 'Empty', '')

    assert window.data.mods['Renamed'].loaders == ['Fabric']
    assert window.MOD_LOADER.toPlainText() == 'Fabric'


# ============================================================================================================= rename
def test_renaming_a_mod_updates_every_instance(window, pages):
    pages.edit_mod('Sodium')

    window.MOD_NAME.setText('Sodium Reloaded')

    stored = read_data_file()
    assert 'Sodium' not in stored['mods'] and stored['mods']['Sodium Reloaded']['url'] == 'https://modrinth.com/mod/sodium'
    assert stored['instances']['Modded']['mods']['Sodium Reloaded'] == ['u', 'f', 5]  # Download info is kept
    assert 'Sodium' not in stored['instances']['Modded']['mods']
    assert pages.selected_mod_name == 'Sodium Reloaded'


@pytest.mark.parametrize('typed, expected', [('  Spaced  ', 'Spaced'), ('', 'Mod Name'), ('Fabric API', 'Fabric API 2')])
def test_mod_names_are_cleaned_and_made_unique(window, pages, typed, expected):
    pages.edit_mod('Sodium')
    window.MOD_NAME.setText(typed)
    assert expected in window.data.mods and 'Sodium' not in window.data.mods


# ================================================================================================================ url
def test_typing_a_url_starts_a_timer_and_requests_the_data_afterwards(window, pages, fake_internet, qtbot):
    pages.edit_mod('Empty')
    fake_internet.clear_history()

    window.MOD_URL.setText('https://modrinth.com/mod/sodium')
    assert pages.mod_url_timer.isActive()
    fake_internet.assert_no_requests()  # Nothing happens on every keystroke

    qtbot.waitUntil(lambda: window.data.mods['Empty'].loaders == ['Fabric', 'Neoforge'], timeout=3000)
    assert read_data_file()['mods']['Empty']['url'] == 'https://modrinth.com/mod/sodium'
    assert window.data.mods['Empty'].supported_versions == ['1.21.4', '1.20.1']
    assert window.MOD_VERSIONS.toPlainText() == '1.21.4\n1.20.1'
    assert sorted(fake_internet.urls()) == sorted(['https://api.modrinth.com/v2/project/sodium', 'https://cdn.modrinth.com/data/AANobbMI/icon.png'])


def test_each_keystroke_restarts_the_timer(window, pages, fake_internet, qtbot):
    pages.edit_mod('Empty')

    for text in ('h', 'ht', 'htt'):
        window.MOD_URL.setText(text)

    assert pages.mod_url_timer.isActive()
    assert window.data.mods['Empty'].url == ''  # Not stored yet


def test_an_invalid_url_is_stored_but_not_requested(window, pages, fake_internet):
    pages.edit_mod('Empty')
    window.MOD_URL.setText('not a url')

    pages.mod_url_timer.timeout.emit()

    assert read_data_file()['mods']['Empty']['url'] == 'not a url'
    fake_internet.assert_no_requests()


def test_a_url_of_an_unsupported_website_is_stored_without_requests(window, pages, fake_internet):
    pages.edit_mod('Empty')
    window.MOD_URL.setText('https://example.com/some/mod')

    pages.mod_url_timer.timeout.emit()

    assert read_data_file()['mods']['Empty']['url'] == 'https://example.com/some/mod'
    fake_internet.assert_no_requests()


def test_a_curseforge_url_requests_the_curseforge_api(window, pages, fake_internet):
    pages.edit_mod('Empty')
    window.MOD_URL.setText('https://www.curseforge.com/minecraft/mc-mods/jei')

    pages.mod_url_timer.timeout.emit()

    assert window.data.mods['Empty'].loaders == ['Fabric', 'Forge']
    assert sorted(fake_internet.urls()) == sorted(['https://api.cfwidget.com/minecraft/mc-mods/jei', 'https://media.forgecdn.net/avatars/thumbnails/jei.png'])


def test_the_url_is_trimmed(window, pages):
    pages.edit_mod('Empty')
    window.MOD_URL.setText('  https://example.com/x  ')
    pages.mod_url_timer.timeout.emit()
    assert window.data.mods['Empty'].url == 'https://example.com/x'


# ============================================================================================================ delete
def test_deleting_a_mod_removes_it_from_all_instances(window, pages, dialogs):
    pages.edit_mod('Sodium')
    dialogs.answer_yes()

    window.DELETE_MOD_BUTTON.click()

    stored = read_data_file()
    assert 'Sodium' not in stored['mods'] and list(stored['instances']['Modded']['mods']) == ['Fabric API']
    assert 'Confirm deletion' in dialogs.last.title and '"Sodium"' in dialogs.last.text
    assert 'Sodium' not in [name for name, _ in window.MODS_PAGE.values]  # Back on the mods page


def test_declining_the_deletion_keeps_the_mod(window, pages, dialogs):
    pages.edit_mod('Sodium')
    dialogs.answer_no()

    window.DELETE_MOD_BUTTON.click()

    assert 'Sodium' in read_data_file()['mods'] and 'Sodium' in read_data_file()['instances']['Modded']['mods']


# ============================================================================================================== tags
def test_ticking_tags_on_the_mod_page_is_saved(window, pages):
    pages.edit_mod('Sodium')

    selected_tag_boxes(window)['Performance'].click()
    assert read_data_file()['mods']['Sodium']['tags'] == ['Performance']

    selected_tag_boxes(window)['Library'].click()
    assert read_data_file()['mods']['Sodium']['tags'] == ['Performance', 'Library']

    selected_tag_boxes(window)['Performance'].click()
    assert read_data_file()['mods']['Sodium']['tags'] == ['Library']


def test_the_edit_tags_button_opens_the_tag_popup(window, pages, dialogs):
    pages.edit_mod('Sodium')

    window.MOD_EDIT_TAGS_BUTTON.click()

    assert dialogs.executed_dialogs == [pages.mod_tag_popup]
    assert pages.mod_tag_popup.tag_list.count() == 2


# ========================================================================================================== tag popup
@pytest.fixture
def popup(window, pages):
    pages.mod_tag_popup._refresh_tags()
    return pages.mod_tag_popup


def click_tag_button(popup, tag: str, button_text: str):
    for index in range(popup.tag_list.count()):
        widget = popup.tag_list.itemWidget(popup.tag_list.item(index))
        if widget.findChild(QLabel).text() == tag:
            next(b for b in widget.findChildren(QPushButton) if b.text() == button_text).click()
            return
    raise AssertionError(f'No tag "{tag}" in the popup')


def test_adding_a_tag(window, popup, dialogs):
    dialogs.input_text_answers.append(('  Utility  ', True))

    popup._add_tag()

    assert read_data_file()['tags'] == ['Library', 'Performance', 'Utility']
    assert popup.tag_list.count() == 3


@pytest.mark.parametrize('answer', [('Library', True), ('all TAGS', True), ('mods WITHOUT tag', True), ('   ', True), ('Whatever', False)],
                         ids=['duplicate', 'reserved_all', 'reserved_none', 'blank', 'cancelled'])
def test_invalid_tags_are_not_added(window, popup, dialogs, answer):
    dialogs.input_text_answers.append(answer)

    popup._add_tag()

    assert read_data_file()['tags'] == ['Library', 'Performance']


def test_renaming_a_tag_updates_the_mods(window, popup, dialogs):
    window.data.mods['Sodium'].tags = ['Library']
    dialogs.input_text_answers.append(('Core', True))

    click_tag_button(popup, 'Library', 'Rename')

    stored = read_data_file()
    assert stored['tags'] == ['Core', 'Performance']
    assert stored['mods']['Fabric API']['tags'] == ['Core'] and stored['mods']['Sodium']['tags'] == ['Core']


@pytest.mark.parametrize('answer', [('Performance', True), ('Library', True), ('All tags', True), ('', True), ('Core', False)],
                         ids=['existing', 'same_name', 'reserved', 'blank', 'cancelled'])
def test_invalid_tag_renames_are_ignored(window, popup, dialogs, answer):
    dialogs.input_text_answers.append(answer)

    click_tag_button(popup, 'Library', 'Rename')

    assert read_data_file()['tags'] == ['Library', 'Performance']
    assert read_data_file()['mods']['Fabric API']['tags'] == ['Library']


def test_deleting_a_tag_removes_it_from_the_mods(window, popup, dialogs):
    dialogs.answer_yes()

    click_tag_button(popup, 'Library', 'Delete')

    stored = read_data_file()
    assert stored['tags'] == ['Performance'] and stored['mods']['Fabric API']['tags'] == []
    assert popup.tag_list.count() == 1


def test_declining_the_tag_deletion_keeps_everything(window, popup, dialogs):
    dialogs.answer_no()

    click_tag_button(popup, 'Library', 'Delete')

    assert read_data_file()['tags'] == ['Library', 'Performance'] and read_data_file()['mods']['Fabric API']['tags'] == ['Library']


# ================================================================================================== mods page (grid)
def test_clicking_a_mod_card_opens_it(window, pages, qtbot):
    window.show_page(2, show_instantly=True)

    qtbot.mouseClick(find_field(window.MODS_PAGE, 'Sodium'), Qt.MouseButton.LeftButton)

    assert pages.selected_mod_name == 'Sodium' and window.MOD_NAME.text() == 'Sodium'


def test_the_tag_filter_limits_the_displayed_mods(window):
    window.show_page(2, show_instantly=True)
    names = lambda: sorted(l.text() for f in window.MODS_PAGE.fields for l in f.findChildren(QLabel) if l.property('class') == 'bigger_text')

    assert names() == ['Empty', 'Fabric API', 'Sodium']
    window.MODS_PAGE.tags_combo_box.setCurrentText('Library')
    assert names() == ['Fabric API']
    window.MODS_PAGE.tags_combo_box.setCurrentText('Mods without tag')
    assert names() == ['Empty', 'Sodium']
