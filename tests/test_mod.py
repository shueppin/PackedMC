import pytest
import requests

from minecraft_api import mod
from minecraft_api.mod import (
    APICooldown, EmptyArguments, InvalidModBaseUrl, ModNotExisting, NoModFileAvailable, TryAgainLater,
    get_download_url, get_mod_data, get_mod_icon_path,
)

from . import fake_file_paths as paths
from .fake_internet import RESPONSES_DIRECTORY
from .helpers import directory_listing, read_json

MODRINTH_FABRIC_API = 'https://modrinth.com/mod/fabric-api'
CURSEFORGE_JEI = 'https://www.curseforge.com/minecraft/mc-mods/jei'
MODRINTH_CACHE = paths.CACHE_DIRECTORY / 'modrinth_mods'
CURSEFORGE_CACHE = paths.CACHE_DIRECTORY / 'curseforge_mods'
ICON_BYTES = (RESPONSES_DIRECTORY / 'icon.png').read_bytes()


# ============================================================================================ get_download_url: Modrinth
def test_modrinth_download_url_requests_the_version_list_of_the_project(fake_internet):
    url, filename = get_download_url(MODRINTH_FABRIC_API, '1.21.4', 'Fabric')

    assert url == 'https://cdn.modrinth.com/data/P7dR8mSH/versions/v1214/fabric-api-0.115.0-1.21.4.jar'
    assert filename == 'fabric-api-0.115.0-1.21.4.jar'
    request = fake_internet.assert_requested('https://api.modrinth.com/v2/project/fabric-api/version')[0]
    assert request.header('User-Agent') == mod.PROJECT_OWN_HEADERS['User-Agent']  # Modrinth requires an identifying User-Agent
    assert len(fake_internet.requests) == 1


@pytest.mark.parametrize('game_version, expected_filename', [
    ('1.21.4', 'fabric-api-0.115.0-1.21.4.jar'),
    ('1.21.3', 'fabric-api-0.114.0-1.21.3.jar'),
    ('1.20.1', 'fabric-api-0.92.2-1.20.1.jar'),
])
def test_modrinth_picks_the_file_for_the_game_version(game_version, expected_filename):
    assert get_download_url(MODRINTH_FABRIC_API, game_version, 'fabric')[1] == expected_filename


def test_modrinth_loader_is_case_insensitive_and_must_match():
    assert get_download_url(MODRINTH_FABRIC_API, '1.20.1', 'QUILT')[1] == 'fabric-api-0.92.2-1.20.1.jar'  # This file supports fabric and quilt

    with pytest.raises(NoModFileAvailable):
        get_download_url(MODRINTH_FABRIC_API, '1.21.4', 'Quilt')  # 1.21.4 only has a fabric file


def test_modrinth_mod_without_file_for_the_version_raises():
    with pytest.raises(NoModFileAvailable, match='1.21.4'):
        get_download_url('https://modrinth.com/mod/old-mod', '1.21.4', 'Fabric')


def test_modrinth_unknown_mod_raises():
    with pytest.raises(ModNotExisting):
        get_download_url('https://modrinth.com/mod/does-not-exist', '1.21.4', 'Fabric')


@pytest.mark.parametrize('version, loader, missing', [('', 'Fabric', 'game_version'), ('1.21.4', '', 'mod_loader')])
def test_modrinth_empty_arguments_raise_before_any_request(fake_internet, version, loader, missing):
    with pytest.raises(EmptyArguments, match=missing):
        get_download_url(MODRINTH_FABRIC_API, version, loader)
    fake_internet.assert_no_requests()


def test_modrinth_rate_limit_raises_api_cooldown(fake_internet):
    fake_internet.add_route('https://api.modrinth.com/v2/project/fabric-api/version', file='modrinth_versions_fabric-api.json', headers={'X-Ratelimit-Remaining': '0'})
    with pytest.raises(APICooldown):
        get_download_url(MODRINTH_FABRIC_API, '1.21.4', 'Fabric')


def test_modrinth_offline_returns_empty_result(fake_internet):
    fake_internet.go_offline()
    assert get_download_url(MODRINTH_FABRIC_API, '1.21.4', 'Fabric') == ('', '')


# =========================================================================================== get_download_url: CurseForge
def test_curseforge_download_url_uses_the_cfwidget_api_with_version_and_loader(fake_internet):
    url, filename = get_download_url(CURSEFORGE_JEI, '1.21.4', 'Fabric')

    assert filename == 'jei-1.21.4-fabric-19.0.0.jar'
    assert url == 'https://edge.forgecdn.net/files/5953/701/jei-1.21.4-fabric-19.0.0.jar'  # File id 5953701 is split after 4 digits
    assert fake_internet.urls() == ['https://api.cfwidget.com/minecraft/mc-mods/jei?version=1.21.4&loader=fabric']


def test_curseforge_spaces_in_the_filename_are_escaped(fake_internet):
    fake_internet.add_route('https://api.cfwidget.com/minecraft/mc-mods/spacey?version=1.21.4&loader=fabric', json={'download': {'id': 1234567, 'name': 'Spacey Mod 1.0.jar'}})
    url, filename = get_download_url('https://www.curseforge.com/minecraft/mc-mods/spacey', '1.21.4', 'fabric')
    assert (url, filename) == ('https://edge.forgecdn.net/files/1234/567/Spacey%20Mod%201.0.jar', 'Spacey Mod 1.0.jar')


def test_curseforge_202_means_try_again_later(fake_internet):
    fake_internet.add_route('https://api.cfwidget.com/minecraft/mc-mods/jei?version=1.20.1&loader=fabric', status=202, json={'message': 'queued'})
    with pytest.raises(TryAgainLater):
        get_download_url(CURSEFORGE_JEI, '1.20.1', 'Fabric')


def test_curseforge_unknown_mod_raises(fake_internet):
    fake_internet.add_route('https://api.cfwidget.com/minecraft/mc-mods/nothing?version=1.21.4&loader=fabric', status=404, json={'error': 'not found'})
    with pytest.raises(ModNotExisting):
        get_download_url('https://www.curseforge.com/minecraft/mc-mods/nothing', '1.21.4', 'Fabric')


def test_curseforge_without_file_for_version_raises(fake_internet):
    fake_internet.add_route('https://api.cfwidget.com/minecraft/mc-mods/jei?version=1.19.4&loader=fabric', json={'message': 'no file'})
    with pytest.raises(NoModFileAvailable):
        get_download_url(CURSEFORGE_JEI, '1.19.4', 'Fabric')


def test_curseforge_offline_returns_empty_result(fake_internet):
    fake_internet.go_offline()
    assert get_download_url(CURSEFORGE_JEI, '1.21.4', 'Fabric') == ('', '')


def test_unsupported_website_raises_without_requests(fake_internet):
    with pytest.raises(InvalidModBaseUrl):
        get_download_url('https://example.com/some/mod', '1.21.4', 'Fabric')
    fake_internet.assert_no_requests()


# ================================================================================================================ get_mod_data
def test_get_mod_data_for_modrinth_returns_and_caches_the_data(fake_internet):
    description, loaders, supported_versions = get_mod_data(MODRINTH_FABRIC_API, never_block=False)

    # Markdown is converted to HTML and the HTML wrapper tags (which markdown can't handle) are removed
    assert '<h1>Fabric API</h1>' in description
    assert '<strong>hooks</strong>' in description
    assert '<li>first point</li>' in description
    assert '<div' not in description and '</div>' not in description
    assert loaders == ['Fabric', 'Quilt']
    assert supported_versions == ['1.21.4', '1.21.3', '1.20.1', '1.19.4']  # Newest first, snapshots (24w14a) are left out

    assert sorted(fake_internet.urls()) == sorted(['https://api.modrinth.com/v2/project/fabric-api', 'https://cdn.modrinth.com/data/P7dR8mSH/icon.png'])
    assert directory_listing(MODRINTH_CACHE) == ['fabric-api.json', 'fabric-api.png']
    assert (MODRINTH_CACHE / 'fabric-api.png').read_bytes() == ICON_BYTES
    cached = read_json(MODRINTH_CACHE / 'fabric-api.json')
    assert cached['loaders'] == loaders and cached['supported_versions'] == supported_versions and cached['description'] == description
    assert directory_listing(CURSEFORGE_CACHE) == []


def test_get_mod_data_for_curseforge_returns_and_caches_the_data(fake_internet):
    description, loaders, supported_versions = get_mod_data(CURSEFORGE_JEI, never_block=False)

    assert description == '<p>View items and recipes</p>'
    assert loaders == ['Fabric', 'Forge']
    assert supported_versions == ['1.21.4', '1.20.1']
    assert sorted(fake_internet.urls()) == sorted(['https://api.cfwidget.com/minecraft/mc-mods/jei', 'https://media.forgecdn.net/avatars/thumbnails/jei.png'])
    assert directory_listing(CURSEFORGE_CACHE) == ['jei.json', 'jei.png']
    assert (CURSEFORGE_CACHE / 'jei.png').read_bytes() == ICON_BYTES
    assert directory_listing(MODRINTH_CACHE) == []


def test_get_mod_data_calls_the_callback_with_the_data_and_the_extra_arguments():
    calls = []

    get_mod_data(MODRINTH_FABRIC_API, lambda *arguments: calls.append(arguments), ('Fabric API', MODRINTH_FABRIC_API))

    assert len(calls) == 1
    description, loaders, supported_versions, mod_name, mod_url = calls[0]
    assert '<h1>Fabric API</h1>' in description
    assert (loaders, mod_name, mod_url) == (['Fabric', 'Quilt'], 'Fabric API', MODRINTH_FABRIC_API)
    assert supported_versions[0] == '1.21.4'


def test_get_mod_data_in_a_thread_returns_the_data_after_the_thread_finished():
    # The default (never_block=True) updates in a background thread. The tests run that thread inline,
    # so the freshly written cache can already be returned. With a real thread the first call would return ('', [], []).
    description, loaders, supported_versions = get_mod_data(MODRINTH_FABRIC_API)
    assert loaders == ['Fabric', 'Quilt'] and supported_versions[0] == '1.21.4' and description


def test_get_mod_data_always_refreshes_from_the_internet_even_if_cached(fake_internet):
    get_mod_data(MODRINTH_FABRIC_API, never_block=False)
    fake_internet.clear_history()

    get_mod_data(MODRINTH_FABRIC_API)

    fake_internet.assert_requested('https://api.modrinth.com/v2/project/fabric-api')


def test_get_mod_data_returns_the_cache_when_offline(fake_internet):
    get_mod_data(MODRINTH_FABRIC_API, never_block=False)
    fake_internet.go_offline()

    description, loaders, supported_versions = get_mod_data(MODRINTH_FABRIC_API)

    assert loaders == ['Fabric', 'Quilt'] and supported_versions[0] == '1.21.4' and '<h1>' in description


def test_get_mod_data_offline_without_cache_returns_nothing(fake_internet):
    fake_internet.go_offline()
    assert get_mod_data(MODRINTH_FABRIC_API) == ('', [], [])
    assert get_mod_data(MODRINTH_FABRIC_API, never_block=False) == ('', [], [])


def test_get_mod_data_for_unknown_mod_raises_when_blocking():
    with pytest.raises(ModNotExisting):
        get_mod_data('https://modrinth.com/mod/does-not-exist', never_block=False)


def test_get_mod_data_for_unknown_mod_fails_inside_the_thread_otherwise(inline_thread_errors):
    assert get_mod_data('https://modrinth.com/mod/does-not-exist') == ('', [], [])

    assert [type(error) for _, error in inline_thread_errors] == [ModNotExisting]
    inline_thread_errors.clear()  # Expected


def test_get_mod_data_for_unsupported_website_raises():
    with pytest.raises(InvalidModBaseUrl):
        get_mod_data('https://example.com/mod')


def test_get_mod_data_without_icon_url_skips_the_icon_download(fake_internet):
    get_mod_data('https://modrinth.com/mod/old-mod', never_block=False)

    assert directory_listing(MODRINTH_CACHE) == ['old-mod.json']
    assert fake_internet.urls() == ['https://api.modrinth.com/v2/project/old-mod']


def test_modrinth_rate_limit_in_get_mod_data_raises(fake_internet):
    fake_internet.add_route('https://api.modrinth.com/v2/project/sodium', file='modrinth_project_sodium.json', headers={'X-Ratelimit-Remaining': '0'})
    with pytest.raises(APICooldown):
        get_mod_data('https://modrinth.com/mod/sodium', never_block=False)


# ============================================================================================================ get_mod_icon_path
def test_get_mod_icon_path_downloads_a_missing_icon(fake_internet):
    path = get_mod_icon_path(MODRINTH_FABRIC_API)

    assert path == MODRINTH_CACHE / 'fabric-api.png'
    assert path.read_bytes() == ICON_BYTES
    fake_internet.assert_requested('https://cdn.modrinth.com/data/P7dR8mSH/icon.png')


def test_get_mod_icon_path_for_curseforge(fake_internet):
    assert get_mod_icon_path(CURSEFORGE_JEI) == CURSEFORGE_CACHE / 'jei.png'
    assert (CURSEFORGE_CACHE / 'jei.png').exists()


def test_get_mod_icon_path_uses_an_existing_icon_without_requests(fake_internet):
    get_mod_icon_path(MODRINTH_FABRIC_API)
    fake_internet.clear_history()

    assert get_mod_icon_path(MODRINTH_FABRIC_API) == MODRINTH_CACHE / 'fabric-api.png'
    fake_internet.assert_no_requests()


def test_get_mod_icon_path_for_unsupported_website_raises():
    with pytest.raises(InvalidModBaseUrl):
        get_mod_icon_path('https://example.com/mod')


# ======================================================================================== _remove_unnecessary_html_tags
@pytest.mark.parametrize('text, expected', [
    ('<div align="center">Hello</div>', 'Hello'),
    ('<CENTER>Hi</CENTER>', 'Hi'),
    ('<details><summary>Title</summary>Body</details>', 'TitleBody'),
    ('<p>Keep <b>this</b></p>', '<p>Keep <b>this</b></p>'),
    ('<divider>not a div</divider>', '<divider>not a div</divider>'),
])
def test_remove_unnecessary_html_tags(text, expected):
    assert mod._remove_unnecessary_html_tags(text) == expected
