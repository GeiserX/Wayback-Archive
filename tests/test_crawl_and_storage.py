"""The crawler queues the right URLs, stores each once under a usable name,
and keeps the text.

Relative links used to be queued exactly as written, so ``href="foo/"`` was
requested from Wayback as the host ``foo``. Visited checks stripped the query
but kept the scheme, so http/https twins were fetched twice while a second
Google Fonts family was never fetched. ``.php`` pages were stored as
downloads, ``/index.php`` next to ``/index.php/about`` crashed the run, and
non-UTF-8 pages silently lost every accented character.
"""

import contextlib
import io
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest
import requests

from wayback_archive.config import Config
from wayback_archive.downloader import WaybackDownloader

TS = "20200101000000"


def _make_downloader(wayback_url=None, output_dir=None):
    os.environ["WAYBACK_URL"] = wayback_url or f"https://web.archive.org/web/{TS}/https://example.com/"
    config = Config()
    if output_dir is not None:
        config.output_dir = str(output_dir)
    return WaybackDownloader(config)


@pytest.fixture(autouse=True)
def _clean_env():
    yield
    os.environ.pop("WAYBACK_URL", None)


class _Response:
    def __init__(self, status, body=b"", content_type=None):
        self.status_code = status
        self.content = body
        self.headers = {"Content-Type": content_type} if content_type else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(response=self)


class _Wayback:
    """Serves the given originals from web.archive.org; everything else 404s.

    Values are bytes, or (bytes, content_type).
    """

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if urlparse(url).hostname == "web.archive.org":
            for original, value in self.pages.items():
                if url.endswith("/" + original):
                    body, content_type = value if isinstance(value, tuple) else (value, None)
                    return _Response(200, body, content_type)
        return _Response(404)


def _run(tmp_path, pages, wayback_url=None):
    output_dir = tmp_path / "out"
    dl = _make_downloader(wayback_url=wayback_url, output_dir=output_dir)
    dl.session = _Wayback(pages)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        dl.download()
    files = {
        p.relative_to(output_dir).as_posix() for p in output_dir.rglob("*") if p.is_file()
    }
    return dl, files, out.getvalue(), output_dir


def _hrefs(html):
    return re.findall(r'(?:href|src)="?([^"\s>]+)', html)


class TestRelativeLinksAreQueuedAbsolute:
    """E2E-1: a relative reference is resolved against the page, not sent raw."""

    PAGE = (
        '<html><head><link rel="stylesheet" href="s.css">'
        '<script src="../app.js"></script></head><body>'
        '<a href="foo/">f</a><a href="foo/#sec">f2</a>'
        '<a href="/bar.html">b</a><a href="../up.html">u</a>'
        '<a href="/web/20200101000000/https://example.com/docs/wb.html">w</a>'
        '<img src="img/a.png"></body></html>'
    )

    def test_process_html_returns_absolute_urls_on_the_site(self):
        dl = _make_downloader()
        _, links = dl._process_html(self.PAGE, "https://example.com/docs/")
        assert set(links) == {
            "https://example.com/docs/s.css",
            "https://example.com/app.js",
            "https://example.com/docs/foo/",
            "https://example.com/bar.html",
            "https://example.com/up.html",
            "https://example.com/docs/wb.html",
            "https://example.com/docs/img/a.png",
        }
        assert len(links) == len(set(links))

    def test_non_fetchable_references_are_never_queued(self):
        dl = _make_downloader()
        html = (
            '<html><head><link rel="icon" href="data:image/png;base64,iVBOR"></head><body>'
            '<a href="javascript:void(0)">j</a><a href="#top">t</a>'
            '<a href="mailto:a@example.com">m</a><a href="tel:123">p</a>'
            '<iframe src="about:blank"></iframe>'
            '<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">'
            '<img src="blob:https://example.com/0f1e">'
            "</body></html>"
        )
        processed, links = dl._process_html(html, "https://example.com/")
        assert links == []
        # html-processing-7: a data: URI is left alone, not turned into a path.
        assert re.search(r'src="?data:image/gif;base64,R0lGODlhAQABAAAAACw="?', processed)
        assert re.search(r'href="?data:image/png;base64,iVBOR[" ]', processed)

    def test_download_requests_the_resolved_url(self, tmp_path):
        page = b'<html><body><a href="foo/">f</a><img src="../logo.png"></body></html>'
        dl, files, _, _ = _run(
            tmp_path,
            {
                "https://example.com/docs/": page,
                "https://example.com/docs/foo/": b"<html><body>foo</body></html>",
                "https://example.com/logo.png": b"\x89PNG\r\n\x1a\nxx",
            },
            wayback_url=f"https://web.archive.org/web/{TS}/https://example.com/docs/",
        )
        assert "docs/foo/index.html" in files
        assert "logo.png" in files
        for url in dl.session.calls:
            original = re.sub(r"^https://web\.archive\.org/web/\d+[a-z_]*/", "", url)
            assert urlparse(original).hostname == "example.com", url

    def test_picture_img_is_queued_once_and_absolute(self):
        """html-processing-12: the <picture> pass re-queued the rewritten src."""
        dl = _make_downloader(wayback_url=f"https://web.archive.org/web/{TS}/https://site.com/")
        html = (
            "<html><body><picture>"
            f'<source srcset="/web/{TS}im_/https://site.com/img/a.webp">'
            f'<img src="/web/{TS}im_/https://site.com/img/a.jpg">'
            "</picture></body></html>"
        )
        _, links = dl._process_html(html, "https://site.com/blog/post")
        assert all(link.startswith("https://site.com/") for link in links), links
        assert links.count("https://site.com/img/a.jpg") == 1


class TestOneFetchPerStoredFile:
    """Visited and queued are keyed by the file a URL is stored as."""

    def _gets(self, session, needle):
        return [u for u in session.calls if needle in u]

    def test_scheme_and_www_twins_are_fetched_once(self, tmp_path):
        page = (
            f'<html><body><a href="/web/{TS}/http://example.com/about">a</a>'
            f'<a href="/web/{TS}/https://example.com/about">b</a>'
            f'<a href="/web/{TS}/https://www.example.com/about">c</a>'
            f'<img src="/web/{TS}im_/http://example.com/a.png">'
            f'<img src="/web/{TS}im_/https://example.com/a.png"></body></html>'
        ).encode()
        dl, files, _, _ = _run(
            tmp_path,
            {
                "https://example.com/": page,
                "example.com/about": b"<html><body>about</body></html>",
                "example.com/a.png": b"\x89PNG\r\n\x1a\nxx",
            },
        )
        assert len(self._gets(dl.session, "/about")) == 1
        assert len(self._gets(dl.session, "/a.png")) == 1
        assert {"about.html", "a.png"} <= files

    def test_cache_busters_still_collapse(self, tmp_path):
        page = (
            b'<html><head><link rel="stylesheet" href="https://example.com/s.css?v=1">'
            b'<link rel="stylesheet" href="https://example.com/s.css?v=2"></head><body></body></html>'
        )
        dl, files, _, _ = _run(
            tmp_path,
            {"https://example.com/": page, "https://example.com/s.css?v=1": b"a{}"},
        )
        assert len(self._gets(dl.session, "/s.css")) == 1
        assert "s.css" in files

    def test_each_google_fonts_family_gets_its_own_file(self, tmp_path):
        page = (
            b'<html><head><link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Lato">'
            b'<link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Roboto">'
            b"</head><body></body></html>"
        )
        dl, files, _, output_dir = _run(
            tmp_path,
            {
                "https://example.com/": page,
                "https://fonts.googleapis.com/css?family=Lato": b"/* lato */",
                "https://fonts.googleapis.com/css?family=Roboto": b"/* roboto */",
            },
        )
        css_files = sorted(f for f in files if f.startswith("fonts.googleapis.com/css-"))
        assert len(css_files) == 2
        index = (output_dir / "index.html").read_text()
        linked = [h for h in _hrefs(index) if "fonts.googleapis.com" in h]
        assert len(linked) == 2
        for href in linked:
            assert (output_dir / unquote(href)).is_file(), href
        contents = {(output_dir / f).read_text() for f in css_files}
        assert contents == {"/* lato */", "/* roboto */"}


class TestTextIsDecodedNotDropped:
    """E2E-3, html-processing-2, download-loop-004."""

    def _saved(self, tmp_path, body, content_type=None, name="index.html", pages=None):
        pages = dict(pages or {})
        pages.setdefault("https://example.com/", (body, content_type))
        _, _, _, output_dir = _run(tmp_path, pages)
        return (output_dir / name).read_text(encoding="utf-8")

    def test_latin1_page_with_meta(self, tmp_path):
        body = (
            '<html><head><meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">'
            "<title>España</title></head><body><p>Sábado, año</p></body></html>"
        ).encode("latin-1")
        html = self._saved(tmp_path, body)
        assert "España" in html and "Sábado, año" in html
        assert re.search(r"charset=utf-8", html, re.I)
        assert "iso-8859-1" not in html.lower()

    def test_cp1252_page_without_any_declaration(self, tmp_path):
        body = "<html><body><p>Café, Año nuevo. Prix: 5€</p></body></html>".encode("cp1252")
        html = self._saved(tmp_path, body)
        assert "Café, Año nuevo. Prix: 5€" in html

    def test_shift_jis_page_with_meta(self, tmp_path):
        body = '<html><head><meta charset="Shift_JIS"></head><body>日本語のページ</body></html>'.encode("shift_jis")
        assert "日本語のページ" in self._saved(tmp_path, body)

    def test_http_charset_wins(self, tmp_path):
        body = "<html><body>日本語のページ</body></html>".encode("shift_jis")
        html = self._saved(tmp_path, body, content_type="text/html; charset=Shift_JIS")
        assert "日本語のページ" in html

    def test_undeclared_utf8_stays_intact(self, tmp_path):
        body = "<html><body>Año 日本</body></html>".encode("utf-8")
        assert "Año 日本" in self._saved(tmp_path, body)

    def test_latin1_stylesheet(self, tmp_path):
        page = b'<html><head><link rel="stylesheet" href="https://example.com/s.css"></head><body></body></html>'
        css = '@charset "iso-8859-1"; a:after{content:"Sábado"}'.encode("latin-1")
        saved = self._saved(
            tmp_path, page, name="s.css", pages={"https://example.com/s.css": css}
        )
        assert "Sábado" in saved
        # Saved as UTF-8, so the declaration must say so.
        assert '@charset "utf-8"' in saved and "iso-8859-1" not in saved


class TestHtmlIsNotSavedAsAnAsset:
    """E2E-4: Wayback answers some asset requests with its own HTML page."""

    WAYBACK_PAGE = b"<!DOCTYPE html>\n<html><head><title>Wayback Machine</title></head><body></body></html>"

    def test_html_answer_to_asset_requests_is_rejected(self, tmp_path):
        page = (
            b'<html><head><link rel="stylesheet" href="https://example.com/s.css">'
            b'<script src="https://example.com/app.js"></script></head><body>'
            b'<img src="https://example.com/logo.png"><img src="https://example.com/ok.png">'
            b"</body></html>"
        )
        _, files, out, _ = _run(
            tmp_path,
            {
                "https://example.com/": page,
                "https://example.com/s.css": self.WAYBACK_PAGE,
                "https://example.com/app.js": self.WAYBACK_PAGE,
                "https://example.com/logo.png": self.WAYBACK_PAGE,
                "https://example.com/ok.png": b"\x89PNG\r\n\x1a\nxx",
            },
        )
        assert "ok.png" in files
        assert not {"s.css", "app.js", "logo.png"} & files
        assert "Files failed: 3" in out
        assert "HTML page" in out


class TestWaybackUrlParsing:
    """url-and-rewrite-9, -10 and download-loop-008."""

    @pytest.mark.parametrize(
        "wayback_url",
        [
            f"https://web.archive.org/web/{TS}if_/https://example.com/",
            f"https://web.archive.org/web/{TS}id_/https://example.com/",
            f"http://archive.org/web/{TS}/https://example.com/",
            f"https://web.archive.org/web/{TS}/https://example.com:443/",
        ],
    )
    def test_accepted_forms(self, wayback_url):
        dl = _make_downloader(wayback_url=wayback_url)
        assert dl.config.base_url == "https://example.com/"
        assert dl.config.domain == "example.com"
        assert dl.original_timestamp == TS

    def test_default_port_does_not_make_the_site_external(self):
        dl = _make_downloader(
            wayback_url="https://web.archive.org/web/20050301000000/http://www.example.com:80/"
        )
        assert dl.config.domain == "www.example.com"
        html = (
            '<a href="/web/20050301000000/http://www.example.com/about.html">About</a>'
            '<a href="/web/20050301000000/http://www.example.com:80/b.html">B</a>'
        )
        processed, links = dl._process_html(html, dl.config.base_url)
        assert set(links) == {"http://www.example.com/about.html", "http://www.example.com:80/b.html"}
        assert re.search(r'href="?about\.html', processed)
        assert re.search(r'href="?b\.html', processed)

    @pytest.mark.parametrize("ts, year, month", [("2015", 2015, 1), ("201506", 2015, 6)])
    def test_short_timestamp_is_padded(self, ts, year, month):
        dl = _make_downloader(wayback_url=f"https://web.archive.org/web/{ts}/https://example.com/")
        assert (dl.original_datetime.year, dl.original_datetime.month) == (year, month)
