"""The saved pages keep what the site had.

Each class pins one way _process_html, the CSS/JS URL helpers or the image
optimizer used to drop, corrupt or mis-point part of an archived page.
"""

import os

import pytest
from bs4 import BeautifulSoup

from wayback_archive.config import Config
from wayback_archive.downloader import WaybackDownloader

W = "/web/20200101000000"
WA = "https://web.archive.org" + W


def _make_dl(url="https://site.com/", **env):
    os.environ["WAYBACK_URL"] = f"https://web.archive.org{W}/{url}"
    for key, value in env.items():
        os.environ[key] = value
    config = Config()
    config.output_dir = "/tmp/wayback-html-fidelity"
    return WaybackDownloader(config)


@pytest.fixture(autouse=True)
def _clean_env():
    yield
    for key in (
        "WAYBACK_URL", "MAKE_WWW", "MAKE_NON_WWW", "OPTIMIZE_IMAGES",
        "REMOVE_EXTERNAL_LINKS_KEEP_ANCHORS", "REMOVE_EXTERNAL_LINKS_REMOVE_ANCHORS",
        "MAKE_INTERNAL_LINKS_RELATIVE", "OUTPUT_DIR",
    ):
        os.environ.pop(key, None)


def _process(dl, html, page="https://site.com/"):
    out, links = dl._process_html(html, page)
    return BeautifulSoup(out, "lxml"), links


class TestWaybackToolbarScripts:
    """Only the toolbar goes; page scripts replayed through Wayback stay."""

    def test_page_scripts_on_web_archive_org_are_kept(self):
        dl = _make_dl()
        soup, links = _process(dl, (
            f'<html><head><script src="{WA}js_/https://www.site.com/js/app.js"></script>'
            f'<script src="//web.archive.org{W}js_/https://site.com/js/protorel.js"></script>'
            f'<script src="{WA}js_/https://code.jquery.com/jquery.min.js"></script>'
            '<script src="https://web-static.archive.org/_static/js/wombat.js"></script>'
            '<script src="https://web-static.archive.org/_static/js/bundle-playback.js"></script>'
            '<script src="//archive.org/includes/athena.js"></script>'
            '</head><body></body></html>'
        ))
        srcs = [s["src"] for s in soup.find_all("script", src=True)]
        assert "js/app.js" in srcs
        assert "js/protorel.js" in srcs
        assert any("code.jquery.com/jquery.min.js" in s for s in srcs)
        assert not any("wombat" in s or "bundle-playback" in s or "athena" in s for s in srcs)
        assert "https://www.site.com/js/app.js" in links
        assert "https://site.com/js/protorel.js" in links
