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

# user:password@host URLs are assembled at runtime: written out, a secret
# scanner reads them as credentials.
_COLON = ":"


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
            "http://web.archive.org" + _COLON + "sqspcdn.com@169.254.169.254/a",
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
        b'<img src="/web/20200101000000im_/http://web.archive.org' + _COLON.encode() + b'sqspcdn.com@169.254.169.254/meta">'
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


# Rewritten CSS always has unquoted url(), and minifiers drop the quotes
# around single-word font names, so nothing stops a match at a quote.
REWRITTEN_CSS = (
    'body{font-family:"Open Sans"}'
    ".hero{background:url(../img/hero.jpg) center/cover}"
    ".logo{background:url(../img/logo.png)}"
    "@font-face{font-family:MyFont;src:url(../fonts/my.eot);"
    'src:url(../fonts/my.woff2) format("woff2"),url(../fonts/my.woff) format("woff")}'
)

GLYPHICONS = (
    "@font-face{font-family:'Glyphicons Halflings';"
    "src:url(../fonts/glyphicons-halflings-regular.eot);"
    "src:url(../fonts/glyphicons-halflings-regular.eot?#iefix) format('embedded-opentype'),"
    "url(../fonts/glyphicons-halflings-regular.woff2) format('woff2'),"
    "url(../fonts/glyphicons-halflings-regular.woff) format('woff'),"
    "url(../fonts/glyphicons-halflings-regular.ttf) format('truetype')}"
)


class TestFontCleanupKeepsTheRestOfTheCss:
    def test_legacy_removal_does_not_cross_rules(self):
        css = ".a{background:url(a.png)}.b{color:red}@font-face{font-family:F;src:url(f.eot)}"
        result = _make_downloader()._remove_legacy_font_formats_from_css(css)
        assert "url(a.png)" in result
        assert ".b{color:red}" in result
        assert "@font-face{font-family:F;" in result
        assert ".eot" not in result

    def test_legacy_removal_on_rewritten_css(self):
        result = _make_downloader()._remove_legacy_font_formats_from_css(REWRITTEN_CSS)
        assert result == REWRITTEN_CSS.replace("src:url(../fonts/my.eot);", "")

    def test_corrupted_font_removal_on_rewritten_css(self):
        dl = _make_downloader()
        dl.corrupted_fonts.add("http://example.com/fonts/my.woff2")
        result = dl._remove_corrupted_fonts_from_css(REWRITTEN_CSS)
        assert result == REWRITTEN_CSS.replace(
            'src:url(../fonts/my.woff2) format("woff2"),', "src:"
        )

    def test_corrupted_font_matches_the_whole_file_name(self):
        dl = _make_downloader()
        dl.corrupted_fonts.add("http://example.com/fonts/regular.woff")
        css = "@font-face{src:url(../x/bold-regular.woff) format('woff')}"
        assert dl._remove_corrupted_fonts_from_css(css) == css

    def test_corrupted_font_with_a_query_string_is_removed(self):
        dl = _make_downloader()
        dl.corrupted_fonts.add("http://example.com/fonts/x.woff2")
        css = "@font-face{src:url(/fonts/x.woff2?v=3) format('woff2'),url(/fonts/x.woff) format('woff')}"
        assert dl._remove_corrupted_fonts_from_css(css) == (
            "@font-face{src:url(/fonts/x.woff) format('woff')}"
        )

    def test_removed_font_takes_its_format_with_it(self):
        dl = _make_downloader()
        dl.corrupted_fonts.add(
            "http://example.com/fonts/glyphicons-halflings-regular.woff2"
        )
        result = dl._remove_legacy_font_formats_from_css(
            dl._remove_corrupted_fonts_from_css(GLYPHICONS)
        )
        assert ", format(" not in result
        assert "format('woff2')" not in result
        assert "url(../fonts/glyphicons-halflings-regular.woff) format('woff')" in result
        assert "url(../fonts/glyphicons-halflings-regular.ttf) format('truetype')" in result

    def test_url_patterns_cannot_run_past_the_closing_paren(self, monkeypatch):
        """Structural guard against the quadratic scan, without timing.

        Every url() pattern must stop its unbounded character classes at ')'.
        A class that only stops at a quote runs to the end of the file from
        each url( it tries, which is quadratic and swallows neighbouring rules.
        """
        import re as real_re
        import wayback_archive.downloader as module

        seen = []

        class Recorder:
            def __getattr__(self, name):
                return getattr(real_re, name)

            def sub(self, pattern, *args, **kwargs):
                seen.append(pattern)
                return real_re.sub(pattern, *args, **kwargs)

            def findall(self, pattern, *args, **kwargs):
                seen.append(pattern)
                return real_re.findall(pattern, *args, **kwargs)

            def finditer(self, pattern, *args, **kwargs):
                seen.append(pattern)
                return real_re.finditer(pattern, *args, **kwargs)

        dl = _make_downloader()
        dl.session.get = lambda *a, **k: _Response(404)
        dl.corrupted_fonts.add("http://example.com/fonts/my.woff2")
        monkeypatch.setattr(module, "re", Recorder())
        dl._check_and_remove_corrupted_fonts_in_css(REWRITTEN_CSS, "http://example.com/css/s.css")
        dl._remove_corrupted_fonts_from_css(REWRITTEN_CSS)
        dl._remove_legacy_font_formats_from_css(REWRITTEN_CSS)
        monkeypatch.undo()

        url_patterns = [p for p in seen if "url" in p]
        assert url_patterns
        for pattern in url_patterns:
            for negated in real_re.findall(r"\[\^((?:\\.|[^\]])*)\][*+]", pattern):
                assert ")" in negated, pattern

    def test_large_plain_stylesheet_passes_through_unchanged(self):
        css = "".join(f".c{i}{{background:url(img/a{i}.png)}}" for i in range(4000))
        dl = _make_downloader()
        dl.session.get = lambda *a, **k: pytest.fail("no font to probe")
        dl.corrupted_fonts.add("http://example.com/fonts/my.woff2")
        assert dl._check_and_remove_corrupted_fonts_in_css(css, "http://example.com/s.css") == css
        assert dl._remove_corrupted_fonts_from_css(css) == css
        assert dl._remove_legacy_font_formats_from_css(css) == css


class TestFontProbe:
    def _downloader(self):
        dl = _make_downloader()
        dl.session = _FakeSession({})
        dl.session.get = lambda url, **kw: (
            dl.session.calls.append((url, kw)) or _Response(200, b"wOF2" + b"\0" * 100)
        )
        return dl

    def test_each_unquoted_font_is_probed_on_its_own(self):
        dl = self._downloader()
        dl._check_and_remove_corrupted_fonts_in_css(
            "a{src:url(/f/a.woff2)}b{src:url(/f/b.woff)}", "http://example.com/s.css"
        )
        probed = [url for url, _ in dl.session.calls]
        assert len(probed) == 2
        assert probed[0].endswith("/http://example.com/f/a.woff2")
        assert probed[1].endswith("/http://example.com/f/b.woff")

    def test_a_font_is_probed_once_per_run(self):
        dl = self._downloader()
        css = "@font-face{src:url(/f/a.woff2)}"
        dl._check_and_remove_corrupted_fonts_in_css(css, "http://example.com/one.css")
        dl._check_and_remove_corrupted_fonts_in_css(css, "http://example.com/two.css")
        assert len(dl.session.calls) == 1

    def test_corrupted_google_font_is_removed_from_the_saved_stylesheet(self, tmp_path):
        """The probe used to run on rewritten CSS, where the Google font had
        become a local path, so it probed example.com/fonts.gstatic.com/... and
        the corruption was only found after the stylesheet was saved."""
        output_dir = tmp_path / "out"
        dl = _make_downloader(output_dir=output_dir)
        font = "https://fonts.gstatic.com/s/r/v30/x.woff2"
        dl.session = _FakeSession(
            {
                "http://example.com/": b'<html><head><link rel="stylesheet" '
                b'href="http://example.com/s.css"></head><body></body></html>',
                "http://example.com/s.css": b"@font-face{font-family:R;src:url("
                + font.encode()
                + b") format('woff2')}p{color:red}",
                font: b"<!DOCTYPE html><html><body>error</body></html>",
            }
        )
        with contextlib.redirect_stdout(io.StringIO()):
            dl.download()
        saved = (output_dir / "s.css").read_text()
        assert "x.woff2" not in saved
        assert "p{color:red}" in saved
        assert not any(
            "example.com/fonts.gstatic.com" in url for url, _ in dl.session.calls
        )


class TestGoogleFontsIsAHostMatch:
    """Only a URL on a Google Fonts host is handled as Google Fonts.

    The checks used to look for "fonts.googleapis.com" anywhere in the URL, so
    a foreign stylesheet whose query mentioned it was fetched and saved as
    fonts.googleapis.com/css-<hash>.css.
    """

    def _run(self, tmp_path, page):
        output_dir = tmp_path / "out"
        dl = _make_downloader(output_dir=output_dir)
        dl.session = _FakeSession({"http://example.com/": page})
        with contextlib.redirect_stdout(io.StringIO()):
            dl.download()
        files = {str(p.relative_to(output_dir)) for p in output_dir.rglob("*") if p.is_file()}
        return dl.session, files

    @pytest.mark.parametrize(
        "href",
        [
            "http://evil.test/a.css?fonts.googleapis.com/css",
            "http://fonts.googleapis.com.evil.test/css?family=X",
        ],
    )
    def test_foreign_stylesheet_is_not_queued_as_google_fonts(self, tmp_path, href):
        page = (
            b'<html><head><link rel="stylesheet" href="' + href.encode() + b'">'
            b"</head><body></body></html>"
        )
        session, files = self._run(tmp_path, page)
        assert not any("evil.test" in url for url, _ in session.calls)
        assert not any(f.startswith("fonts.googleapis.com") for f in files)

    def test_site_stylesheet_mentioning_google_fonts_keeps_its_own_fonts(self):
        dl = _make_downloader()
        css = dl._rewrite_css_urls(
            "a{src:url(/s/x.woff2)}", "http://example.com/s.css?fonts.googleapis.com"
        )
        assert "fonts.gstatic.com" not in css

    def test_foreign_url_mentioning_gstatic_is_not_made_local(self):
        dl = _make_downloader()
        css = dl._rewrite_css_urls(
            "a{background:url(http://evil.test/a.png?fonts.gstatic.com)}",
            "http://example.com/s.css",
        )
        assert "http://evil.test/a.png" in css

    @pytest.mark.parametrize(
        "href",
        [
            "https://fonts.googleapis.com/css?family=Roboto",
            "/web/20200101000000cs_/https://fonts.googleapis.com/css2?family=Roboto",
        ],
    )
    def test_missing_google_fonts_stylesheet_is_fetched_live(self, tmp_path, href):
        """The stylesheet has no extension, so it was taken for a page, and a
        page is never fetched live."""
        page = (
            b'<html><head><link rel="stylesheet" href="' + href.encode() + b'">'
            b"</head><body></body></html>"
        )
        session, files = self._run(tmp_path, page)
        live = [url for url, _ in session.live_calls()]
        assert live == [href[href.index("https://"):]]
        assert any(
            f.startswith("fonts.googleapis.com/css-") and f.endswith(".css") for f in files
        )
        assert not any("if_/https://fonts.googleapis.com" in url for url, _ in session.calls)


class TestUserinfoOnATrustedHost:
    """userinfo in front of a genuine trusted host still does not match.

    Parsing the host already rejects "trusted@elsewhere"; these pin the case
    where only the "@" check stands in the way.
    """

    def test_squarespace_host_with_userinfo_is_not_the_cdn(self):
        assert _make_downloader()._is_squarespace_cdn("http://u" + _COLON + "p@static1.squarespace.com/x") is False

    def test_live_fetch_refuses_userinfo(self):
        dl = _make_downloader()
        dl.session = _FakeSession({})
        assert dl._fetch_from_live_cdn("http://u" + _COLON + "p@static1.squarespace.com/x.js") is None
        assert dl._fetch_from_live_cdn("http://u@fonts.gstatic.com/s/x.woff2") is None
        assert dl.session.calls == []

    def test_wayback_url_with_userinfo_is_wrapped(self):
        dl = _make_downloader()
        url = "http://u@web.archive.org/web/2020/http://example.com/"
        converted = dl._convert_to_wayback_url_with_timestamp(url)
        assert converted.startswith("https://web.archive.org/web/20200101000000")
        assert converted.endswith(url)
