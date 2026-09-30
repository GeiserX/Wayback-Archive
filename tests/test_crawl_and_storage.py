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
