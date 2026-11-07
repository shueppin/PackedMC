# PackedMC test suite

```
pip install -r requirements-dev.txt     # needs Python 3.14 like the project itself
pytest                                   # whole suite, ~13 s, headless
pytest tests/test_instance_page.py -k play
pytest -rx                               # show the reasons of the known bugs (expected failures)
```

Nothing in the suite touches your real PackedMC data, the real Minecraft directory, the network, the Minecraft Launcher or any
dialog. A session-wide check fails the run if a file in the real project directory is created, changed or deleted.

## How it works

| Piece | What it does |
|---|---|
| `testing_file_paths.py` | Copy of `utils/file_paths.py`. `conftest.py` registers it as `sys.modules['utils.file_paths']` **before** the project is imported, so every `from utils.file_paths import X` gets the testing value. Everything the app writes goes to `tests/testing_directory/` (wiped before every test, left in place afterwards so you can inspect it). Resources shipped with the project (.ui files, icons, stylesheet) still point to the real files. |
| `fake_internet.py` + `http_responses/` | Answers every `requests` call (patched at `HTTPAdapter.send`) **and** the Qt `QNetworkAccessManager` of the Modrinth search from `http_responses/routes.json`. Records every request. An unregistered URL raises and fails the test in teardown. |
| `conftest.py` | Bootstrap order, plus autouse safety nets: dialogs (`dialogs`), `subprocess` (`subprocesses`), process list (`running_processes`), project threads run inline (`inline_thread_errors`), fake home directory. |
| `helpers.py` | Builders/readers for `data.json`, `launcher_profiles.json`, and Qt helpers. |

## Writing a test

```python
def test_playing_a_fabric_instance(make_main_window, fake_internet, dialogs, subprocesses):
    window = make_main_window(make_data_file_contents(instances={...}, mods={...}))   # real MainWindow
    write_launcher_profiles()

    window.instance_page_class.play_instance('Modded')                                # what the Play button calls

    fake_internet.assert_requested('https://api.modrinth.com/v2/project/sodium/version')
    assert read_data_file()['last_played_instance'] == 'Modded'                       # what ended up on disk
    assert directory_listing(paths.MINECRAFT_DIRECTORY / 'mods') == [...]
    assert subprocesses.commands() == [...]                                           # launcher "started"
```

* **Change an answer**: `fake_internet.add_route(url, json=..., status=..., headers=...)` (beats the defaults).
  **Go offline**: `fake_internet.go_offline()`.
* **Add a default answer**: save the real API response as a file in `http_responses/` and add an entry to `routes.json`.
* **Dialogs**: `dialogs.answer_yes()` (default is "No"), `dialogs.existing_directory = ...`, `dialogs.input_text_answers.append(('Tag', True))`, inspect `dialogs.messages`.
* **Fake running programs**: `running_processes.append('MinecraftLauncher.exe')`.
* A new path constant in `utils/file_paths.py`? `test_environment.py` fails until you add it to `testing_file_paths.py` as well.
* A directory the app creates at import time? It is detected automatically and recreated before every test.

## Known bugs (expected failures)

Tests marked `xfail` describe the **intended** behaviour of code that currently misbehaves; the marker holds the reason.
`xfail_strict` is on: when you fix a bug the test turns into a failure ("XPASS strict") telling you to delete the marker.
