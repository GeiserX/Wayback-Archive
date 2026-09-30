"""Behaving well when the Wayback Machine says no.

A capture can be an archived error or a Cloudflare challenge (issue #48), a
URL can be missing, Wayback can throttle, and the user can press Ctrl-C.
Each used to cost a pile of blind requests, a silently empty archive with
exit code 0, or an interrupt that was swallowed.
"""

import os

import pytest
import requests

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
    for key in ("WAYBACK_URL", "MAX_FILES", "MAKE_WWW", "MAKE_NON_WWW"):
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
