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

    def test_site_static_js_bundle_is_kept(self):
        # /static/js/ is where create-react-app puts the site's own bundles.
        dl = _make_dl()
        soup, links = _process(dl, '<html><head><script src="/static/js/main.abc.js"></script></head><body></body></html>')
        assert soup.script["src"] == "static/js/main.abc.js"
        assert "https://site.com/static/js/main.abc.js" in links


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


class TestSrcset:
    """Every srcset keeps every candidate, each rewritten and downloaded."""

    def test_img_srcset_keeps_all_candidates(self):
        dl = _make_dl()
        soup, links = _process(dl, (
            f'<html><body><img src="{W}im_/https://site.com/a.jpg" '
            f'srcset="{W}im_/https://site.com/a-1x.jpg 1x, {W}im_/https://site.com/a-2x.jpg 2x">'
            '</body></html>'
        ))
        assert soup.img["srcset"] == "a-1x.jpg 1x, a-2x.jpg 2x"
        assert "https://site.com/a-1x.jpg" in links
        assert "https://site.com/a-2x.jpg" in links

    def test_candidates_without_space_after_comma(self):
        dl = _make_dl()
        soup, links = _process(dl, (
            f'<html><body><img srcset="{W}im_/https://site.com/s.jpg 300w,{W}im_/https://site.com/m.jpg 600w">'
            '</body></html>'
        ))
        assert soup.img["srcset"] == "s.jpg 300w, m.jpg 600w"
        assert "https://site.com/m.jpg" in links

    def test_link_imagesrcset_and_data_srcset(self):
        dl = _make_dl()
        soup, links = _process(dl, (
            f'<html><head><link rel="preload" as="image" imagesrcset="{W}im_/https://site.com/p1.jpg 1x, {W}im_/https://site.com/p2.jpg 2x"></head>'
            f'<body><img data-srcset="{W}im_/https://site.com/l1.jpg 1x, {W}im_/https://site.com/l2.jpg 2x"></body></html>'
        ))
        assert soup.link["imagesrcset"] == "p1.jpg 1x, p2.jpg 2x"
        assert soup.img["data-srcset"] == "l1.jpg 1x, l2.jpg 2x"
        for name in ("p1.jpg", "p2.jpg", "l1.jpg", "l2.jpg"):
            assert f"https://site.com/{name}" in links

    def test_commas_inside_candidate_urls_survive(self):
        dl = _make_dl()
        soup, links = _process(dl, (
            '<html><body><picture><source srcset="'
            f'{WA}im_/https://res.cloudinary.com/demo/image/upload/w_400,c_fill/a.jpg 400w, '
            f'{WA}im_/https://res.cloudinary.com/demo/image/upload/w_800,c_fill/a.jpg 800w">'
            f'<img src="{W}im_/https://site.com/x.jpg"></picture></body></html>'
        ))
        srcset = soup.source["srcset"]
        assert "w_400,c_fill/a.jpg 400w" in srcset
        assert "w_800,c_fill/a.jpg 800w" in srcset
        assert not any(link.endswith("c_fill/a.jpg") and "cloudinary" not in link for link in links)


class TestAnchors:
    """Links keep their fragments, script links and markup."""

    def test_fragments_survive(self):
        dl = _make_dl()
        soup, links = _process(dl, (
            '<html><body><a href="#myCarousel" data-slide="prev">p</a><a href="#">t</a>'
            f'<a href="{W}/https://site.com/about#team">a</a></body></html>'
        ), page="https://site.com/blog/post")
        assert [a["href"] for a in soup.find_all("a")] == ["#myCarousel", "#", "../about.html#team"]
        assert links == ["https://site.com/about"]

    def test_fragments_survive_with_relative_links_off(self):
        dl = _make_dl(MAKE_INTERNAL_LINKS_RELATIVE="false")
        soup, _ = _process(dl, f'<html><body><a href="{W}/https://site.com/about#team">a</a></body></html>')
        assert soup.a["href"] == "https://site.com/about#team"

    def test_area_and_meta_refresh_keep_their_fragments(self):
        dl = _make_dl()
        soup, links = _process(dl, (
            '<html><head><meta http-equiv="refresh" content="0; url=next.html#a"></head><body>'
            f'<map><area href="{W}/https://site.com/about#team"></map></body></html>'
        ))
        assert soup.meta["content"] == "0; url=next.html#a"
        assert soup.area["href"] == "about.html#team"
        assert "https://site.com/next.html" in links

    def test_javascript_links_are_left_alone(self):
        dl = _make_dl()
        soup, _ = _process(dl, (
            '<html><body><a href="javascript:void(0)" onclick="openMenu()" class="menu-toggle">'
            '<span class="icon"></span> Menu</a><a href="javascript:window.print()">Print</a></body></html>'
        ))
        anchors = soup.find_all("a")
        assert [a["href"] for a in anchors] == ["javascript:void(0)", "javascript:window.print()"]
        assert anchors[0]["onclick"] == "openMenu()"
        assert anchors[0].find("span", class_="icon") is not None

    def test_flattened_external_link_keeps_its_children(self):
        dl = _make_dl()
        soup, links = _process(dl, (
            f'<html><body><a href="{W}/https://partner.org/"><img src="{W}im_/https://site.com/logo-partner.png"></a>'
            f'<a href="{W}/https://x.org/"><strong>Bold</strong> text</a></body></html>'
        ))
        assert soup.find("a") is None
        assert soup.img["src"] == "logo-partner.png"
        assert "https://site.com/logo-partner.png" in links
        assert "<strong>Bold</strong> text" in str(soup)

    def test_kept_external_link_loses_its_wayback_prefix(self):
        dl = _make_dl(REMOVE_EXTERNAL_LINKS_KEEP_ANCHORS="false")
        soup, _ = _process(dl, f'<html><body><a href="{W}/https://twitter.com/site">t</a></body></html>')
        assert soup.a["href"] == "https://twitter.com/site"


class TestBaseHref:
    """<base href> is honoured while resolving, then dropped from the output,
    since every link written is relative to the page's own file."""

    def test_base_href_resolves_links_and_is_removed(self):
        dl = _make_dl()
        soup, links = _process(dl, (
            f'<html><head><base href="{W}/https://site.com/" target="_blank"></head><body>'
            '<a href="other.html">o</a><img src="img/a.jpg">'
            f'<a href="{W}/https://site.com/blog/sibling.html">s</a>'
            '</body></html>'
        ), page="https://site.com/blog/post")
        assert soup.base is None or not soup.base.has_attr("href")
        assert soup.base["target"] == "_blank"
        assert soup.find("a", string="o")["href"] == "../other.html"
        assert soup.find("a", string="s")["href"] == "sibling.html"
        assert soup.img["src"] == "../img/a.jpg"
        assert "https://site.com/other.html" in links
        assert "https://site.com/img/a.jpg" in links

    def test_base_without_other_attributes_is_removed(self):
        dl = _make_dl()
        soup, _ = _process(dl, f'<html><head><base href="{W}/https://site.com/"></head><body></body></html>')
        assert soup.base is None

    def test_every_relative_reference_follows_the_base(self):
        dl = _make_dl()
        soup, links = _process(dl, (
            f'<html><head><base href="{W}/https://site.com/"><style>a{{background:url(img/s.png)}}</style></head><body>'
            '<div style="background:url(img/bg.png)"></div><form action="search"></form>'
            '<video poster="p.jpg"><source src="v.mp4"></video><img data-src="img/lazy.jpg">'
            '<map><area href="about.html"></map><object data="f.swf"></object><input src="b.png" type="image">'
            '<table background="img/t.gif"></table>'
            '</body></html>'
        ), page="https://site.com/blog/post")
        assert soup.div["style"] == "background:url(../img/bg.png)"
        assert soup.style.string == "a{background:url(../img/s.png)}"
        assert soup.form["action"] == "../search.html"
        assert soup.video["poster"] == "../p.jpg"
        assert soup.source["src"] == "../v.mp4"
        assert soup.img["data-src"] == "../img/lazy.jpg"
        assert soup.area["href"] == "../about.html"
        assert soup.object["data"] == "../f.swf"
        assert soup.input["src"] == "../b.png"
        assert soup.table["background"] == "../img/t.gif"
        for name in ("img/bg.png", "img/s.png", "p.jpg", "v.mp4", "img/lazy.jpg", "f.swf", "b.png", "img/t.gif"):
            assert f"https://site.com/{name}" in links, name

    def test_base_on_another_host_gives_it_no_local_paths(self):
        dl = _make_dl()
        soup, links = _process(dl, (
            '<html><head><base href="https://shop.other.com/x/"></head><body>'
            '<a href="cart.html">c</a><img src="logo.png"><video poster="p.jpg"></video>'
            f'<a href="{W}/https://site.com/about">a</a>'
            '<video poster="https://site.com/p2.jpg"></video>'
            '</body></html>'
        ), page="https://site.com/blog/post")
        assert soup.base is None
        assert soup.find("a", string="c") is None or soup.find("a", string="c")["href"] == "https://shop.other.com/x/cart.html"
        assert soup.img["src"] == "https://shop.other.com/x/logo.png"
        posters = [v["poster"] for v in soup.find_all("video")]
        assert posters == ["https://shop.other.com/x/p.jpg", "../p2.jpg"]
        assert soup.find("a", string="a")["href"] == "../about.html"
        assert not any("other.com" in link for link in links)
        assert "https://site.com/about" in links
        assert "https://site.com/p2.jpg" in links


class TestSvgUseSprites:
    """<use> pointing into a sprite file keeps the file; one pointing into
    the page itself keeps just the fragment."""

    def test_external_sprite_is_kept_and_downloaded(self):
        dl = _make_dl()
        soup, links = _process(dl, (
            f'<html><body><svg><use xlink:href="{W}im_/https://site.com/assets/sprite.svg#icon-search"></use></svg>'
            '</body></html>'
        ), page="https://site.com/blog/post")
        assert soup.find("use")["xlink:href"] == "../assets/sprite.svg#icon-search"
        assert "https://site.com/assets/sprite.svg" in links

    def test_external_sprite_keeps_its_symbol_with_relative_links_off(self):
        dl = _make_dl(MAKE_INTERNAL_LINKS_RELATIVE="false")
        soup, links = _process(dl, f'<html><body><svg><use xlink:href="{W}im_/https://site.com/s.svg#i"></use></svg></body></html>')
        assert soup.find("use")["xlink:href"] == "https://site.com/s.svg#i"
        assert "https://site.com/s.svg" in links

    def test_same_page_symbol_keeps_the_fragment(self):
        dl = _make_dl()
        soup, links = _process(dl, (
            f'<html><body><svg><use xlink:href="{W}im_/https://site.com/#email-icon" href="{W}im_/https://site.com/#email-icon"></use></svg>'
            '</body></html>'
        ))
        use = soup.find("use")
        assert use["xlink:href"] == "#email-icon"
        assert use["href"] == "#email-icon"
        assert links == []


class TestExternalStylesheets:
    """The external-link flags are about links, not a page's stylesheets."""

    @pytest.mark.parametrize("keep,remove", [("true", "true"), ("false", "false")])
    def test_external_stylesheet_survives_with_its_live_url(self, keep, remove):
        dl = _make_dl(REMOVE_EXTERNAL_LINKS_KEEP_ANCHORS=keep, REMOVE_EXTERNAL_LINKS_REMOVE_ANCHORS=remove)
        soup, _ = _process(dl, (
            f'<html><head><link rel="stylesheet" href="{W}cs_/https://stackpath.bootstrapcdn.com/bootstrap/4.5.0/css/bootstrap.min.css">'
            '</head><body></body></html>'
        ))
        assert soup.link["href"] == "https://stackpath.bootstrapcdn.com/bootstrap/4.5.0/css/bootstrap.min.css"


class TestWwwConversionOnlyForTheSite:
    """MAKE_WWW / MAKE_NON_WWW apply to the archived site's host only."""

    def test_make_www_leaves_third_party_hosts(self):
        dl = _make_dl(MAKE_WWW="true")
        soup, _ = _process(dl, (
            f'<html><head><link rel="stylesheet" href="{W}cs_/https://cdn.jsdelivr.net/npm/bootstrap.css"></head></html>'
        ))
        assert soup.link["href"] == "https://cdn.jsdelivr.net/npm/bootstrap.css"

    def test_make_non_www_leaves_third_party_hosts(self):
        dl = _make_dl()
        soup, _ = _process(dl, (
            f'<html><head><link rel="stylesheet" href="{W}cs_/https://www.gstatic.com/x.css"></head></html>'
        ))
        assert soup.link["href"] == "https://www.gstatic.com/x.css"

    def test_make_www_wins_over_make_non_www(self):
        dl = _make_dl(MAKE_WWW="true", MAKE_INTERNAL_LINKS_RELATIVE="false")
        dl.config.make_non_www = True
        soup, _ = _process(dl, (
            f'<html><body><a href="{W}/https://site.com/about">a</a>'
            f'<a href="{W}/https://www.site.com/about2">b</a></body></html>'
        ))
        assert [a["href"] for a in soup.find_all("a")] == [
            "https://www.site.com/about", "https://www.site.com/about2",
        ]


class TestUrlsWithParentheses:
    """Wikipedia-style names like File_(2).png keep their parentheses."""

    def test_html_references_keep_parentheses(self):
        dl = _make_dl()
        soup, links = _process(dl, (
            f'<html><body><img src="{W}im_/https://site.com/wiki/File_(2).png">'
            f'<a href="{W}/https://site.com/wiki/Foo_(bar)">f</a></body></html>'
        ))
        assert soup.img["src"] == "wiki/File_%282%29.png"
        assert soup.a["href"] == "wiki/Foo_%28bar%29.html"
        assert "https://site.com/wiki/File_(2).png" in links
        assert "https://site.com/wiki/Foo_(bar)" in links

    def test_closing_paren_of_a_wrapper_is_still_dropped(self):
        dl = _make_dl()
        assert dl._extract_original_url_from_path(f"url({W}im_/https://site.com/a.png)") == "https://site.com/a.png"
        assert dl._extract_original_url_from_path(f"url({W}im_/https://site.com/a_(1).png)") == "https://site.com/a_(1).png"

    def test_css_references_keep_parentheses(self):
        dl = _make_dl()
        dl._current_page_url = "https://site.com/css/style.css"
        css = f"a{{background:url({W}im_/https://site.com/img/photo_(1).jpg)}}"
        assert dl._extract_css_urls(css, "https://site.com/css/style.css") == ["https://site.com/img/photo_(1).jpg"]
        assert dl._rewrite_css_urls(css, "https://site.com/css/style.css") == "a{background:url(../img/photo_%281%29.jpg)}"


class TestGoogleFontsInsideStylesheets:
    """A site stylesheet's Google Fonts @import points at the file stored."""

    def test_imports_point_at_the_stored_font_stylesheets(self):
        import re
        dl = _make_dl()
        dl._current_page_url = "https://site.com/css/style.css"
        css = (
            f"@import url({W}cs_/https://fonts.googleapis.com/css?family=Open+Sans:400,700); "
            '@import url("https://fonts.googleapis.com/css?family=Lato"); '
            '@import "https://fonts.googleapis.com/css2?family=Roboto"; '
            "a{src:url(https://fonts.gstatic.com/s/x/v1/a.woff2)}"
        )
        out = dl._rewrite_css_urls(css, "https://site.com/css/style.css")
        assert "css.css" not in out
        imports = re.findall(r"\.\./fonts\.googleapis\.com/css-[0-9a-f]{8}\.css", out)
        assert len(imports) == 3 and len(set(imports)) == 3
        for url in dl._extract_css_urls(css, "https://site.com/css/style.css")[:3]:
            assert dl._make_relative_path(url, "stylesheet") in imports
        assert "url(../fonts.gstatic.com/s/x/v1/a.woff2)" in out


class TestJsUrlExtraction:
    """Root-relative URLs and names containing "if" (.gif, life) are URLs."""

    @pytest.mark.parametrize("js,expected", [
        ('a.src="/images/loading.gif"', ["https://site.com/images/loading.gif"]),
        ('fetch("/api/data.json")', ["https://site.com/api/data.json"]),
        ('y.src="https://site.com/img/spinner.gif"', ["https://site.com/img/spinner.gif"]),
        ('y.src="https://site.com/img/life.png"', ["https://site.com/img/life.png"]),
        ('y.src="https://site.com/img/File_(2).png"', ["https://site.com/img/File_(2).png"]),
        ('z.src="https://site.com/a.png;v=2"', ["https://site.com/a.png;v=2"]),
        ('y.src="function(){return 1}"', []),
        ('y.href="/a b"', []),
        ('y.src="https://other.com/x.png"', []),
    ])
    def test_extract(self, js, expected):
        assert _make_dl()._extract_js_urls(js, "https://site.com/js/a.js") == expected


class TestOptimizeImagesKeepsWhatImagesAre:
    """OPTIMIZE_IMAGES compresses; it never drops alpha, frames or formats."""

    @staticmethod
    def _encode(img, fmt, **kwargs):
        from io import BytesIO
        buf = BytesIO()
        img.save(buf, format=fmt, **kwargs)
        return buf.getvalue()

    def test_png_keeps_transparency(self):
        from io import BytesIO
        from PIL import Image
        dl = _make_dl(OPTIMIZE_IMAGES="true")
        content = self._encode(Image.new("RGBA", (64, 64), (255, 0, 0, 0)), "PNG")
        out = Image.open(BytesIO(dl._optimize_image(content, "PNG")))
        assert out.mode == "RGBA"
        assert out.getpixel((0, 0))[3] == 0

    def test_animated_gif_is_left_alone(self):
        from PIL import Image
        dl = _make_dl(OPTIMIZE_IMAGES="true")
        frames = [Image.new("P", (8, 8), i * 40) for i in range(5)]
        content = self._encode(frames[0], "GIF", save_all=True, append_images=frames[1:])
        assert dl._optimize_image(content, "GIF") == content

    def test_favicon_is_saved_as_the_icon_it_is(self, tmp_path):
        import contextlib
        import io
        from PIL import Image
        dl = _make_dl(OPTIMIZE_IMAGES="true")
        dl.config.output_dir = str(tmp_path)
        ico = self._encode(Image.new("RGBA", (16, 16), (0, 0, 255, 128)), "ICO")
        page = b'<html><head><link rel="icon" href="/favicon.ico"></head><body>x</body></html>'
        bodies = {"https://site.com/": page, "https://site.com/favicon.ico": ico}
        dl.download_file = lambda url: bodies.get(url)
        with contextlib.redirect_stdout(io.StringIO()):
            dl.download()
        assert (tmp_path / "favicon.ico").read_bytes() == ico
