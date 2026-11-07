"""
Tests for the Modrinth search in the mods page. This part of PackedMC does not use ``requests`` but Qt's network classes,
which the fake internet also replaces (see fake_internet.py).
"""
import json

import pytest
from PyQt6.QtGui import QPixmap

from pyqt_utils.modrinth_search_handler import ModrinthIconLoader, ModrinthSearcher

from .helpers import make_data_file_contents, make_instance_dict, make_mod_dict, read_data_file

SEARCH_URL = 'https://api.modrinth.com/v2/search'
SODIUM_ICON = 'https://cdn.modrinth.com/data/AANobbMI/icon.png'


def search_requests(fake_internet):
    return fake_internet.requests_to(SEARCH_URL)


# ============================================================================================== ModrinthSearcher
@pytest.fixture
def searcher(qtbot):
    searcher = ModrinthSearcher(debounce_ms=10)
    return searcher


def test_a_search_requests_the_modrinth_api_and_returns_the_hits(searcher, fake_internet, qtbot):
    with qtbot.waitSignal(searcher.results_ready, timeout=2000) as blocker:
        searcher.search('sodium')

    hits = blocker.args[0]
    assert [hit['slug'] for hit in hits] == ['sodium', 'sodium-extra']
    request = fake_internet.assert_requested(SEARCH_URL)[0]
    assert request.source == 'qt' and request.method == 'GET'
    assert request.query['query'] == ['sodium']
    assert json.loads(request.query['facets'][0]) == [['project_type:mod']]  # Only mods, no modpacks or resource packs
    assert request.query['limit'] == ['20'] and request.query['index'] == ['relevance']
    assert request.header('User-Agent') == 'shueppin/PackedMC'


def test_the_search_announces_its_start(searcher, qtbot):
    with qtbot.waitSignal(searcher.search_started, timeout=2000) as blocker:
        searcher.search('  sodium  ')
    assert blocker.args == ['sodium']  # Trimmed


def test_a_search_without_results(searcher, qtbot):
    with qtbot.waitSignal(searcher.results_ready, timeout=2000) as blocker:
        searcher.search('nothing-matches-this')
    assert blocker.args[0] == []


def test_the_limit_can_be_configured(qtbot, fake_internet):
    searcher = ModrinthSearcher(debounce_ms=10, limit=5)
    with qtbot.waitSignal(searcher.results_ready, timeout=2000):
        searcher.search('sodium')
    assert search_requests(fake_internet)[0].query['limit'] == ['5']


def test_typing_quickly_only_searches_once_for_the_last_text(searcher, fake_internet, qtbot):
    searcher.search_timer.setInterval(100)

    with qtbot.waitSignal(searcher.results_ready, timeout=3000):
        searcher.search('s')
        searcher.search('so')
        searcher.search('sodium')

    assert [r.query['query'] for r in search_requests(fake_internet)] == [['sodium']]


def test_an_empty_query_does_not_search(searcher, fake_internet, qtbot):
    with qtbot.assertNotEmitted(searcher.search_started, wait=150):
        searcher.search('   ')
    fake_internet.assert_no_requests()


def test_cancel_prevents_a_pending_search(searcher, fake_internet, qtbot):
    searcher.search('sodium')
    searcher.cancel()

    with qtbot.assertNotEmitted(searcher.results_ready, wait=150):
        pass
    fake_internet.assert_no_requests()


def test_an_outdated_reply_is_discarded(searcher, fake_internet, qtbot):
    """ Two searches overlap: only the answer of the second one may arrive. """
    received = []
    searcher.results_ready.connect(received.append)

    searcher.current_query = 'sodium'
    searcher._perform_search()
    searcher.current_query = 'nothing-matches-this'
    searcher._perform_search()  # Aborts the first request
    qtbot.wait(100)

    assert received == [[]]  # Only the second (empty) answer
    assert [r.query['query'] for r in search_requests(fake_internet)] == [['sodium'], ['nothing-matches-this']]


def test_a_failed_request_emits_search_failed(searcher, fake_internet, qtbot):
    fake_internet.go_offline()

    with qtbot.waitSignal(searcher.search_failed, timeout=2000) as blocker:
        searcher.search('sodium')

    assert blocker.args[0]  # Some error text


def test_an_error_status_emits_search_failed(searcher, fake_internet, qtbot):
    fake_internet.add_route(SEARCH_URL, status=500, text='server error')
    with qtbot.waitSignal(searcher.search_failed, timeout=2000):
        searcher.search('sodium')


def test_an_invalid_answer_emits_search_failed(searcher, fake_internet, qtbot):
    fake_internet.add_route(SEARCH_URL, text='<html>not json</html>')
    with qtbot.waitSignal(searcher.search_failed, timeout=2000):
        searcher.search('sodium')


# ============================================================================================== ModrinthIconLoader
@pytest.fixture
def icon_loader(qtbot):
    return ModrinthIconLoader()


def test_the_icon_is_downloaded_and_emitted(icon_loader, fake_internet, qtbot):
    with qtbot.waitSignal(icon_loader.icon_ready, timeout=2000) as blocker:
        icon_loader.load(SODIUM_ICON)

    url, pixmap = blocker.args
    assert url == SODIUM_ICON and isinstance(pixmap, QPixmap) and not pixmap.isNull()
    fake_internet.assert_requested(SODIUM_ICON)


def test_a_loaded_icon_is_cached(icon_loader, fake_internet, qtbot):
    with qtbot.waitSignal(icon_loader.icon_ready, timeout=2000):
        icon_loader.load(SODIUM_ICON)

    with qtbot.waitSignal(icon_loader.icon_ready, timeout=2000):
        icon_loader.load(SODIUM_ICON)

    assert len(fake_internet.requests_to(SODIUM_ICON)) == 1


def test_an_empty_icon_url_is_ignored(icon_loader, fake_internet, qtbot):
    with qtbot.assertNotEmitted(icon_loader.icon_ready, wait=100):
        icon_loader.load('')
    fake_internet.assert_no_requests()


def test_icons_that_fail_to_download_are_not_emitted(icon_loader, fake_internet, qtbot):
    fake_internet.add_route('https://cdn.modrinth.com/data/BROKEN/icon.png', status=404)

    with qtbot.assertNotEmitted(icon_loader.icon_ready, wait=150):
        icon_loader.load('https://cdn.modrinth.com/data/BROKEN/icon.png')

    fake_internet.assert_requested('https://cdn.modrinth.com/data/BROKEN/icon.png')


def test_icons_which_are_not_images_are_not_emitted(icon_loader, fake_internet, qtbot):
    fake_internet.add_route('https://cdn.modrinth.com/data/TEXT/icon.png', text='this is not a png')
    with qtbot.assertNotEmitted(icon_loader.icon_ready, wait=150):
        icon_loader.load('https://cdn.modrinth.com/data/TEXT/icon.png')


# ======================================================================================== the search in the mods page
@pytest.fixture
def window(make_main_window):
    window = make_main_window(make_data_file_contents(
        instances={'Latest Release': make_instance_dict(is_default=True)},
        mods={'Sodium': make_mod_dict('https://modrinth.com/mod/sodium'), 'Fabric API': make_mod_dict('https://modrinth.com/mod/fabric-api')},
    ))
    window.show_page(2, show_instantly=True)
    return window


@pytest.fixture
def grid(window):
    return window.MODS_PAGE


def local_names(grid):
    from PyQt6.QtWidgets import QLabel
    return sorted(label.text() for field in grid.fields for label in field.findChildren(QLabel) if label.property('class') == 'bigger_text')


def test_typing_in_the_search_field_searches_modrinth_and_shows_the_results(window, grid, fake_internet, qtbot):
    fake_internet.clear_history()

    grid.search_line_edit.setText('sodium')

    assert grid.modrinth_overlay_shown and grid.modrinth_status_label.text() == 'Searching Modrinth...'
    qtbot.waitUntil(lambda: grid.modrinth_results_list.count() == 2, timeout=3000)
    assert grid.modrinth_status_label.text() == '2 Modrinth result(s)'
    assert search_requests(fake_internet)[0].query['query'] == ['sodium']
    qtbot.waitUntil(lambda: len(fake_internet.requests_to(SODIUM_ICON)) == 1, timeout=3000)  # Icons are loaded for results which have one
    assert len(fake_internet.requests_to(SODIUM_ICON)) == 1


def test_the_local_mods_are_filtered_while_searching(grid, qtbot):
    assert local_names(grid) == ['Fabric API', 'Sodium']

    grid.search_line_edit.setText('sod')

    assert local_names(grid) == ['Sodium']


def test_no_results_are_reported(grid, qtbot):
    grid.search_line_edit.setText('nothing-matches-this')
    qtbot.waitUntil(lambda: grid.modrinth_status_label.text() == 'No Modrinth mods found.', timeout=3000)


def test_a_failed_search_is_reported(grid, fake_internet, qtbot):
    fake_internet.go_offline()
    grid.search_line_edit.setText('sodium')
    qtbot.waitUntil(lambda: grid.modrinth_status_label.text() == 'Could not search Modrinth.', timeout=3000)


def test_clearing_the_search_hides_the_overlay_and_cancels(grid, fake_internet, qtbot):
    grid.search_line_edit.setText('sodium')
    assert grid.modrinth_overlay_shown

    grid.search_line_edit.setText('')

    assert not grid.modrinth_overlay_shown
    with qtbot.assertNotEmitted(grid.modrinth_searcher.results_ready, wait=150):
        pass
    assert local_names(grid) == ['Fabric API', 'Sodium']


def test_pressing_enter_searches_only_local_mods(grid, fake_internet, qtbot):
    fake_internet.clear_history()
    grid.search_line_edit.setText('sodium')

    grid.search_line_edit.returnPressed.emit()

    assert not grid.modrinth_overlay_shown
    qtbot.wait(150)
    assert search_requests(fake_internet) == []  # The pending search was cancelled
    assert local_names(grid) == ['Sodium']


def test_choosing_a_result_creates_the_mod_and_opens_it(window, grid, fake_internet, qtbot):
    fake_internet.add_route('https://api.modrinth.com/v2/project/sodium-extra', json={'body': 'Extras', 'game_versions': ['1.21.4'], 'loaders': ['fabric'], 'icon_url': None})
    grid.search_line_edit.setText('sodium')
    qtbot.waitUntil(lambda: grid.modrinth_results_list.count() == 2, timeout=3000)
    fake_internet.clear_history()

    grid.modrinth_results_list.itemClicked.emit(grid.modrinth_results_list.item(1))  # "Sodium Extra"

    assert not grid.modrinth_overlay_shown
    stored = read_data_file()['mods']['Sodium Extra']
    assert stored['url'] == 'https://modrinth.com/mod/sodium-extra'
    assert window.mods_page_class.selected_mod_name == 'Sodium Extra'  # The edit page is shown
    fake_internet.assert_requested('https://api.modrinth.com/v2/project/sodium-extra')  # The data of the new mod is loaded
    assert window.data.mods['Sodium Extra'].loaders == ['Fabric']


def test_modrinth_is_not_searched_in_the_mods_of_an_instance(window, fake_internet):
    fake_internet.clear_history()

    window.INSTANCE_MODS_DISPLAY.search_line_edit.setText('sodium')

    assert not window.INSTANCE_MODS_DISPLAY.modrinth_overlay_shown
    fake_internet.assert_no_requests()
