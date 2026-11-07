"""
Small helpers to build and read the files PackedMC works with.
"""
import json
from datetime import datetime
from pathlib import Path

from . import testing_file_paths as paths


def read_json(path: Path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def write_json(path: Path, data) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    return path


def write_text(path: Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


# ------------------------------------------------------------------------------------------------------ data.json
def make_instance_dict(type='Release', version='latest', minecraft_directory=None, mods=None, is_default=False, is_favourite=False, use_default_options_file=False, advanced_arguments=None) -> dict:
    """ The data.json representation of one instance. ``mods`` maps the mod name to [download_url, filename, last_checked]. """
    data = {
        'type': type,
        'version': version,
        'is_default': is_default,
        'minecraft_directory': str(minecraft_directory or paths.MINECRAFT_DIRECTORY),
        'use_default_options_file': use_default_options_file,
        'mods': mods or {},
        'is_favourite': is_favourite,
    }
    if advanced_arguments is not None:
        data['advanced_arguments'] = advanced_arguments
    return data


def make_mod_dict(url='', loaders=None, supported_versions=None, tags=None) -> dict:
    return {'url': url, 'loaders': loaders or [], 'supported_versions': supported_versions or [], 'tags': tags or []}


def make_data_file_contents(instances: dict | None = None, mods: dict | None = None, last_played_instance: str = None, tags: list | None = None, settings: dict | None = None) -> dict:
    instances = instances or {}
    if last_played_instance is None:
        last_played_instance = next(iter(instances), '')

    contents = {'last_played_instance': last_played_instance, 'instances': instances, 'mods': mods or {}, 'tags': tags or []}
    if settings:
        contents['settings'] = settings
    return contents


def write_data_file(contents: dict) -> Path:
    return write_json(paths.DATA_FILE_PATH, contents)


def read_data_file() -> dict:
    return read_json(paths.DATA_FILE_PATH)


# ------------------------------------------------------------------------------------ launcher_profiles.json
def make_launcher_profile(name='', last_version_id='latest-release', last_used='2026-01-01T10:00:00.000Z', game_dir=None, **extra) -> dict:
    profile = {'created': '2025-01-01T10:00:00.000Z', 'icon': 'Grass', 'lastUsed': last_used, 'lastVersionId': last_version_id, 'name': name, 'type': 'custom'}
    if game_dir is not None:
        profile['gameDir'] = str(game_dir)
    profile.update(extra)
    return profile


def write_launcher_profiles(profiles: dict | None = None) -> Path:
    """
    Creates the launcher_profiles.json of the (fake) official Minecraft Launcher.
    Without arguments it contains the built-in "latest-release" profile, like a launcher that was just installed.
    Pass ``profiles={}`` for a file without any profile.
    """
    if profiles is None:
        profiles = {'latest-release': make_launcher_profile(last_version_id='latest-release', last_used='1970-01-01T00:00:00.000Z', type='latest-release')}
    return write_json(paths.MINECRAFT_LAUNCHER_PROFILES_PATH, {'profiles': profiles, 'settings': {'enableSnapshots': False}, 'version': 3})


def read_launcher_profiles() -> dict:
    return read_json(paths.MINECRAFT_LAUNCHER_PROFILES_PATH)


# ------------------------------------------------------------------------------------------------------- time
def freeze_datetime(monkeypatch, module, moment: datetime):
    """ Make ``datetime.now()`` inside of ``module`` return ``moment``. """
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return moment

    monkeypatch.setattr(module, 'datetime', FrozenDatetime)
    return moment


def directory_listing(path: Path) -> list[str]:
    """ Sorted names inside a directory (empty if it does not exist). Handy for asserting which files were created. """
    path = Path(path)
    return sorted(p.name for p in path.iterdir()) if path.exists() else []


# --------------------------------------------------------------------------------------------------------- Qt helpers
def find_field(grid, name: str):
    """ The card in a ScrollableGrid (instance or mod) which shows ``name``. """
    from PyQt6.QtWidgets import QLabel
    for field in grid.fields:
        if any(label.text() == name for label in field.findChildren(QLabel)):
            return field
    raise AssertionError(f'No field named "{name}" in the grid. Fields: {[[l.text() for l in f.findChildren(QLabel)] for f in grid.fields]}')


def click_button_in(field, text: str):
    from PyQt6.QtWidgets import QPushButton
    for button in field.findChildren(QPushButton):
        if button.text() == text:
            button.click()
            return
    raise AssertionError(f'No button "{text}" in the field.')
