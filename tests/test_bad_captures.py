"""Behaving well when the Wayback Machine says no.

A capture can be an archived error or a Cloudflare challenge (issue #48), a
URL can be missing, Wayback can throttle, and the user can press Ctrl-C.
Each used to cost a pile of blind requests, a silently empty archive with
exit code 0, or an interrupt that was swallowed.
"""

import http.server
import json
import os
import threading

import pytest
import requests

from wayback_archive import cli
from wayback_archive.config import Config
from wayback_archive.downloader import WaybackDownloader

TS = "20200101000000"


def _make_downloader(wayback_url=None, output_dir=None):
    os.environ["WAYBACK_URL"] = wayback_url or f"https://web.archive.org/web/{TS}/http://example.com/"
    config = Config()
    if output_dir is not None:
        config.output_dir = str(output_dir)
    return WaybackDownloader(config)


@pytest.fixture(autouse=True)
def _clean_env():
    yield
    for key in ("WAYBACK_URL", "MAX_FILES", "MAKE_WWW", "MAKE_NON_WWW", "OUTPUT_DIR"):
        os.environ.pop(key, None)


class _Response:
    def __init__(self, status, body=b"", headers=None, url=""):
        self.status_code = status
        self.content = body
        self.headers = headers or {}
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(response=self)

    def json(self):
        return json.loads(self.content)


class _Recorder:
    """session.get stand-in: records every URL and answers with handler(url, kwargs)."""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.handler(url, kwargs)


class TestInterrupt:
    def test_ctrl_c_in_the_page_fetch_is_not_swallowed(self):
        dl = _make_downloader()

        def interrupt(url, kwargs):
            raise KeyboardInterrupt

        dl.session.get = _Recorder(interrupt)
        with pytest.raises(KeyboardInterrupt):
            dl.download_file("http://example.com/about")
        assert len(dl.session.get.calls) == 1

    def test_ctrl_c_during_the_404_search_is_not_swallowed(self):
        dl = _make_downloader()
        answers = iter([_Response(404), _Response(404)])

        def handler(url, kwargs):
            try:
                return next(answers)
            except StopIteration:
                raise KeyboardInterrupt

        dl.session.get = _Recorder(handler)
        with pytest.raises(KeyboardInterrupt):
            dl.download_file("http://example.com/logo.png")
        assert len(dl.session.get.calls) == 3


class TestMissingUrl:
    """Wayback already snaps any timestamp to the nearest capture, so a 404
    is worth at most three distinct probes, not thirteen overlapping ones."""

    def test_missing_asset_costs_at_most_four_requests_all_distinct(self):
        dl = _make_downloader()
        dl.session.get = _Recorder(lambda url, kwargs: _Response(404))
        assert dl.download_file("http://example.com/missing.png") is None
        urls = [url for url, _ in dl.session.get.calls]
        assert len(urls) <= 4
        assert len(set(urls)) == len(urls)

    def test_missing_page_costs_at_most_five_requests_all_distinct(self):
        dl = _make_downloader()
        dl.session.get = _Recorder(lambda url, kwargs: _Response(404))
        assert dl.download_file("http://example.com/gone") is None
        urls = [url for url, _ in dl.session.get.calls]
        assert len(urls) <= 5
        assert len(set(urls)) == len(urls)

    def test_a_probe_that_lands_on_a_good_capture_is_used(self):
        dl = _make_downloader()

        def handler(url, kwargs):
            if f"/{TS}" in url:
                return _Response(404)
            return _Response(200, b"PNGDATA")

        dl.session.get = _Recorder(handler)
        assert dl.download_file("http://example.com/logo.png") == b"PNGDATA"


CDX = "https://web.archive.org/cdx/search/cdx"
ARCHIVED = {"memento-datetime": "Wed, 01 Jan 2020 00:00:00 GMT"}
CHALLENGE = (
    b"<!DOCTYPE html><html><head><title>Just a moment...</title></head>"
    b"<body><script src='/cdn-cgi/challenge-platform/h/b/orchestrate/jsch/v1'></script></body></html>"
)
GOOD_PAGE = b"<!DOCTYPE html><html><head><title>Home</title></head><body>Hello</body></html>"


def _cdx_rows(*timestamps):
    return _Response(200, json.dumps([["timestamp"]] + [[ts] for ts in timestamps]).encode())


class _BadCaptureWayback:
    """The capture at TS is bad; CDX answers with cdx(); any other timestamp is good."""

    def __init__(self, bad, cdx, good=GOOD_PAGE):
        self.bad = bad
        self.cdx = cdx
        self.good = good

    def __call__(self, url, kwargs):
        if url == CDX:
            return self.cdx(kwargs)
        if f"/{TS}" in url:
            return self.bad
        return _Response(200, self.good, url=url)


def _cdx_calls(dl):
    return [kwargs for url, kwargs in dl.session.get.calls if url == CDX]


class TestBadCapture:
    """Issue #48: an archived error or a Cloudflare challenge is replaced by
    the nearest capture with status 200, found with one CDX query."""

    def test_archived_403_falls_back_to_the_nearest_good_capture(self):
        dl = _make_downloader()
        dl.session.get = _Recorder(_BadCaptureWayback(
            _Response(403, CHALLENGE, headers=ARCHIVED),
            lambda kwargs: _cdx_rows("20191231230000"),
        ))
        assert dl.download_file("http://example.com/about") == GOOD_PAGE
        cdx = _cdx_calls(dl)
        assert len(cdx) == 1
        params = cdx[0]["params"]
        assert params["url"] == "http://example.com/about"
        assert params["filter"] == "statuscode:200"
        assert params["closest"] == TS
        assert dl.session.get.calls[-1][0] == (
            "https://web.archive.org/web/20191231230000if_/http://example.com/about"
        )

    def test_archived_500_asset_falls_back_too(self):
        dl = _make_downloader()
        dl.session.get = _Recorder(_BadCaptureWayback(
            _Response(500, b"oops", headers=ARCHIVED),
            lambda kwargs: _cdx_rows("20191231230000"),
            good=b"PNGDATA",
        ))
        assert dl.download_file("http://example.com/logo.png") == b"PNGDATA"
        assert dl.session.get.calls[-1][0] == (
            "https://web.archive.org/web/20191231230000im_/http://example.com/logo.png"
        )

    def test_start_url_adopts_the_timestamp_actually_used(self):
        dl = _make_downloader()
        dl.session.get = _Recorder(_BadCaptureWayback(
            _Response(503, CHALLENGE, headers=ARCHIVED),
            lambda kwargs: _cdx_rows("20191231230000"),
        ))
        assert dl.download_file(dl.config.base_url) == GOOD_PAGE
        assert dl.original_timestamp == "20191231230000"
        assert dl.original_datetime.strftime("%Y%m%d%H%M%S") == "20191231230000"

    def test_other_urls_keep_the_requested_timestamp(self):
        dl = _make_downloader()
        dl.session.get = _Recorder(_BadCaptureWayback(
            _Response(503, CHALLENGE, headers=ARCHIVED),
            lambda kwargs: _cdx_rows("20191231230000"),
        ))
        dl.download_file("http://example.com/about")
        assert dl.original_timestamp == TS

    def test_challenge_archived_as_200_falls_back(self):
        dl = _make_downloader()
        dl.session.get = _Recorder(_BadCaptureWayback(
            _Response(200, CHALLENGE),
            lambda kwargs: _cdx_rows("20191231230000"),
        ))
        assert dl.download_file("http://example.com/about") == GOOD_PAGE
        assert len(_cdx_calls(dl)) == 1

    def test_challenge_200_skips_the_bad_capture_cdx_returns_first(self):
        """A challenge archived with status 200 passes CDX's statuscode:200
        filter, so CDX's closest row is the challenge itself."""
        dl = _make_downloader()
        dl.session.get = _Recorder(_BadCaptureWayback(
            _Response(200, CHALLENGE),
            lambda kwargs: _cdx_rows(TS, "20191231230000"),
        ))
        assert dl.download_file("http://example.com/about") == GOOD_PAGE
        assert len(_cdx_calls(dl)) == 1
        assert dl.session.get.calls[-1][0] == (
            "https://web.archive.org/web/20191231230000if_/http://example.com/about"
        )

    def test_challenge_200_skips_the_capture_wayback_redirected_to(self):
        served = "20200101000512"

        def handler(url, kwargs):
            if url == CDX:
                return _cdx_rows(served, "20191231230000")
            if f"/{TS}" in url or f"/{served}" in url:
                return _Response(200, CHALLENGE, url=f"https://web.archive.org/web/{served}if_/http://example.com/about")
            return _Response(200, GOOD_PAGE, url=url)

        dl = _make_downloader()
        dl.session.get = _Recorder(handler)
        assert dl.download_file("http://example.com/about") == GOOD_PAGE
        assert "/20191231230000if_/" in dl.session.get.calls[-1][0]

    def test_archived_429_page_is_a_bad_capture_not_throttling(self):
        """Wayback's own 429 has no memento-datetime; an archived one is the
        site's answer, and a page is treated like an asset."""
        dl = _make_downloader()
        dl.session.get = _Recorder(_BadCaptureWayback(
            _Response(429, b"Too Many Requests", headers=ARCHIVED),
            lambda kwargs: _cdx_rows("20191231230000"),
        ))
        assert dl.download_file("http://example.com/about") == GOOD_PAGE
        assert len(_cdx_calls(dl)) == 1
        assert dl._last_failure is None

    def test_good_page_mentioning_challenge_platform_is_kept(self):
        """Negative control: Cloudflare injects challenge-platform into normal pages."""
        page = (
            b"<!DOCTYPE html><html><head><title>nowSecure</title></head><body>Hi"
            b"<script src='/cdn-cgi/challenge-platform/scripts/jsd/main.js'></script></body></html>"
        )
        dl = _make_downloader()
        dl.session.get = _Recorder(lambda url, kwargs: _Response(200, page))
        assert dl.download_file("http://example.com/about") == page
        assert _cdx_calls(dl) == []

    def test_wayback_own_503_is_not_a_bad_capture(self):
        """Without memento-datetime the error is Wayback's, and CDX cannot help."""
        dl = _make_downloader()
        dl.session.get = _Recorder(lambda url, kwargs: _Response(503, b"Temporarily Offline"))
        assert dl.download_file("http://example.com/about") is None
        assert _cdx_calls(dl) == []

    def test_no_good_capture_returns_none_after_one_lookup(self):
        for rows in (b"[]", b'[["timestamp"]]'):
            dl = _make_downloader()
            dl.session.get = _Recorder(_BadCaptureWayback(
                _Response(403, CHALLENGE, headers=ARCHIVED),
                lambda kwargs: _Response(200, rows),
            ))
            assert dl.download_file("http://example.com/about") is None
            assert len(_cdx_calls(dl)) == 1

    def test_fallback_capture_also_bad_returns_none_with_one_lookup(self):
        dl = _make_downloader()
        bad = _Response(403, CHALLENGE, headers=ARCHIVED)
        dl.session.get = _Recorder(lambda url, kwargs: _cdx_rows("20191231230000") if url == CDX else bad)
        assert dl.download_file("http://example.com/about") is None
        assert len(_cdx_calls(dl)) == 1
        assert dl.original_timestamp == TS

    def test_cdx_stops_after_three_consecutive_failures(self):
        dl = _make_downloader()
        dl.session.get = _Recorder(_BadCaptureWayback(
            _Response(403, CHALLENGE, headers=ARCHIVED),
            lambda kwargs: _Response(503, b"<html>Temporarily Offline</html>"),
        ))
        for n in range(5):
            assert dl.download_file(f"http://example.com/p{n}") is None
        assert len(_cdx_calls(dl)) == 3

    def test_cdx_success_resets_the_failure_count(self):
        answers = iter([_Response(503, b"x"), _Response(503, b"x"), _cdx_rows("20191231230000")] * 3)
        dl = _make_downloader()
        dl.session.get = _Recorder(_BadCaptureWayback(
            _Response(403, CHALLENGE, headers=ARCHIVED),
            lambda kwargs: next(answers),
        ))
        for n in range(9):
            dl.download_file(f"http://example.com/p{n}")
        assert len(_cdx_calls(dl)) == 9

    def test_cdx_lookups_are_capped_per_run(self):
        dl = _make_downloader()
        dl.session.get = _Recorder(_BadCaptureWayback(
            _Response(403, CHALLENGE, headers=ARCHIVED),
            lambda kwargs: _Response(200, b"[]"),
        ))
        for n in range(30):
            dl.download_file(f"http://example.com/p{n}")
        assert len(_cdx_calls(dl)) == 25


def _run_cli(monkeypatch, tmp_path, handler, wayback_url=None):
    """Run cli.main() against a fake Wayback; return (exit code, stdout, stderr lines)."""
    os.environ["WAYBACK_URL"] = wayback_url or f"https://web.archive.org/web/{TS}/http://example.com/"
    os.environ["OUTPUT_DIR"] = str(tmp_path / "out")
    recorder = _Recorder(handler)
    monkeypatch.setattr(requests.Session, "get", lambda self, url, **kwargs: recorder(url, **kwargs))
    code = 0
    try:
        cli.main()
    except SystemExit as e:
        code = e.code
    return code, recorder


class TestExitStatus:
    def test_nothing_saved_exits_1_with_one_line(self, monkeypatch, tmp_path, capsys):
        code, _ = _run_cli(monkeypatch, tmp_path, lambda url, kwargs: _Response(503, b"down"))
        err = capsys.readouterr().err
        assert code == 1
        assert err.startswith("Error: ") and err.count("\n") == 1
        assert "http://example.com/" in err
        assert "Traceback" not in err

    def test_a_saved_start_page_exits_0(self, monkeypatch, tmp_path, capsys):
        code, _ = _run_cli(monkeypatch, tmp_path, lambda url, kwargs: _Response(200, GOOD_PAGE))
        assert code == 0
        assert (tmp_path / "out" / "index.html").exists()

    @pytest.mark.parametrize("url", ["not-a-url", "https://example.com/"])
    def test_malformed_wayback_url_is_one_line_not_a_traceback(self, monkeypatch, tmp_path, capsys, url):
        code, recorder = _run_cli(monkeypatch, tmp_path, lambda u, kwargs: _Response(200, GOOD_PAGE), url)
        err = capsys.readouterr().err
        assert code == 1
        assert err.startswith("Error: WAYBACK_URL") and err.count("\n") == 1
        assert "https://web.archive.org/web/<timestamp>/<url>" in err
        assert recorder.calls == []


class _Sequence(http.server.BaseHTTPRequestHandler):
    """Answers each GET with the next (status, headers) from the server's list."""

    def do_GET(self):
        status, headers = self.server.answers.pop(0)
        self.server.hits += 1
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


@pytest.fixture
def local_server():
    """A server on 127.0.0.1 (no real network) driven by a list of answers."""
    server = http.server.HTTPServer(("127.0.0.1", 0), _Sequence)
    server.answers, server.hits = [], 0
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


class TestThrottling:
    def _session_on(self, server):
        """The downloader's session with its Wayback adapter pointed at server,
        without the backoff sleeps between retries."""
        dl = _make_downloader()
        base = f"http://127.0.0.1:{server.server_port}/"
        adapter = dl.session.get_adapter("https://web.archive.org/web/")
        adapter.max_retries = adapter.max_retries.new(backoff_factor=0)
        dl.session.mount(base, adapter)
        return dl.session, base

    def test_429_is_retried_after_retry_after(self, local_server):
        local_server.answers = [(429, {"Retry-After": "0"}), (429, {"Retry-After": "0"}), (200, {})]
        session, base = self._session_on(local_server)
        response = session.get(base + "x", timeout=5)
        assert response.status_code == 200
        assert local_server.hits == 3

    @pytest.mark.parametrize("status, headers", [
        (503, {}),
        (503, {"Retry-After": "0"}),
        (413, {"Retry-After": "0"}),
        (429, {"Retry-After": "0", **ARCHIVED}),
    ])
    def test_5xx_is_not_retried(self, local_server, status, headers):
        """Only Wayback's own 429 is retried: a 503 or 413 with Retry-After
        is not, and neither is an archived 429 (it has memento-datetime)."""
        local_server.answers = [(status, headers), (200, {})]
        session, base = self._session_on(local_server)
        assert session.get(base + "x", timeout=5).status_code == status
        assert local_server.hits == 1

    def test_retries_are_bounded(self, local_server):
        local_server.answers = [(429, {"Retry-After": "0"})] * 10
        session, base = self._session_on(local_server)
        assert session.get(base + "x", timeout=5).status_code == 429
        assert local_server.hits <= 4

    def test_a_long_retry_after_is_capped(self):
        dl = _make_downloader()
        retry = dl.session.get_adapter("https://web.archive.org/web/").max_retries
        assert 0 < retry.get_retry_after(_Response(429, headers={"Retry-After": "3600"})) <= 60

    def test_only_wayback_gets_the_retrying_adapter(self):
        dl = _make_downloader()
        assert dl.session.get_adapter("https://code.jquery.com/x").max_retries.total == 0

    @pytest.mark.parametrize("refusal", ["429", "connection"])
    def test_five_refusals_in_a_row_stop_the_run(self, tmp_path, refusal):
        links = "".join(f'<a href="/p{n}.html">p{n}</a>' for n in range(10))
        start = f"<!DOCTYPE html><html><body>{links}</body></html>".encode()
        dl = _make_downloader(output_dir=tmp_path / "out")

        def handler(url, kwargs):
            if url.endswith("/http://example.com/"):
                return _Response(200, start)
            if refusal == "429":
                return _Response(429, b"slow down")
            raise requests.exceptions.ConnectionError("reset")

        dl.session.get = _Recorder(handler)
        with pytest.raises(RuntimeError, match="refused 5 requests in a row"):
            dl.download()
        pages = {url.rsplit("/", 1)[-1] for url, _ in dl.session.get.calls if "/p" in url}
        assert len(pages) == 5
        # One request per refused page: the plain URL would be refused too.
        assert len(dl.session.get.calls) == 1 + 5
        assert (tmp_path / "out" / "index.html").exists()

    def test_files_saved_from_the_cdn_are_not_refusals(self, tmp_path):
        """Wayback does not answer, but every file comes from its CDN."""
        links = "".join(
            f'<link rel="stylesheet" href="https://fonts.googleapis.com/css?family=F{n}">' for n in range(8)
        )
        start = f"<!DOCTYPE html><html><head>{links}</head><body></body></html>".encode()
        dl = _make_downloader(output_dir=tmp_path / "out")

        def handler(url, kwargs):
            if url.endswith("/http://example.com/"):
                return _Response(200, start)
            if url.startswith("https://fonts.googleapis.com/"):
                return _Response(200, b"body{color:red}", url=url)
            raise requests.exceptions.ConnectTimeout("no answer")

        dl.session.get = _Recorder(handler)
        dl.download()
        live = [url for url, _ in dl.session.get.calls if url.startswith("https://fonts.googleapis.com/")]
        assert len(live) == 8
        saved = [p for p in (tmp_path / "out").rglob("*") if p.is_file() and p.name != "index.html"]
        assert len(saved) == 8

    def test_a_success_resets_the_count(self, tmp_path):
        """Four refusals, a success, four more: the run goes on to the end."""
        links = "".join(f'<a href="/p{n}.html">p{n}</a>' for n in range(9))
        start = f"<!DOCTYPE html><html><body>{links}</body></html>".encode()
        dl = _make_downloader(output_dir=tmp_path / "out")

        def handler(url, kwargs):
            if url.endswith("/http://example.com/") or "/p4.html" in url:
                return _Response(200, start)
            return _Response(429, b"slow down")

        dl.session.get = _Recorder(handler)
        dl.download()
        pages = {url.rsplit("/", 1)[-1] for url, _ in dl.session.get.calls if "/p" in url}
        assert len(pages) == 9


class TestConfigValidation:
    @pytest.mark.parametrize("value", ["0", "-1", "5 files", "1e2", "abc"])
    def test_max_files_that_is_not_a_positive_integer_is_an_error(self, value):
        os.environ["WAYBACK_URL"] = f"https://web.archive.org/web/{TS}/http://example.com/"
        os.environ["MAX_FILES"] = value
        ok, error = Config().validate()
        assert not ok
        assert "MAX_FILES" in error and value in error

    @pytest.mark.parametrize("value, expected", [("3", 3), (" 7 ", 7), ("", None)])
    def test_valid_max_files(self, value, expected):
        os.environ["WAYBACK_URL"] = f"https://web.archive.org/web/{TS}/http://example.com/"
        os.environ["MAX_FILES"] = value
        config = Config()
        assert config.validate() == (True, None)
        assert config.max_files == expected

    def test_make_www_alone_adds_www_and_never_strips_it(self):
        os.environ["MAKE_WWW"] = "true"
        dl = _make_downloader()
        base = "http://example.com/"
        assert dl._normalize_url("http://www.example.com/a", base) == "http://www.example.com/a"
        assert dl._normalize_url("http://example.com/b", base) == "http://www.example.com/b"


class TestMaxFilesBoundsRequests:
    def test_failed_attempts_count_toward_max_files(self, tmp_path):
        images = "".join(f'<img src="/i{n}.png">' for n in range(10))
        start = f"<!DOCTYPE html><html><body>{images}</body></html>".encode()
        os.environ["MAX_FILES"] = "2"
        dl = _make_downloader(output_dir=tmp_path / "out")
        dl.session.get = _Recorder(
            lambda url, kwargs: _Response(200, start) if url.endswith("/http://example.com/") else _Response(404)
        )
        dl.download()
        images_tried = {url.rsplit("/", 1)[-1] for url, _ in dl.session.get.calls if ".png" in url}
        assert len(images_tried) == 1
        assert len(dl.session.get.calls) <= 1 + 4


class TestDotenv:
    def test_cli_reads_dotenv_from_the_working_directory(self, monkeypatch, tmp_path):
        """The package lives outside tmp_path, so only a cwd search finds this file."""
        (tmp_path / ".env").write_text(
            f"WAYBACK_URL=https://web.archive.org/web/{TS}/http://from-dotenv.example/\n"
            f"OUTPUT_DIR={tmp_path / 'out'}\n"
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("WAYBACK_URL", raising=False)
        monkeypatch.delenv("OUTPUT_DIR", raising=False)
        seen = {}

        class FakeDownloader:
            def __init__(self, config):
                seen["config"] = config

            def download(self):
                pass

        monkeypatch.setattr(cli, "WaybackDownloader", FakeDownloader)
        cli.main()
        assert seen["config"].wayback_url.endswith("/http://from-dotenv.example/")
        assert seen["config"].output_dir == str(tmp_path / "out")


class TestStartRedirect:
    def _site(self, final_original):
        final = f"https://web.archive.org/web/20200102000000if_/{final_original}"
        start = (
            b"<!DOCTYPE html><html><body>"
            b'<a href="/web/20200102000000/https://example-new.com/about">About</a>'
            b'<a href="contact.html">Contact</a>'
            b"</body></html>"
        )

        def handler(url, kwargs):
            if url.endswith("/http://example.com/"):
                return _Response(200, start, url=final)
            if "example-new.com/about" in url or "example-new.com/contact.html" in url \
                    or "www.example.com/about" in url or "www.example.com/contact.html" in url:
                return _Response(200, GOOD_PAGE, url=url)
            return _Response(404)

        return handler

    def test_a_start_capture_on_another_host_moves_the_crawl_there(self, tmp_path, capsys):
        dl = _make_downloader(output_dir=tmp_path / "out")
        dl.session.get = _Recorder(self._site("https://example-new.com/"))
        dl.download()
        requested = [url for url, _ in dl.session.get.calls]
        assert any(u.endswith("/https://example-new.com/about") for u in requested)
        assert any(u.endswith("/https://example-new.com/contact.html") for u in requested)
        assert (tmp_path / "out" / "about.html").exists()
        assert (tmp_path / "out" / "contact.html").exists()
        assert "redirects to https://example-new.com/" in capsys.readouterr().out

    def test_a_www_redirect_is_not_a_host_change(self, tmp_path, capsys):
        dl = _make_downloader(output_dir=tmp_path / "out")
        dl.session.get = _Recorder(self._site("http://www.example.com/"))
        dl.download()
        assert dl.config.domain == "example.com"
        assert "redirects to" not in capsys.readouterr().out


class TestJqueryReplacement:
    @pytest.mark.parametrize("src, version", [
        ("/js/jquery-1.7.2/jquery.min.js", "1.7.2"),
        ("/wp-includes/js/jquery/jquery.min.js?ver=3.6.0", "3.6.0"),
        ("/js/jquery.min.js", "3.7.1"),
    ])
    def test_the_version_named_in_the_url_is_fetched(self, tmp_path, src, version):
        start = f'<!DOCTYPE html><html><head><script src="{src}"></script></head><body></body></html>'.encode()
        dl = _make_downloader(output_dir=tmp_path / "out")

        def handler(url, kwargs):
            if url.endswith("/http://example.com/"):
                return _Response(200, start)
            if url.startswith("https://code.jquery.com/"):
                return _Response(200, b"/*! jQuery */", url=url)
            return _Response(404)

        dl.session.get = _Recorder(handler)
        dl.download()
        live = [url for url, _ in dl.session.get.calls if "code.jquery.com" in url]
        assert live == [f"https://code.jquery.com/jquery-{version}.min.js"]

    @pytest.mark.parametrize("src, tried", [
        ("/js/jquery.min.js?ver=5.8.1", ["5.8.1", "3.7.1"]),
        ("/js/jquery-1.9/jquery.min.js", ["1.9", "1.9.0"]),
        ("/wp-includes/js/jquery/jquery.min.js?ver=1.0", ["1.0", "1.0.0", "3.7.1"]),
    ])
    def test_a_version_the_cdn_lacks_falls_back(self, tmp_path, src, tried):
        """?ver= is often the WordPress version, and a two-part version has no
        file on code.jquery.com: try x.y.0, then 3.7.1."""
        start = f'<!DOCTYPE html><html><head><script src="{src}"></script></head><body></body></html>'.encode()
        dl = _make_downloader(output_dir=tmp_path / "out")
        on_cdn = ("https://code.jquery.com/jquery-1.9.0.min.js", "https://code.jquery.com/jquery-3.7.1.min.js")

        def handler(url, kwargs):
            if url.endswith("/http://example.com/"):
                return _Response(200, start)
            if url in on_cdn:
                return _Response(200, b"/*! jQuery */", url=url)
            return _Response(404)

        dl.session.get = _Recorder(handler)
        dl.download()
        live = [url for url, _ in dl.session.get.calls if "code.jquery.com" in url]
        assert live == [f"https://code.jquery.com/jquery-{v}.min.js" for v in tried]
        saved = [p for p in (tmp_path / "out").rglob("jquery.min.js")]
        assert len(saved) == 1 and saved[0].read_bytes().startswith(b"/*! jQuery */")
