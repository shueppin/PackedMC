"""
Tests for downloading the mods in the background after pressing play: the separate progress window, that the main window stays usable
meanwhile, and that failed mods are reported at the end.

Most tests use REAL threads (the "real_threads" fixture). To be able to look at the state while the download is still running, a "gate"
blocks one request inside the download thread until the test releases it. This way the tests do not depend on timing.
"""
import logging
import threading

import pytest
import requests
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from interface import instance_page as instance_page_module
from pyqt_utils.progress_window import ProgressWindow
from utils import mod_files_handler
from utils.data_file_helper import Data
from utils.mod_files_handler import ModUpdateTask

from . import fake_file_paths as paths
from .helpers import directory_listing, make_data_file_contents, make_instance_dict, make_mod_dict, read_data_file, write_launcher_profiles

SODIUM_LOOKUP_URL = 'https://api.modrinth.com/v2/project/sodium/version'
FABRIC_API_FILE = 'fabric-api-0.115.0-1.21.4.jar'
SODIUM_FILE = 'sodium-fabric-0.6.0-1.21.4.jar'
MINECRAFT_MODS = paths.MINECRAFT_DIRECTORY / 'mods'


@pytest.fixture
def window(make_main_window):
    return make_main_window(make_data_file_contents(
        instances={
            'Latest Release': make_instance_dict(is_default=True),
            'Modded': make_instance_dict(type='Fabric', version='1.21.4', mods={'Fabric API': ['', '', 0], 'Sodium': ['', '', 0]}),
        },
        mods={
            'Fabric API': make_mod_dict('https://modrinth.com/mod/fabric-api', loaders=['Fabric']),
            'Sodium': make_mod_dict('https://modrinth.com/mod/sodium', loaders=['Fabric']),
            'Old Mod': make_mod_dict('https://modrinth.com/mod/old-mod', loaders=['Fabric']),
        },
        last_played_instance='Latest Release',
    ))


@pytest.fixture
def pages(window):
    return window.instance_page_class


@pytest.fixture
def gate(fake_internet, monkeypatch):
    """ Blocks the lookup of Sodium (the second mod) inside the download thread until ``gate.release()`` is called. """
    class Gate:
        def __init__(self):
            self.reached = threading.Event()  # The thread is waiting in front of the gate
            self._open = threading.Event()

        def release(self):
            self._open.set()

        def wait(self):
            self.reached.set()
            assert self._open.wait(timeout=15), 'The test never released the blocked request.'

    gate = Gate()
    original_send = fake_internet.send

    def gated_send(adapter, request, **keyword_arguments):
        if request.url == SODIUM_LOOKUP_URL:
            gate.wait()
        return original_send(adapter, request, **keyword_arguments)

    # noinspection unresolved-references
    monkeypatch.setattr(fake_internet, 'send', gated_send)
    yield gate
    gate.release()  # Never leave a thread blocked, whatever happened in the test


def play_and_wait_at_the_gate(pages, gate, qtbot):
    write_launcher_profiles()
    pages.play_instance('Modded')
    qtbot.waitUntil(gate.reached.is_set, timeout=5000)
    return pages.mod_update_task


def wait_until_finished(pages, qtbot):
    qtbot.waitUntil(lambda: pages.mod_update_task is None, timeout=5000)


# ======================================================================================== downloading in the background
def test_playing_returns_immediately_and_the_download_finishes_in_the_background(window, pages, gate, real_threads, qtbot, subprocesses):
    task = play_and_wait_at_the_gate(pages, gate, qtbot)  # play_instance returned, although the download is not finished

    assert task is not None
    qtbot.waitUntil(lambda: 'Sodium' in task.progress_window.label.text(), timeout=5000)  # The window follows the download thread
    assert task.progress_window.isVisible() and task.progress_window.progress_bar.value() == 1
    assert len(subprocesses.calls) == 1  # The launcher was started right away
    assert not MINECRAFT_MODS.exists() or not directory_listing(MINECRAFT_MODS)  # The mods are only moved when everything is downloaded

    gate.release()
    wait_until_finished(pages, qtbot)

    assert directory_listing(MINECRAFT_MODS) == sorted([FABRIC_API_FILE, SODIUM_FILE, 'packedmc.json'])
    assert task.progress_window is None  # The window was closed
    assert read_data_file()['instances']['Modded']['mods']['Sodium'][1] == SODIUM_FILE


def test_the_progress_window_is_separate_from_the_main_window_and_not_modal(window, pages, gate, real_threads, qtbot):
    task = play_and_wait_at_the_gate(pages, gate, qtbot)
    progress = task.progress_window

    assert progress.isWindow() and progress is not window
    assert progress.windowModality() == Qt.WindowModality.NonModal
    assert QApplication.activeModalWidget() is None  # Nothing blocks the main window
    assert window.isEnabled()

    gate.release()
    wait_until_finished(pages, qtbot)


def test_the_main_window_can_be_used_while_the_mods_download(window, pages, gate, real_threads, qtbot):
    play_and_wait_at_the_gate(pages, gate, qtbot)

    pages.edit_instance('Latest Release')
    window.INSTANCE_FAVOURITE_BUTTON.click()  # Works while the download is blocked

    assert read_data_file()['instances']['Latest Release']['is_favourite'] is True
    gate.release()
    wait_until_finished(pages, qtbot)


def test_changes_of_the_user_during_the_download_are_not_overwritten(window, pages, gate, real_threads, qtbot):
    play_and_wait_at_the_gate(pages, gate, qtbot)
    pages.edit_instance('Latest Release')
    window.INSTANCE_FAVOURITE_BUTTON.click()
    del window.data.instances['Modded'].mods['Sodium']  # The user deselects a mod, which is just being downloaded
    window.data.save()  # (The UI saves after every change)

    gate.release()
    wait_until_finished(pages, qtbot)

    stored = read_data_file()
    assert stored['instances']['Latest Release']['is_favourite'] is True
    assert list(stored['instances']['Modded']['mods']) == ['Fabric API']  # Not selected again by the finished download
    assert stored['instances']['Modded']['mods']['Fabric API'][1] == FABRIC_API_FILE


def test_the_data_is_only_changed_in_the_main_thread(window, pages, gate, real_threads, qtbot, monkeypatch):
    threads = []
    original_save = Data.save
    monkeypatch.setattr(Data, 'save', lambda self: (threads.append(threading.current_thread()), original_save(self))[1])

    play_and_wait_at_the_gate(pages, gate, qtbot)
    gate.release()
    wait_until_finished(pages, qtbot)

    assert threads and all(thread is threading.main_thread() for thread in threads)


def test_playing_again_while_the_mods_download_is_refused(window, pages, gate, real_threads, qtbot, subprocesses, dialogs):
    play_and_wait_at_the_gate(pages, gate, qtbot)

    pages.play_instance('Latest Release')

    assert dialogs.last.title == 'Download in progress'
    assert len(subprocesses.calls) == 1  # The launcher was not started a second time
    gate.release()
    wait_until_finished(pages, qtbot)

    pages.play_instance('Latest Release')  # Possible again
    assert len(subprocesses.calls) == 2


def test_packedmc_closes_only_after_the_mods_are_downloaded(window, pages, gate, real_threads, qtbot, monkeypatch):
    closed = []
    # noinspection unresolved-references
    monkeypatch.setattr(instance_page_module, 'exit', lambda: closed.append(True), raising=False)  # exit() inside of a Qt slot would end the test process
    window.data.settings.close_packedmc = True

    play_and_wait_at_the_gate(pages, gate, qtbot)
    assert closed == []  # Not while the download is running

    gate.release()
    wait_until_finished(pages, qtbot)
    assert closed == [True]


# ============================================================================================ reporting failed mods
def play_with_a_timeout_for_sodium(window, pages, fake_internet):
    fake_internet.add_route(SODIUM_LOOKUP_URL, raises=requests.exceptions.ReadTimeout())
    write_launcher_profiles()
    pages.play_instance('Modded')


def test_failed_mods_are_logged_and_listed_in_the_final_message(window, pages, fake_internet, dialogs, caplog):
    window.data.instances['Modded'].mods['Old Mod'] = ('', '', 0)  # No file for 1.21.4

    with caplog.at_level(logging.WARNING):
        play_with_a_timeout_for_sodium(window, pages, fake_internet)

    # One message with both: the missing mod and the failed mod
    assert len(dialogs.messages) == 1 and dialogs.last.kind == 'warning' and dialogs.last.title == 'Could not update all mods'
    assert 'Could not find a file for the following mods for Fabric 1.21.4' in dialogs.last.text and ' - Old Mod' in dialogs.last.text
    assert ' - Sodium (timed out' in dialogs.last.text
    assert 'Fabric API' not in dialogs.last.text
    assert any('Sodium' in record.getMessage() and 'timed out' in record.getMessage() for record in caplog.records if record.levelno == logging.WARNING)
    # The mods which worked are installed anyway
    assert directory_listing(MINECRAFT_MODS) == [FABRIC_API_FILE, 'packedmc.json']


def test_a_message_with_only_failed_mods(window, pages, fake_internet, dialogs):
    play_with_a_timeout_for_sodium(window, pages, fake_internet)

    assert dialogs.last.kind == 'warning'
    assert 'Could not find a file' not in dialogs.last.text and ' - Sodium (timed out' in dialogs.last.text


def test_nothing_is_shown_if_all_mods_were_updated(window, pages, dialogs):
    write_launcher_profiles()
    pages.play_instance('Modded')
    assert not dialogs.messages


def test_a_failed_mod_keeps_its_old_file_and_is_retried_on_the_next_play(window, pages, fake_internet, dialogs):
    play_with_a_timeout_for_sodium(window, pages, fake_internet)
    assert list(window.data.instances['Modded'].mods['Sodium']) == ['', '', 0]  # Not marked as checked
    dialogs.messages.clear()

    fake_internet.add_route(SODIUM_LOOKUP_URL, file='modrinth_versions_sodium.json')  # The website works again
    pages.play_instance('Modded')

    assert not dialogs.messages
    assert SODIUM_FILE in directory_listing(MINECRAFT_MODS)


# ================================================================================================= the task and the window
def test_a_crash_of_the_update_still_finishes_and_closes_the_window(window, monkeypatch, caplog):
    def crash(*arguments, **keyword_arguments):
        raise RuntimeError('crash for the test')

    monkeypatch.setattr(mod_files_handler, 'run_mod_update', crash)
    results = []
    task = ModUpdateTask(window, 'Modded', window.data.instances['Modded'].mods, '1.21.4', 'Fabric', on_finished=results.append)

    with caplog.at_level(logging.ERROR):
        task.start()

    assert len(results) == 1  # The caller is always told, so nothing waits forever
    assert task.progress_window is None
    assert 'stopped unexpectedly' in caplog.text


def test_the_task_can_run_without_a_window(window):
    results = []
    task = ModUpdateTask(window, 'Modded', window.data.instances['Modded'].mods, '1.21.4', 'Fabric', on_finished=results.append, show_progress_window=False)

    task.start()

    assert task.progress_window is None
    assert len(results) == 1 and not results[0].has_problems
    assert window.data.instances['Modded'].mods['Fabric API'][1] == FABRIC_API_FILE


def test_progress_window_properties(qtbot):
    progress = ProgressWindow(None, 'Title', 3, 'Text')
    qtbot.addWidget(progress)

    assert progress.isWindow() and progress.windowModality() == Qt.WindowModality.NonModal
    assert progress.windowTitle() == 'Title' and progress.label.text() == 'Text'
    assert not progress.windowFlags() & Qt.WindowType.WindowCloseButtonHint  # It can't be cancelled, so it has no close button

    progress.set_progress(2, 'Next')
    assert (progress.progress_bar.maximum(), progress.progress_bar.value(), progress.label.text()) == (3, 2, 'Next')


def test_progress_window_without_mods_does_not_break_the_progress_bar(qtbot):
    progress = ProgressWindow(None, 'Title', 0)
    qtbot.addWidget(progress)
    assert progress.progress_bar.maximum() == 1
