"""
A fake internet for the PackedMC tests.

Nothing in the test suite is allowed to touch the real network. Instead, every HTTP request made by PackedMC is answered
from a list of routes. The default routes live in ``tests/http_responses/routes.json`` and the bodies they point to live
next to it as plain files, so you can simply save a real API answer in that directory and add a route for it.

Two network stacks are intercepted:

* ``requests`` (used by ``minecraft_api`` and ``utils``): we replace ``HTTPAdapter.send``. This is the lowest level of
  ``requests``, so ``requests.get``, ``requests.post``, ``Session.get`` ... are all covered and the code under test still
  receives real ``requests.Response`` objects.
* ``QNetworkAccessManager`` (used by the Modrinth search in ``pyqt_utils``): we replace the class used by
  ``pyqt_utils.modrinth_search_handler`` with a fake one, which answers asynchronously like the real one.

Every request is recorded (``FakeInternet.requests``). A request that matches no route is recorded in
``FakeInternet.unmatched`` and raises ``UnregisteredRequest``. The ``fake_internet`` fixture additionally fails the test
during teardown if anything was unmatched, so a code path that swallows the exception can not hide a wrong URL.

Which route answers a request: routes added inside of a test (``fake_internet.add_route``) always beat the default routes
from routes.json. Within the same group the most specific route wins (no wildcard, more ``match_query`` entries) and
after that the one registered last.

routes.json format (a list):

    {
      "url": "https://api.example.com/some/path",     # may contain * wildcards in the path
      "match_query": {"query": "sodium"},              # optional, only match if these query parameters are present
      "file": "body.json"  |  "json": {...}  |  "text": "...",
      "status": 200,                                   # optional
      "headers": {"X-Ratelimit-Remaining": "299"}      # optional
    }

A "?a=b" inside the url is treated exactly like ``match_query``.
"""
from __future__ import annotations

import fnmatch
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, parse_qs

import requests
from PyQt6.QtCore import QObject, QTimer, QByteArray, pyqtSignal
from PyQt6.QtNetwork import QNetworkReply, QNetworkRequest

logger = logging.getLogger(__name__)

RESPONSES_DIRECTORY = Path(__file__).resolve().parent / 'http_responses'
ROUTES_FILE = RESPONSES_DIRECTORY / 'routes.json'


class UnregisteredRequest(Exception):
    """ Raised when PackedMC requests a URL for which no fake answer was registered. """


@dataclass
class Route:
    url: str  # Without query. May contain wildcards
    query: dict[str, str] = field(default_factory=dict)
    status: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    content: bytes = b''
    order: int = 0
    is_default: bool = False  # Loaded from routes.json (as opposed to added by a test)

    def specificity(self) -> tuple[int, int, int, int]:
        has_wildcard = '*' in self.url
        return (0 if self.is_default else 1), (0 if has_wildcard else 1), len(self.query), self.order

    def matches(self, url_without_query: str, query: dict[str, list[str]]) -> bool:
        if '*' in self.url:
            if not fnmatch.fnmatchcase(url_without_query, self.url):
                return False
        elif url_without_query != self.url:
            return False

        return all(key in query and value in query[key] for key, value in self.query.items())


@dataclass
class RecordedRequest:
    method: str
    url: str
    headers: dict[str, str]
    body: Any
    timeout: Any
    source: str  # 'requests' or 'qt'
    status: int | None = None  # None if no route matched

    @property
    def url_without_query(self) -> str:
        return url_without_query(self.url)

    @property
    def query(self) -> dict[str, list[str]]:
        return parse_qs(urlsplit(self.url).query, keep_blank_values=True)

    def header(self, name: str) -> str | None:
        for key, value in self.headers.items():
            if key.lower() == name.lower():
                return value
        return None

    def __str__(self):
        return f'{self.method} {self.url}'


def url_without_query(url: str) -> str:
    parts = urlsplit(url)
    return f'{parts.scheme}://{parts.netloc}{parts.path}'


class FakeInternet:
    def __init__(self):
        self.default_routes = self._load_manifest()
        self.routes: list[Route] = []
        self.requests: list[RecordedRequest] = []
        self.unmatched: list[RecordedRequest] = []
        self.offline = False
        self.reset()

    # ------------------------------------------------------------------ routes
    @staticmethod
    def _load_manifest() -> list[dict]:
        with open(ROUTES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)

    def reset(self):
        """ Back to the default routes, an empty history and an online connection. """
        self.routes = []
        self.requests = []
        self.unmatched = []
        self.offline = False
        for entry in self.default_routes:
            self.add_route(**entry)
        for route in self.routes:
            route.is_default = True

    def add_route(self, url: str, *, file: str = None, json: Any = None, text: str = None, content: bytes = None, status: int = 200, headers: dict[str, str] = None, match_query: dict[str, str] = None):
        """ Register (or override) the answer for a URL. Without a body the answer is empty. """
        import json as json_module

        if file is not None:
            body = (RESPONSES_DIRECTORY / file).read_bytes()
        elif json is not None:
            body = json_module.dumps(json).encode('utf-8')
        elif text is not None:
            body = text.encode('utf-8')
        elif content is not None:
            body = content
        else:
            body = b''

        query = dict(match_query or {})
        parts = urlsplit(url)
        for key, values in parse_qs(parts.query, keep_blank_values=True).items():
            query[key] = values[0]

        route_headers = dict(headers or {})
        if (file or '').endswith('.json') or json is not None:
            route_headers.setdefault('Content-Type', 'application/json')

        self.routes.append(Route(url=url_without_query(url), query=query, status=status, headers=route_headers, content=body, order=len(self.routes)))

    def go_offline(self):
        """ Every request raises ``requests.exceptions.ConnectionError`` (or a network error in Qt). """
        self.offline = True

    def go_online(self):
        self.offline = False

    def _find_route(self, url: str) -> Route | None:
        parts = urlsplit(url)
        base_url = url_without_query(url)
        query = parse_qs(parts.query, keep_blank_values=True)

        candidates = [route for route in self.routes if route.matches(base_url, query)]
        if not candidates:
            return None
        return max(candidates, key=Route.specificity)

    def _handle(self, method: str, url: str, headers: dict[str, str], body: Any, timeout: Any, source: str) -> Route:
        recorded = RecordedRequest(method=method, url=url, headers=dict(headers), body=body, timeout=timeout, source=source)
        self.requests.append(recorded)

        if self.offline:
            recorded.status = None
            raise requests.exceptions.ConnectionError(f'The fake internet is offline ({method} {url})')

        route = self._find_route(url)
        if route is None:
            self.unmatched.append(recorded)
            raise UnregisteredRequest(f'PackedMC requested {method} {url}, but no fake answer is registered for it. Add a route to tests/http_responses/routes.json or use fake_internet.add_route(...).')

        recorded.status = route.status
        return route

    # ----------------------------------------------------------- requests glue
    def send(self, adapter, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        """ Replacement for ``requests.adapters.HTTPAdapter.send``. """
        route = self._handle(request.method, request.url, dict(request.headers), request.body, timeout, 'requests')

        response = requests.Response()
        response.status_code = route.status
        response.headers = requests.structures.CaseInsensitiveDict(route.headers)
        response._content = route.content
        response._content_consumed = True
        response.url = request.url
        response.encoding = 'utf-8'
        response.reason = 'OK' if route.status < 400 else 'ERROR'
        response.request = request
        return response

    # -------------------------------------------------------------- qt glue
    def qt_get(self, request: QNetworkRequest) -> 'FakeQtReply':
        url = request.url().toString()
        headers = {bytes(name).decode(): bytes(request.rawHeader(name)).decode() for name in request.rawHeaderList()}

        try:
            route = self._handle('GET', url, headers, None, None, 'qt')
        except (requests.exceptions.ConnectionError, UnregisteredRequest):
            return FakeQtReply(error=QNetworkReply.NetworkError.HostNotFoundError, error_string=f'No fake answer for {url}')

        if route.status >= 400:
            error = QNetworkReply.NetworkError.ContentNotFoundError if route.status == 404 else QNetworkReply.NetworkError.UnknownContentError
            return FakeQtReply(error=error, error_string=f'HTTP {route.status}', content=route.content)

        return FakeQtReply(content=route.content)

    # ---------------------------------------------------------- assertions
    def urls(self, method: str = None) -> list[str]:
        """ All requested URLs (including the query) in the order they were requested. """
        return [r.url for r in self.requests if method is None or r.method == method]

    def requests_to(self, url: str) -> list[RecordedRequest]:
        """ All requests whose URL equals ``url`` (with query) or whose URL without query equals ``url``. """
        base = url_without_query(url)
        if '?' in url:
            return [r for r in self.requests if r.url == url]
        return [r for r in self.requests if r.url_without_query == base]

    def assert_requested(self, url: str, times: int = 1) -> list[RecordedRequest]:
        found = self.requests_to(url)
        assert len(found) == times, f'Expected {times} request(s) to {url}, but found {len(found)}. All requests: {self.urls()}'
        return found

    def assert_not_requested(self, url: str):
        found = self.requests_to(url)
        assert not found, f'Did not expect a request to {url}, but found {len(found)}.'

    def assert_no_requests(self):
        assert not self.requests, f'Expected no network requests, but found: {self.urls()}'

    def clear_history(self):
        self.requests.clear()
        self.unmatched.clear()


class FakeQtReply(QObject):
    """ A stand-in for QNetworkReply. The ``finished`` signal is emitted asynchronously, like the real thing. """
    finished = pyqtSignal()
    NetworkError = QNetworkReply.NetworkError  # The code under test accesses it via the reply instance

    def __init__(self, content: bytes = b'', error=QNetworkReply.NetworkError.NoError, error_string: str = ''):
        super().__init__()
        self._content = content
        self._error = error
        self._error_string = error_string
        self._finished = False
        QTimer.singleShot(0, self._finish)

    def _finish(self):
        if self._finished:
            return
        self._finished = True
        self.finished.emit()

    def abort(self):
        if not self._finished:
            self._error = QNetworkReply.NetworkError.OperationCanceledError
            self._error_string = 'Operation canceled'
            self._finished = True
            self.finished.emit()

    def error(self):
        return self._error

    def errorString(self) -> str:
        return self._error_string

    def readAll(self) -> QByteArray:
        return QByteArray(self._content)


def make_fake_network_access_manager(internet: FakeInternet):
    class FakeQNetworkAccessManager(QObject):
        def __init__(self, parent=None):
            super().__init__(parent)

        def get(self, request: QNetworkRequest) -> FakeQtReply:
            return internet.qt_get(request)

    return FakeQNetworkAccessManager
