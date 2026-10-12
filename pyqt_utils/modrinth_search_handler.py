import json

# noinspection PyPackageRequirements
from PyQt6.QtCore import QObject, QTimer, QUrl, QUrlQuery, pyqtSignal
# noinspection PyPackageRequirements
from PyQt6.QtGui import QPixmap
# noinspection PyPackageRequirements
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest


MODRINTH_SEARCH_URL = "https://api.modrinth.com/v2/search"
MODRINTH_BASE_MOD_URL = "https://modrinth.com/mod/"


class ModrinthSearcher(QObject):
    results_ready = pyqtSignal(list)
    search_started = pyqtSignal(str)
    search_failed = pyqtSignal(str)

    def __init__(self, parent=None, debounce_ms=250, limit=20):
        super().__init__(parent)

        self.limit = limit
        self.network_manager = QNetworkAccessManager(self)
        self.current_reply = None
        self.search_generation = 0

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(debounce_ms)
        # noinspection PyUnresolvedReferences
        self.search_timer.timeout.connect(self._perform_search)

        self.current_query = ""

    def search(self, query: str):
        self.current_query = query.strip()

        if not self.current_query:
            self.cancel()
            return

        self.search_timer.start()

    def cancel(self):
        self.search_timer.stop()
        self.search_generation += 1

        if self.current_reply is not None:
            self.current_reply.abort()
            self.current_reply = None

    def _perform_search(self):
        query = self.current_query

        if not query:
            return

        self.search_generation += 1
        generation = self.search_generation

        if self.current_reply is not None:
            self.current_reply.abort()
            self.current_reply = None

        url = QUrl(MODRINTH_SEARCH_URL)
        url_query = QUrlQuery()
        url_query.addQueryItem("query", query)
        url_query.addQueryItem("facets", json.dumps([["project_type:mod"]], separators=(",", ":")))
        url_query.addQueryItem("limit", str(self.limit))
        url_query.addQueryItem("index", "relevance")
        url.setQuery(url_query)

        request = QNetworkRequest(url)
        request.setRawHeader(b"User-Agent", b"shueppin/PackedMC")

        # noinspection PyUnresolvedReferences
        self.search_started.emit(query)
        reply = self.network_manager.get(request)
        self.current_reply = reply
        reply.setProperty("search_generation", generation)
        # noinspection PyUnresolvedReferences
        reply.finished.connect(lambda: self._reply_finished(reply))

    def _reply_finished(self, reply):
        generation = reply.property("search_generation")

        if generation != self.search_generation:
            reply.deleteLater()
            return

        if self.current_reply is reply:
            self.current_reply = None

        if reply.error() != reply.NetworkError.NoError:
            error = reply.errorString()
            reply.deleteLater()
            # noinspection PyUnresolvedReferences
            self.search_failed.emit(error)
            return

        try:
            payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
            hits = payload.get("hits", [])
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
            reply.deleteLater()
            # noinspection PyUnresolvedReferences
            self.search_failed.emit(str(exc))
            return

        reply.deleteLater()
        # noinspection PyUnresolvedReferences
        self.results_ready.emit(hits)


class ModrinthIconLoader(QObject):
    icon_ready = pyqtSignal(str, QPixmap)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.network_manager = QNetworkAccessManager(self)
        self.cache = {}

    def load(self, url: str):
        if not url:
            return

        if url in self.cache:
            # noinspection PyUnresolvedReferences
            self.icon_ready.emit(url, self.cache[url])
            return

        request = QNetworkRequest(QUrl(url))
        reply = self.network_manager.get(request)
        # noinspection PyUnresolvedReferences
        reply.finished.connect(lambda: self._reply_finished(reply, url))

    def _reply_finished(self, reply, url):
        if reply.error() != reply.NetworkError.NoError:
            reply.deleteLater()
            return

        pixmap = QPixmap()
        pixmap.loadFromData(bytes(reply.readAll()))

        if not pixmap.isNull():
            self.cache[url] = pixmap
            # noinspection PyUnresolvedReferences
            self.icon_ready.emit(url, pixmap)

        reply.deleteLater()
