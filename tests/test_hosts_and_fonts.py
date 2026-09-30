"""The tool only talks to hosts it means to, and font clean-up keeps the CSS.

Host checks used to be substring or ``lstrip("www.")`` comparisons, so a URL
that merely *contained* a trusted name (``web.archive.org@10.0.0.1``,
``sqspcdn.com.evil.test``, ``wexample.com``) was treated as trusted and fetched
directly. The font clean-up regexes matched ``url(`` up to the next quote, so a
single match could swallow neighbouring rules.
"""

import contextlib
import io
import os
from urllib.parse import urlparse

import pytest
from wayback_archive.config import Config
from wayback_archive.downloader import WaybackDownloader


def _make_downloader(wayback_url=None, output_dir=None):
    """Create a downloader with a clean environment."""
    os.environ["WAYBACK_URL"] = (
        wayback_url or "https://web.archive.org/web/20200101000000/http://example.com/"
    )
    config = Config()
    if output_dir is not None:
        config.output_dir = str(output_dir)
    return WaybackDownloader(config)


def _archive(downloader, pages):
    """Run download() with download_file served from a dict; return the calls."""
    calls = []

    def fake_download_file(url):
        calls.append(url)
        return pages.get(url)

    downloader.download_file = fake_download_file
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        downloader.download()
    return calls, out.getvalue()


@pytest.fixture(autouse=True)
def _clean_env():
    yield
    os.environ.pop("WAYBACK_URL", None)


class TestWaybackUrlIsParsedNotPrefixMatched:
    """Only a real web.archive.org URL may skip the Wayback rewrite."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://web.archive.org@10.0.0.1/x.woff",
            "http://web.archive.org:sqspcdn.com@169.254.169.254/a",
            "http://web.archive.org.evil.test/a.png",
            "https://web.archive.org.evil.test/web/2020/http://example.com/",
        ],
    )
    def test_lookalike_is_wrapped(self, url):
        dl = _make_downloader()
        converted = dl._convert_to_wayback_url_with_timestamp(url)
        assert converted.startswith("https://web.archive.org/web/20200101000000")
        assert converted.endswith(url)

    def test_real_wayback_url_is_returned_unchanged(self):
        dl = _make_downloader()
        url = "https://web.archive.org/web/2020/http://example.com/"
        assert dl._convert_to_wayback_url_with_timestamp(url) == url


class TestSquarespaceCdnIsAHostMatch:
    @pytest.mark.parametrize(
        "url",
        [
            "http://sqspcdn.com@10.0.0.1/x",
            "http://sqspcdn.com.evil.test/x",
            "http://evilsqspcdn.com/x",
            "http://static1.squarespace.com@192.168.1.1/x",
        ],
    )
    def test_foreign_host_is_not_the_cdn(self, url):
        assert _make_downloader()._is_squarespace_cdn(url) is False

    @pytest.mark.parametrize(
        "url",
        [
            "https://static1.squarespace.com/a.js",
            "https://images.squarespace-cdn.com/b.jpg",
            "https://assets.sqspcdn.com/c.css",
            "//static1.squarespace.com/d.css",
        ],
    )
    def test_real_cdn_host_matches(self, url):
        assert _make_downloader()._is_squarespace_cdn(url) is True


class TestWwwIsAPrefixNotACharacterSet:
    """lstrip("www.") stripped any leading w and dot, not the www. prefix."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://wexample.com/a.png",
            "http://w.example.com/",
            "http://ww.example.com/",
            "http://example.com@evil.test/",
            "http://user@example.com/",
        ],
    )
    def test_lookalike_is_not_internal(self, url):
        assert _make_downloader()._is_internal_url(url) is False

    def test_www_variant_is_still_internal(self):
        assert _make_downloader()._is_internal_url("http://www.example.com/a.png") is True

    def test_base_domain_starting_with_w(self):
        dl = _make_downloader(
            "https://web.archive.org/web/20200101000000/http://wiki.example.com/"
        )
        assert dl._is_internal_url("http://wiki.example.com/x") is True
        assert dl._is_internal_url("http://www.wiki.example.com/x") is True
        assert dl._is_internal_url("http://iki.example.com/x") is False

    def test_normalize_keeps_the_scheme_of_a_foreign_host(self):
        """Only an internal URL takes the base URL's scheme."""
        dl = _make_downloader()
        assert (
            dl._normalize_url("https://wexample.com/a", "http://example.com/")
            == "https://wexample.com/a"
        )
        assert (
            dl._normalize_url("https://example.com/a", "http://example.com/")
            == "http://example.com/a"
        )

    def test_lookalike_link_is_not_rewritten_to_the_home_page(self):
        dl = _make_downloader()
        html, links = dl._process_html(
            '<a href="https://wexample.com/">other site</a>', "http://example.com/"
        )
        assert "index.html" not in html
        assert links == []

    def test_site_on_a_w_host_visits_each_page_once(self, tmp_path):
        """The visited key used to be 'iki.example.com', so no check ever hit."""
        dl = _make_downloader(
            "https://web.archive.org/web/20200101000000/http://wiki.example.com/",
            tmp_path / "out",
        )
        links = (
            b'<a href="http://wiki.example.com/">h</a>'
            b'<a href="http://wiki.example.com/a.html">a</a>'
            b'<a href="http://wiki.example.com/b.html">b</a>'
        )
        page = b"<html><body>" + links + b"</body></html>"
        pages = {
            "http://wiki.example.com/": page,
            "http://wiki.example.com/a.html": page,
            "http://wiki.example.com/b.html": page,
        }
        calls, out = _archive(dl, pages)
        assert sorted(calls) == sorted(pages)
        assert "Files skipped (duplicates): 0" in out


class TestCssOnlyQueuesRealGoogleFonts:
    def test_url_that_mentions_gstatic_is_not_a_google_font(self, tmp_path):
        dl = _make_downloader(output_dir=tmp_path / "out")
        pages = {
            "http://example.com/": b'<html><head><link rel="stylesheet" '
            b'href="http://example.com/s.css"></head><body></body></html>',
            "http://example.com/s.css": b"a{background:url(http://192.168.1.1/cgi-bin/"
            b"export.cgi?fonts.gstatic.com)}"
            b"b{background:url(https://fonts.gstatic.com/s/r/v1/x.woff2)}",
        }
        calls, _ = _archive(dl, pages)
        assert not any("192.168.1.1" in c for c in calls)
        assert "https://fonts.gstatic.com/s/r/v1/x.woff2" in calls
