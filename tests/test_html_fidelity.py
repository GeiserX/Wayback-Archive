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


class TestTrackerAndAdRemovalMatchesHostsAndFileNames:
    """REMOVE_TRACKERS / REMOVE_ADS are on by default, so a loose word match
    deleted the site's own banners, popups and order-tracking scripts."""

    def test_site_assets_with_tracker_like_words_survive(self):
        dl = _make_dl()
        soup, links = _process(dl, (
            '<html><head>'
            f'<script src="{W}js_/https://site.com/js/omega.js"></script>'
            f'<script src="{W}js_/https://site.com/js/order-tracking.js"></script>'
            f'<script src="{W}js_/https://site.com/js/jquery.magnific-popup.min.js"></script>'
            f'<script src="{W}js_/https://site.com/js/stats.js"></script>'
            '<script>function toggleMenu(){}; window.dataLayer=window.dataLayer||[];</script>'
            '<script src="https://securepubads.g.doubleclick.net/tag/js/gpt.js"></script>'
            '<script src="https://www.googletagmanager.com/gtag/js?id=UA-1"></script>'
            "<script>function gtag(){dataLayer.push(arguments);}gtag('config','UA-1');</script>"
            '</head><body>'
            f'<img src="{W}im_/https://site.com/img/hero-banner.jpg">'
            f'<img src="{W}im_/https://site.com/img/threads.png">'
            f'<img src="{W}im_/https://site.com/img/sponsor-logo.png">'
            '<img src="https://ads.adnetwork.net/b.gif">'
            '</body></html>'
        ))
        html = str(soup)
        for name in ("js/omega.js", "js/order-tracking.js", "js/jquery.magnific-popup.min.js",
                     "js/stats.js", "img/hero-banner.jpg", "img/threads.png", "img/sponsor-logo.png"):
            assert name in html, name
            assert f"https://site.com/{name}" in links, name
        assert "toggleMenu" in html
        assert "doubleclick" not in html
        assert "googletagmanager" not in html
        assert "gtag('config'" not in html
        assert "adnetwork" not in html

    @pytest.mark.parametrize("url,expected", [
        ("https://www.google-analytics.com/analytics.js", True),
        ("https://stats.wp.com/e-202001.js", True),
        ("https://cdn.example.net/js/gtag.js", True),
        (f"{WA}js_/https://www.google-analytics.com/ga.js", True),
        ("https://site.com/js/analytics.js", False),
        ("https://www.site.com/stats.js", False),
        ("/js/ga.js", False),
        ("https://cdn.example.net/js/omega.js", False),
        ("https://cdn.example.net/js/order-tracking.js", False),
    ])
    def test_is_tracker(self, url, expected):
        assert _make_dl()._is_tracker(url) is expected

    @pytest.mark.parametrize("url,expected", [
        ("https://ads.adnetwork.net/a.js", True),
        ("https://pagead2.googlesyndication.com/x.js", True),
        ("https://site.com/img/banner.jpg", False),
        ("https://cdn.example.net/img/popup-close.png", False),
        ("https://cdn.example.net/uploads/threads.png", False),
    ])
    def test_is_ad(self, url, expected):
        assert _make_dl()._is_ad(url) is expected


class TestCatchAllAttributePasses:
    """The last passes over every attribute only touch values that are plainly
    one URL, and queue whatever they point at locally."""

    def test_json_data_attribute_is_left_alone(self):
        import json
        dl = _make_dl()
        value = '{"background_slideshow_gallery":[{"id":7,"url":"https:\\/\\/site.com\\/wp-content\\/uploads\\/a.jpg"}]}'
        soup, _ = _process(dl, f"<html><body><div data-settings='{value}'></div></body></html>")
        assert soup.div["data-settings"] == value
        json.loads(soup.div["data-settings"])

    def test_inline_handler_is_left_alone(self):
        dl = _make_dl()
        handler = f"location.href='{WA}/https://site.com/contact'"
        soup, _ = _process(dl, f'<html><body><button onclick="{handler}">c</button></body></html>')
        assert soup.button["onclick"] == handler

    def test_data_attribute_that_is_not_a_url_is_left_alone(self):
        dl = _make_dl()
        soup, _ = _process(dl, '<html><body><div data-email="info@site.com" data-domain="site.com"></div></body></html>')
        assert soup.div["data-email"] == "info@site.com"
        assert soup.div["data-domain"] == "site.com"

    def test_meta_refresh_keeps_its_delay_and_is_followed(self):
        dl = _make_dl()
        soup, links = _process(dl, (
            f'<html><head><meta http-equiv="refresh" content="0; url={WA}/https://site.com/new-page">'
            '</head><body></body></html>'
        ))
        assert soup.meta["content"] == "0; url=new-page.html"
        assert "https://site.com/new-page" in links

    def test_every_locally_rewritten_resource_is_queued(self):
        dl = _make_dl()
        soup, links = _process(dl, (
            '<html><body>'
            f'<img data-src="{W}im_/https://site.com/img/lazy.jpg" src="{W}im_/https://site.com/img/ph.gif">'
            f'<video poster="{W}im_/https://site.com/p.jpg"><source src="{W}/https://site.com/v.mp4"></video>'
            f'<audio src="{W}/https://site.com/a.mp3"></audio>'
            f'<object data="{W}/https://site.com/f.swf"></object>'
            f'<embed src="{W}/https://site.com/g.pdf">'
            f'<svg><image href="{W}im_/https://site.com/pic.png"></image></svg>'
            f'<input type="image" src="{W}im_/https://site.com/btn.png">'
            '</body></html>'
        ))
        assert soup.img["data-src"] == "img/lazy.jpg"
        assert soup.video["poster"] == "p.jpg"
        for name in ("img/lazy.jpg", "p.jpg", "v.mp4", "a.mp3", "f.swf", "g.pdf", "pic.png", "btn.png"):
            assert f"https://site.com/{name}" in links, name

    def test_extensionless_poster_is_fetched_as_an_image(self):
        dl = _make_dl()
        _process(dl, f'<html><body><video poster="{W}im_/https://site.com/media/poster"></video></body></html>')
        assert "im_/" in dl._convert_to_wayback_url("https://site.com/media/poster")
