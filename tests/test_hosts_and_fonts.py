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


class _Response:
    """A minimal requests.Response stand-in."""

    def __init__(self, status_code, content=b""):
        self.status_code = status_code
        self.content = content
        self.headers = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.exceptions.HTTPError(response=self)


class _FakeSession:
    """Wayback has only the pages given; every other host answers 200 LIVE."""

    def __init__(self, wayback_pages, live_status=200):
        self.wayback_pages = wayback_pages
        self.live_status = live_status
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if urlparse(url).hostname == "web.archive.org":
            for original, body in self.wayback_pages.items():
                if url.endswith("/" + original):
                    return _Response(200, body)
            return _Response(404)
        return _Response(self.live_status, b"LIVE:" + url.encode())

    def live_calls(self):
        return [
            (url, kwargs)
            for url, kwargs in self.calls
            if urlparse(url).hostname != "web.archive.org"
        ]


class TestLiveFallbackIsCdnOnly:
    """What Wayback does not have is reported as failed, not fetched live.

    The archived site's domain may belong to someone else today, and what it
    serves now is not the archive. Only a short list of well-known CDN hosts
    may be fetched live when Wayback misses, and never through a redirect.
    """

    PAGE = (
        b"<html><head>"
        b'<script src="http://example.com/app.js"></script>'
        b'<link rel="stylesheet" href="http://example.com/s.css">'
        b"</head><body>"
        b'<a href="http://example.com/contact.php">c</a>'
        b'<img src="http://web.archive.org@10.0.0.1/x.png">'
        b'<img src="/web/20200101000000im_/http://web.archive.org:sqspcdn.com@169.254.169.254/meta">'
        b'<script src="http://sqspcdn.com@169.254.169.254/latest/user-data"></script>'
        b'<img src="http://wexample.com/a.png">'
        b'<img src="https://static1.squarespace.com/static/logo.png">'
        b"</body></html>"
    )
    CSS = (
        b"@font-face{font-family:R;src:url(https://fonts.gstatic.com/s/r/v1/x.woff2)}"
        b"a{background:url(http://192.168.1.1/cgi-bin/export.cgi?fonts.gstatic.com)}"
        b"b{src:url(http://web.archive.org@192.168.1.1/api/reboot?x.woff)}"
    )

    def _run(self, tmp_path, live_status=200):
        output_dir = tmp_path / "out"
        dl = _make_downloader(output_dir=output_dir)
        dl.session = _FakeSession(
            {"http://example.com/": self.PAGE, "http://example.com/s.css": self.CSS},
            live_status,
        )
        with contextlib.redirect_stdout(io.StringIO()):
            dl.download()
        files = {str(p.relative_to(output_dir)) for p in output_dir.rglob("*") if p.is_file()}
        return dl.session, files

    def test_only_allowlisted_cdn_hosts_are_fetched_live(self, tmp_path):
        session, files = self._run(tmp_path)
        live_hosts = {urlparse(url).hostname for url, _ in session.live_calls()}
        assert live_hosts == {"fonts.gstatic.com", "static1.squarespace.com"}
        assert all(kw.get("allow_redirects") is False for _, kw in session.live_calls())
        assert "fonts.gstatic.com/s/r/v1/x.woff2" in files
        assert "app.js" not in files
        assert "contact.php" not in files
        assert "a.png" not in files

    def test_a_cdn_redirect_is_a_failure(self, tmp_path):
        session, files = self._run(tmp_path, live_status=302)
        assert session.live_calls()
        assert "fonts.gstatic.com/s/r/v1/x.woff2" not in files

    def test_site_asset_on_wayback_timeout_is_not_fetched_live(self):
        import requests

        dl = _make_downloader()
        calls = []

        def get(url, **kwargs):
            calls.append(url)
            raise requests.exceptions.Timeout()

        dl.session.get = get
        assert dl.download_file("http://example.com/image.jpg") is None
        assert all(urlparse(u).hostname == "web.archive.org" for u in calls)

    def test_jquery_replacement_comes_only_from_code_jquery_com(self, tmp_path):
        output_dir = tmp_path / "out"
        dl = _make_downloader(output_dir=output_dir)
        dl.session = _FakeSession(
            {
                "http://example.com/": b'<html><head><script src="http://example.com/'
                b'js/jquery.min.js"></script></head><body></body></html>'
            }
        )
        with contextlib.redirect_stdout(io.StringIO()):
            dl.download()
        live = [url for url, _ in dl.session.live_calls()]
        assert live == ["https://code.jquery.com/jquery-3.7.1.min.js"]
        assert all(kw.get("allow_redirects") is False for _, kw in dl.session.live_calls())
        assert (output_dir / "js/jquery.min.js").read_bytes().startswith(b"LIVE:https://code.jquery.com/")
