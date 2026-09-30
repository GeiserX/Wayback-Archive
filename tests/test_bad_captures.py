"""Behaving well when the Wayback Machine says no.

A capture can be an archived error or a Cloudflare challenge (issue #48), a
URL can be missing, Wayback can throttle, and the user can press Ctrl-C.
Each used to cost a pile of blind requests, a silently empty archive with
exit code 0, or an interrupt that was swallowed.
"""

import json
import os

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
