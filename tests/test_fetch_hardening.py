"""The fetch layer stays on the hosts it trusts, waits out Wayback's
outages, and never reads an unbounded body."""

import http.server
import io
import os
import threading
import time
from unittest.mock import Mock

import pytest
import requests
from urllib3.exceptions import MaxRetryError, ReadTimeoutError

from wayback_archive.config import Config
from wayback_archive.downloader import WaybackDownloader, _host_matches

TS = "20200101000000"
WAYBACK = f"https://web.archive.org/web/{TS}/"
ARCHIVED = {"memento-datetime": "Wed, 01 Jan 2020 00:00:00 GMT"}
CHALLENGE = b"<html><head><title>Just a moment...</title></head><body></body></html>"


@pytest.fixture
def dl():
    os.environ["WAYBACK_URL"] = WAYBACK + "http://example.com/"
    yield WaybackDownloader(Config())
    os.environ.pop("WAYBACK_URL", None)


class _Response:
    def __init__(self, status, body=b"", headers=None, url=""):
        self.status_code = status
        self.content = body
        self.headers = headers or {}
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(response=self)

    def close(self):
        pass


class _Recorder:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.handler(url, kwargs)


class TestHostMatches:
    FONTS = ("fonts.gstatic.com",)

    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.com\\.fonts.gstatic.com/x",
            "https://fonts.gstatic.com@evil.com/x",
            "https://evil.com%2f.fonts.gstatic.com/x",
            "https://evil.com\t.fonts.gstatic.com/x",
            "https://evil.com .fonts.gstatic.com/x",
            "https://evil.com\x00.fonts.gstatic.com/x",
            "https://évil.fonts.gstatic.com/x",
            "https://notfonts.gstatic.com/x",
            "https://fonts.gstatic.com.evil.com/x",
            "/relative/path",
            "https://fonts.gstatic.com]/x",
            "https://[fonts.gstatic.com]/x",
        ],
    )
    def test_spoofed_hosts_never_match(self, url):
        assert not _host_matches(url, self.FONTS)

    def test_requests_connects_to_the_host_before_a_backslash(self):
        """Why the backslash is refused: urllib and requests disagree on the host."""
        prepared = requests.Request("GET", "https://evil.com\\.fonts.gstatic.com/x").prepare()
        assert prepared.url.startswith("https://evil.com/")

    @pytest.mark.parametrize(
        "url",
        ["https://fonts.gstatic.com/x", "https://FONTS.gstatic.com./x", "https://a.fonts.gstatic.com:443/x"],
    )
    def test_the_host_and_its_subdomains_match(self, url):
        assert _host_matches(url, self.FONTS)


class TestLiveCdn:
    def test_http_is_upgraded_to_https(self, dl):
        dl.session.get = _Recorder(lambda url, kw: _Response(200, b"/* js */", url=url))
        assert dl._fetch_from_live_cdn("http://code.jquery.com/jquery-3.7.1.min.js") == b"/* js */"
        assert [url for url, _ in dl.session.get.calls] == ["https://code.jquery.com/jquery-3.7.1.min.js"]
        assert dl.session.get.calls[0][1]["allow_redirects"] is False

    @pytest.mark.parametrize(
        "url",
        [
            "https://code.jquery.com:8443/jquery.min.js",
            "http://code.jquery.com:8080/jquery.min.js",
            "ftp://code.jquery.com/jquery.min.js",
            "https://evil.com\\.code.jquery.com/jquery.min.js",
        ],
    )
    def test_other_ports_schemes_and_spoofs_send_nothing(self, dl, url):
        dl.session.get = _Recorder(lambda url, kw: _Response(200, b"x", url=url))
        assert dl._fetch_from_live_cdn(url) is None
        assert dl.session.get.calls == []

    def test_an_answer_from_another_host_is_dropped(self, dl):
        dl.session.get = _Recorder(lambda url, kw: _Response(200, b"evil", url="https://evil.com/x.js"))
        assert dl._fetch_from_live_cdn("https://code.jquery.com/jquery.min.js") is None

    def test_live_cdn_is_not_paced(self, dl, monkeypatch):
        dl.config.request_delay = 5
        sleeps = []
        monkeypatch.setattr(time, "sleep", sleeps.append)
        dl.session.get = _Recorder(lambda url, kw: _Response(200, b"x", url=url))
        assert dl._fetch_from_live_cdn("https://code.jquery.com/jquery.min.js") == b"x"
        assert sleeps == []


class TestStaysOnWayback:
    @pytest.mark.parametrize("url", ["http://example.com/logo.png", "http://example.com/about"])
    def test_a_redirect_off_wayback_is_never_content(self, dl, url):
        dl.session.get = _Recorder(lambda u, kw: _Response(200, b"<html>evil</html>", url="https://evil.com/"))
        assert dl.download_file(url) is None

    def test_an_answer_from_wayback_is_content(self, dl):
        dl.session.get = _Recorder(lambda url, kw: _Response(200, b"PNG", url=WAYBACK + "http://example.com/x.png"))
        assert dl.download_file("http://example.com/x.png") == b"PNG"

    def test_every_wayback_request_streams(self, dl):
        dl.session.get = _Recorder(lambda url, kw: _Response(404))
        dl.download_file("http://example.com/missing.png")
        assert dl.session.get.calls
        assert all(kw.get("stream") is True for _, kw in dl.session.get.calls)


class TestPacing:
    def test_no_delay_by_default(self, dl, monkeypatch):
        sleeps = []
        monkeypatch.setattr(time, "sleep", sleeps.append)
        dl.session.get = _Recorder(lambda url, kw: _Response(404))
        dl.download_file("http://example.com/gone.png")
        assert sleeps == []

    def test_each_wayback_request_waits_the_delay_with_jitter(self, dl, monkeypatch):
        dl.config.request_delay = 2.0
        sleeps = []
        monkeypatch.setattr(time, "sleep", sleeps.append)
        dl.session.get = _Recorder(lambda url, kw: _Response(404))
        dl.download_file("http://example.com/gone.png")
        assert len(dl.session.get.calls) > 1
        assert len(sleeps) == len(dl.session.get.calls)
        assert all(1.6 <= s <= 2.4 for s in sleeps)
        assert len(set(sleeps)) > 1


class TestTimestampFallback:
    def test_a_bad_variant_is_skipped_for_the_next(self, dl):
        variants = iter([_Response(200, CHALLENGE), _Response(200, b"GOOD")])
        dl.session.get = _Recorder(lambda url, kw: _Response(404) if f"/{TS}" in url else next(variants))
        assert dl.download_file("http://example.com/logo.png") == b"GOOD"

    def test_an_archived_error_variant_is_never_content(self, dl):
        dl.session.get = _Recorder(
            lambda url, kw: _Response(404) if f"/{TS}" in url else _Response(200, CHALLENGE, headers=ARCHIVED)
        )
        assert dl.download_file("http://example.com/logo.png") is None

    def test_a_429_stops_the_variant_search(self, dl):
        dl.session.get = _Recorder(lambda url, kw: _Response(404) if f"/{TS}" in url else _Response(429))
        assert dl.download_file("http://example.com/logo.png") is None
        assert len(dl.session.get.calls) == 2
        assert dl._last_failure == "throttled"


class TestUnavailable:
    def test_a_5xx_after_the_retries_is_a_refusal(self, dl):
        dl.session.get = _Recorder(lambda url, kw: _Response(503, b"Temporarily Offline"))
        assert dl.download_file("http://example.com/about") is None
        assert dl._last_failure == "unavailable"
        # The page's plain URL is not asked for too.
        assert len(dl.session.get.calls) == 1
        assert dl.download_file("http://example.com/logo.png") is None
        assert dl._last_failure == "unavailable"

    def test_a_read_timeout_after_the_retries_is_a_refusal(self, dl):
        def handler(url, kw):
            raise requests.exceptions.ConnectionError(MaxRetryError(None, url, ReadTimeoutError(None, url, "slow")))

        dl.session.get = _Recorder(handler)
        assert dl.download_file("http://example.com/about") is None
        assert dl._last_failure == "unavailable"

    def test_no_answer_is_still_a_connection_refusal(self, dl):
        def handler(url, kw):
            raise requests.exceptions.ConnectionError("refused")

        dl.session.get = _Recorder(handler)
        assert dl.download_file("http://example.com/about") is None
        assert dl._last_failure == "connection"


class _Sequence(http.server.BaseHTTPRequestHandler):
    """Answers each GET with the next (status, headers, body, delay)."""

    def do_GET(self):
        status, headers, body, delay = self.server.answers.pop(0)
        self.server.hits += 1
        time.sleep(delay)
        try:
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            if "Content-Length" not in headers:
                self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            pass

    def log_message(self, *args):
        pass


@pytest.fixture
def local_server():
    """A threaded server on 127.0.0.1 (no real network), so a slow answer
    does not hold up the retry behind it."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Sequence)
    server.daemon_threads = True
    server.answers, server.hits = [], 0
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _session_on(dl, server):
    """The Wayback adapter pointed at server, without the backoff sleeps."""
    base = f"http://127.0.0.1:{server.server_port}/"
    adapter = dl.session.get_adapter("https://web.archive.org/web/")
    adapter.max_retries = adapter.max_retries.new(backoff_factor=0, backoff_jitter=0)
    dl.session.mount(base, adapter)
    return dl.session, base


class TestRetries:
    def test_the_retry_policy(self, dl):
        retry = dl.session.get_adapter("https://web.archive.org/web/").max_retries
        assert retry.total == 5
        assert retry.backoff_factor == 1
        assert retry.backoff_jitter > 0
        assert set(retry.status_forcelist) == {429, 502, 503, 504}
        assert retry.RETRY_AFTER_MAX == 120

    def test_wayback_5xx_is_retried(self, dl, local_server):
        local_server.answers = [(502, {}, b"", 0), (503, {}, b"", 0), (504, {}, b"", 0), (200, {}, b"ok", 0)]
        session, base = _session_on(dl, local_server)
        assert session.get(base + "x", timeout=5).status_code == 200
        assert local_server.hits == 4

    def test_an_archived_503_is_not_retried(self, dl, local_server):
        local_server.answers = [(503, ARCHIVED, b"", 0), (200, {}, b"ok", 0)]
        session, base = _session_on(dl, local_server)
        assert session.get(base + "x", timeout=5).status_code == 503
        assert local_server.hits == 1

    def test_a_read_timeout_is_retried(self, dl, local_server):
        local_server.answers = [(200, {}, b"slow", 0.5), (200, {}, b"ok", 0)]
        session, base = _session_on(dl, local_server)
        response = session.get(base + "x", timeout=0.2)
        assert response.status_code == 200
        assert response.content == b"ok"
        assert local_server.hits == 2


class TestBodyCap:
    def _get(self, server):
        return requests.get(f"http://127.0.0.1:{server.server_port}/x", stream=True, timeout=5)

    def test_a_body_past_the_cap_is_refused(self, dl, local_server):
        dl.MAX_BODY_BYTES = 1000
        local_server.answers = [(200, {}, b"x" * 5000, 0)]
        with pytest.raises(Exception, match="too large"):
            dl._read_body(self._get(local_server))

    def test_a_declared_length_past_the_cap_is_refused_unread(self, dl, local_server):
        dl.MAX_BODY_BYTES = 1000
        local_server.answers = [(200, {"Content-Length": "999999"}, b"x" * 10, 0)]
        with pytest.raises(Exception, match="too large"):
            dl._read_body(self._get(local_server))

    def test_a_body_under_the_cap_is_kept_for_every_later_read(self, dl, local_server):
        local_server.answers = [(200, ARCHIVED, CHALLENGE, 0)]
        response = self._get(local_server)
        assert dl._read_body(response) == CHALLENGE
        assert response.content == CHALLENGE
        assert dl._bad_capture_reason(response) == "Cloudflare challenge page"

    def test_a_test_double_gives_its_content(self, dl):
        assert dl._read_body(Mock(content=b"abc")) == b"abc"

    def test_download_file_returns_none_past_the_cap(self, dl):
        dl.MAX_BODY_BYTES = 10

        def big(url, kw):
            response = requests.Response()
            response.status_code = 200
            response.url = WAYBACK + "http://example.com/big.png"
            response.raw = io.BytesIO(b"x" * 100)
            return response

        dl.session.get = _Recorder(big)
        assert dl.download_file("http://example.com/big.png") is None
        assert len(dl.session.get.calls) == 1


class TestCorruptedFont:
    @pytest.mark.parametrize(
        "url, body",
        [
            ("http://example.com/f.woff2?v=3", b"<!DOCTYPE html><html><body>404</body></html>"),
            ("http://example.com/f.ttf", b"\n  <HTML><HEAD><TITLE>Error</TITLE>"),
            ("http://example.com/f.otf", b"<?xml version='1.0'?><head></head>"),
        ],
    )
    def test_an_html_page_is_a_corrupted_font(self, dl, url, body):
        assert dl._is_corrupted_font(body, url)

    @pytest.mark.parametrize(
        "url, body",
        [
            (
                "http://example.com/logo.svg",
                b'<?xml version="1.0"?>\n<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "x"><svg></svg>',
            ),
            ("http://example.com/logo.svg", b'<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "x"><svg></svg>'),
            ("http://example.com/logo.svg?v=2", b"<!DOCTYPE svg><svg></svg>"),
            (
                "http://example.com/card.svg",
                b'<svg xmlns="http://www.w3.org/2000/svg"><foreignObject>'
                b'<body xmlns="http://www.w3.org/1999/xhtml"><p>x</p></body></foreignObject></svg>',
            ),
            ("http://example.com/f.woff2", b"wOF2\x00\x01"),
            ("http://example.com/page.html", b"<!DOCTYPE html><html>"),
        ],
    )
    def test_svg_and_real_fonts_are_kept(self, dl, url, body):
        assert not dl._is_corrupted_font(body, url)


class TestFontProbeStaysOnWayback:
    """The probe of the fonts a stylesheet names goes through _wayback_get."""

    FONT = "http://example.com/f/a.woff2"
    CSS = "@font-face{font-family:A;src:url(/f/a.woff2) format('woff2')}"
    HTML = b"<!DOCTYPE html><html><body>404</body></html>"

    def _probe(self, dl, response):
        dl.session.get = _Recorder(lambda url, kw: response(url))
        dl._check_and_remove_corrupted_fonts_in_css(self.CSS, "http://example.com/s.css")

    def test_an_html_answer_from_wayback_is_a_corrupted_font_and_is_removed(self, dl):
        self._probe(dl, lambda url: _Response(200, self.HTML, url=url))
        assert dl.corrupted_fonts == {self.FONT}
        assert "a.woff2" not in dl._remove_corrupted_fonts_from_css(self.CSS)
        assert all(kw.get("stream") is True for _, kw in dl.session.get.calls)

    def test_an_answer_redirected_off_wayback_is_ignored(self, dl):
        self._probe(dl, lambda url: _Response(200, self.HTML, url="https://evil.com/a.woff2"))
        assert len(dl.session.get.calls) == 1
        assert dl.corrupted_fonts == set()

    def test_a_challenge_page_is_not_a_corrupted_font(self, dl):
        self._probe(dl, lambda url: _Response(200, CHALLENGE, url=url))
        assert dl.corrupted_fonts == set()

    def test_the_probe_is_paced(self, dl, monkeypatch):
        sleeps = []
        monkeypatch.setattr(time, "sleep", sleeps.append)
        dl.config.request_delay = 1.0
        self._probe(dl, lambda url: _Response(200, b"wOF2", url=url))
        assert len(sleeps) == 1


def test_a_byte_cp1252_leaves_undefined_is_kept(dl):
    data = b"Caf\xe9 \x93hi\x94 \x81 end"
    with pytest.raises(UnicodeDecodeError):
        data.decode("cp1252")
    assert dl._decode_text(data, "iso-8859-1") == "Café “hi” \x81 end"


def test_a_failed_download_forgets_the_previous_final_url(dl):
    dl._last_final_url = WAYBACK + "http://other.com/"
    dl.session.get = _Recorder(lambda url, kw: _Response(404))
    assert dl.download_file("http://example.com/gone") is None
    assert dl._last_final_url is None


def test_svg_logs_as_an_image(dl):
    assert dl._get_file_type_from_url("http://example.com/a.svg") == "Image"
