"""
Test bootstrap for PackedMC.

The ORDER of the steps at the top of this file matters, because PackedMC does work at import time (it creates
directories and even downloads the Minecraft version list):

1. Qt is told to run headless.
2. ``utils.file_paths`` is replaced by ``tests/testing_file_paths.py`` before anything imports it.
3. The fake internet and the "run project threads inline" patch are installed.
4. Only then are the PackedMC modules imported.

After that, fixtures keep every test isolated (fresh testing directory, fresh fake internet, no real dialogs, no real
subprocesses, no real process list).
"""
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

# 1. Headless Qt. Has to be set before the first QApplication is created.
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

PROJECT_DIRECTORY = Path(__file__).resolve().parent.parent
if str(PROJECT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIRECTORY))

# 2. Swap the file paths ---------------------------------------------------------------------------------------------
import utils  # noqa: E402  (the package itself has no side effects)
from . import testing_file_paths  # noqa: E402

assert 'utils.file_paths' not in sys.modules, 'utils.file_paths was imported before the tests could replace it.'
sys.modules['utils.file_paths'] = testing_file_paths
utils.file_paths = testing_file_paths

TESTING_DIRECTORY = testing_file_paths.TESTING_DIRECTORY


def _create_directories(directories):
    for directory in sorted(directories, key=lambda d: len(Path(d).parts)):
        Path(directory).mkdir(parents=True, exist_ok=True)


def reset_testing_directory(extra_directories=()):
    """ Delete everything in the testing directory and recreate the standard directory skeleton. """
    if TESTING_DIRECTORY.exists():
        shutil.rmtree(TESTING_DIRECTORY)
    _create_directories(set(testing_file_paths.REQUIRED_DIRECTORIES) | set(extra_directories))


reset_testing_directory()

# 3. Fake internet and inline threads --------------------------------------------------------------------------------
import requests  # noqa: E402
from .fake_internet import FakeInternet, make_fake_network_access_manager  # noqa: E402
from pyqt_utils import modrinth_search_handler  # noqa: E402

INTERNET = FakeInternet()
THREAD_ERRORS: list[tuple[str, BaseException]] = []

_PROJECT_PACKAGES = {'minecraft_api', 'utils', 'interface', 'pyqt_utils'}
_original_thread_start = threading.Thread.start


def _inline_thread_start(self):
    """
    PackedMC starts daemon threads for background work (updating mods, refreshing the version list...).
    Threads that run code from the project are executed right away instead, which makes the tests deterministic.
    Exceptions are collected like an unhandled exception in a real thread would be, see the "inline_thread_errors" fixture.
    """
    target = getattr(self, '_target', None)
    top_level_package = (getattr(target, '__module__', None) or '').split('.')[0]

    if top_level_package not in _PROJECT_PACKAGES:
        return _original_thread_start(self)

    try:
        self.run()
    except BaseException as exception:  # noqa: B902
        THREAD_ERRORS.append((self.name, exception))


_session_patches = pytest.MonkeyPatch()
_session_patches.setattr(threading.Thread, 'start', _inline_thread_start)
_session_patches.setattr(requests.adapters.HTTPAdapter, 'send', lambda adapter, request, **kwargs: INTERNET.send(adapter, request, **kwargs))
_session_patches.setattr(modrinth_search_handler, 'QNetworkAccessManager', make_fake_network_access_manager(INTERNET))

# 4. Import the project. This runs the import-time code against the testing directory and the fake internet ----------
import minecraft_api.minecraft  # noqa: E402,F401
import minecraft_api.fabric  # noqa: E402,F401
import minecraft_api.mod  # noqa: E402,F401
import minecraft_api.minecraft_launcher_integration  # noqa: E402,F401
import utils.data_file_helper  # noqa: E402,F401
import utils.mod_files_handler  # noqa: E402,F401
import interface  # noqa: E402,F401

assert interface.INTERFACE_FILE_PATH is testing_file_paths.INTERFACE_FILE_PATH, 'The project is not using the testing file paths!'

# Directories which the project created while importing must also exist after every wipe.
_IMPORT_TIME_DIRECTORIES = {path for path in TESTING_DIRECTORY.rglob('*') if path.is_dir()}
reset_testing_directory(_IMPORT_TIME_DIRECTORIES)

# Imports for the fixtures below (after the project was imported)
from PyQt6.QtCore import QAbstractAnimation  # noqa: E402
from PyQt6.QtWidgets import QApplication, QDialog, QFileDialog, QInputDialog, QMessageBox  # noqa: E402
import psutil  # noqa: E402
from . import helpers  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    _session_patches.undo()


# ======================================================================================================================
# Session fixtures
# ======================================================================================================================
@pytest.fixture(scope='session', autouse=True)
def _fake_home_directory():
    """ ``is_subdir_of_user_home`` asks the OS for the home directory. Point it into the testing directory. """
    patches = pytest.MonkeyPatch()
    patches.setenv('HOME', str(testing_file_paths.FAKE_HOME_DIRECTORY))
    patches.setenv('USERPROFILE', str(testing_file_paths.FAKE_HOME_DIRECTORY))
    yield
    patches.undo()


def _snapshot_project_directory() -> dict[str, tuple[int, int]]:
    ignored_directories = {'.git', 'tests', '__pycache__', '.pytest_cache', '.venv', 'venv', 'env', '.idea', '.vscode', 'node_modules', 'python'}
    snapshot = {}
    for root, directories, files in os.walk(PROJECT_DIRECTORY):
        directories[:] = [d for d in directories if d not in ignored_directories]
        for file_name in files:
            if file_name.endswith('.pyc'):
                continue
            path = Path(root) / file_name
            stat = path.stat()
            snapshot[str(path.relative_to(PROJECT_DIRECTORY))] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


@pytest.fixture(scope='session', autouse=True)
def _real_project_directory_stays_untouched():
    """ Safety net: the tests must never create, change or delete files in the real project directory (e.g. data.json). """
    before = _snapshot_project_directory()
    yield
    after = _snapshot_project_directory()

    created = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    modified = sorted(path for path in set(before) & set(after) if before[path] != after[path])
    assert not (created or removed or modified), f'The tests touched the real project directory! created={created} removed={removed} modified={modified}'


# ======================================================================================================================
# Function fixtures (all autouse ones are safety nets, so a test can not accidentally leave the sandbox)
# ======================================================================================================================
@pytest.fixture(autouse=True)
def clean_testing_directory():
    reset_testing_directory(_IMPORT_TIME_DIRECTORIES)
    return TESTING_DIRECTORY


@pytest.fixture(autouse=True)
def fake_internet(clean_testing_directory):
    """
    The fake internet. Use ``fake_internet.add_route(...)`` to change answers, ``fake_internet.go_offline()`` to simulate
    no connection and ``fake_internet.assert_requested(...)`` to check what PackedMC requested.
    The test fails if PackedMC requested a URL without a registered answer.
    """
    INTERNET.reset()
    yield INTERNET
    unmatched = [str(request) for request in INTERNET.unmatched]
    INTERNET.reset()
    assert not unmatched, f'PackedMC requested URLs without a registered fake answer: {unmatched}'


@pytest.fixture(autouse=True)
def inline_thread_errors():
    """
    PackedMC threads run inline during the tests. Exceptions raised inside of them are collected here and fail the test,
    unless the test inspects and clears the list itself.
    """
    THREAD_ERRORS.clear()
    yield THREAD_ERRORS
    errors = [(name, repr(exception)) for name, exception in THREAD_ERRORS]
    THREAD_ERRORS.clear()
    assert not errors, f'Unhandled exceptions in PackedMC threads: {errors}'


@pytest.fixture(autouse=True)
def restore_minecraft_globals(monkeypatch):
    """ ``_reload_data`` rebinds the module globals. Make sure that never leaks into the next test. """
    from minecraft_api import minecraft
    for name in ('LATEST_RELEASE', 'LATEST_SNAPSHOT', 'ALL_RELEASE_VERSIONS', 'ALL_SNAPSHOT_VERSIONS'):
        monkeypatch.setattr(minecraft, name, getattr(minecraft, name))


# ---------------------------------------------------------------------------------------------------- dialogs
@dataclass
class ShownMessage:
    kind: str  # 'question', 'warning', 'information', 'critical'
    title: str
    text: str


@dataclass
class DialogRecorder:
    """
    Replaces all modal Qt dialogs (they would block forever in a test) and records what the user would have seen.

    Configure the answers before triggering the action:
        dialogs.answer_yes()                       # QMessageBox.question -> Yes   (default is No)
        dialogs.existing_directory = '/some/dir'   # QFileDialog.getExistingDirectory
        dialogs.open_file_name = '/some/file.json' # QFileDialog.getOpenFileName
        dialogs.input_text_answers.append(('Tag', True))  # QInputDialog.getText (answers are consumed in order)
    """
    messages: list[ShownMessage] = field(default_factory=list)
    question_answer: QMessageBox.StandardButton = QMessageBox.StandardButton.No
    existing_directory: str = ''
    open_file_name: str = ''
    input_text_answers: list[tuple[str, bool]] = field(default_factory=list)
    file_dialog_calls: list[tuple[str, tuple, dict]] = field(default_factory=list)
    executed_dialogs: list[QDialog] = field(default_factory=list)  # Dialogs on which exec() was called

    def answer_yes(self):
        self.question_answer = QMessageBox.StandardButton.Yes

    def answer_no(self):
        self.question_answer = QMessageBox.StandardButton.No

    def of_kind(self, kind: str) -> list[ShownMessage]:
        return [message for message in self.messages if message.kind == kind]

    @property
    def last(self) -> ShownMessage:
        assert self.messages, 'No message box was shown.'
        return self.messages[-1]


@pytest.fixture(autouse=True)
def dialogs(monkeypatch):
    recorder = DialogRecorder()

    def message_box(kind, answer):
        def fake(parent=None, title='', text='', *args, **kwargs):
            recorder.messages.append(ShownMessage(kind, title, text))
            return answer() if callable(answer) else answer
        return staticmethod(fake)

    monkeypatch.setattr(QMessageBox, 'question', message_box('question', lambda: recorder.question_answer))
    monkeypatch.setattr(QMessageBox, 'warning', message_box('warning', QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, 'information', message_box('information', QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(QMessageBox, 'critical', message_box('critical', QMessageBox.StandardButton.Ok))

    def get_existing_directory(*args, **kwargs):
        recorder.file_dialog_calls.append(('getExistingDirectory', args, kwargs))
        return recorder.existing_directory

    def get_open_file_name(*args, **kwargs):
        recorder.file_dialog_calls.append(('getOpenFileName', args, kwargs))
        return recorder.open_file_name, ''

    def get_text(*args, **kwargs):
        if recorder.input_text_answers:
            return recorder.input_text_answers.pop(0)
        return '', False

    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', staticmethod(get_existing_directory))
    monkeypatch.setattr(QFileDialog, 'getOpenFileName', staticmethod(get_open_file_name))
    monkeypatch.setattr(QInputDialog, 'getText', staticmethod(get_text))

    def fake_exec(self):
        recorder.executed_dialogs.append(self)
        return 0

    monkeypatch.setattr(QDialog, 'exec', fake_exec)
    return recorder


# ------------------------------------------------------------------------------------------- external programs
@dataclass
class SubprocessCall:
    function: str  # 'run' or 'Popen'
    args: tuple
    kwargs: dict

    @property
    def command(self) -> str:
        """ The command as one string, no matter whether it was passed as string or list. """
        first = self.args[0] if self.args else self.kwargs.get('args')
        return first if isinstance(first, str) else ' '.join(map(str, first))


@dataclass
class SubprocessRecorder:
    calls: list[SubprocessCall] = field(default_factory=list)
    run_exception: BaseException | None = None  # Raised by subprocess.run, e.g. FileNotFoundError()

    def commands(self) -> list[str]:
        return [call.command for call in self.calls]


@pytest.fixture(autouse=True)
def subprocesses(monkeypatch):
    """ PackedMC starts ``explorer.exe``. Nothing may be launched during the tests, so it is only recorded. """
    recorder = SubprocessRecorder()

    def fake_run(*args, **kwargs):
        recorder.calls.append(SubprocessCall('run', args, kwargs))
        if recorder.run_exception is not None:
            raise recorder.run_exception
        return subprocess.CompletedProcess(args, 0)

    class FakePopen:
        def __init__(self, *args, **kwargs):
            recorder.calls.append(SubprocessCall('Popen', args, kwargs))
            self.returncode = 0

        def wait(self, timeout=None):
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr(subprocess, 'run', fake_run)
    monkeypatch.setattr(subprocess, 'Popen', FakePopen)
    return recorder


@pytest.fixture(autouse=True)
def running_processes(monkeypatch):
    """
    PackedMC refuses to start while the Minecraft Launcher runs. The real process list must never matter in a test.
    Add names to this list to simulate running programs: ``running_processes.append('MinecraftLauncher.exe')``
    """
    names: list[str] = []

    def fake_process_iter(attrs=None, ad_value=None):
        return [SimpleNamespace(info={'name': name, 'exe': ''}) for name in names]

    monkeypatch.setattr(psutil, 'process_iter', fake_process_iter)
    return names


# ------------------------------------------------------------------------------------------------- main window
@pytest.fixture
def stylesheet_calls(monkeypatch):
    """
    Applying a real qt_material stylesheet takes a long time, so ``interface.apply_stylesheet`` is replaced by a recorder.
    Each call is stored as a dict with the keyword arguments. One test in test_main_window.py uses the real one.
    """
    calls = []
    monkeypatch.setattr(interface, 'apply_stylesheet', lambda application, **kwargs: calls.append(kwargs))
    return calls


@pytest.fixture
def make_main_window(qtbot, stylesheet_calls):
    """
    Factory for the real MainWindow:  ``window = make_main_window(data={...})``
    ``data`` is written to data.json before the window is created (see helpers.make_data_file_contents).
    ``close_packedmc`` is set to False, so that play_instance does not terminate the test process with exit().
    """
    windows = []

    def factory(data: dict | None = None, close_packedmc: bool = False):
        if data is not None:
            helpers.write_data_file(data)

        window = interface.MainWindow(QApplication.instance())
        qtbot.addWidget(window)
        windows.append(window)

        window.data.settings.close_packedmc = close_packedmc
        window.data.save()
        return window

    yield factory

    for window in windows:
        # Page changes start 300 ms animations (interface/animation.py). If one is still running when its window is destroyed, Qt
        # advances it during the event loop of a LATER test and crashes the whole test process (segmentation fault). So stop them first.
        for animation in window.findChildren(QAbstractAnimation):
            animation.stop()

        # Every ScrollableGrid installs an application wide event filter which is only removed in the grid's own closeEvent.
        # That never happens when the whole window is closed, so without this the filters pile up and slow down every later test.
        for grid in (window.INSTANCES_PAGE, window.MODS_PAGE, window.INSTANCE_MODS_DISPLAY):
            QApplication.instance().removeEventFilter(grid)


@pytest.fixture
def main_window(make_main_window):
    return make_main_window()
