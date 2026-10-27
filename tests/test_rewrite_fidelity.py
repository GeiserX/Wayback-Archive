"""The rewriting layer keeps the copy faithful to what the site had.

External references lose their Wayback prefix, text that looks like a URL
stays text, the site's comments and scripts stay, CSS fragments survive, and
the font clean-up touches only the @font-face rules it means to.
"""

import os
import re
from io import BytesIO

import pytest
from bs4 import BeautifulSoup

from wayback_archive.config import Config
from wayback_archive.downloader import WaybackDownloader

W = "/web/20200101000000"
WA = "https://web.archive.org" + W


def _make_dl(**env):
    os.environ["WAYBACK_URL"] = f"{WA}/https://site.com/"
    for key, value in env.items():
        os.environ[key] = value
    config = Config()
    config.output_dir = "/tmp/wayback-rewrite-fidelity"
    return WaybackDownloader(config)


@pytest.fixture(autouse=True)
def _clean_env():
    yield
    for key in ("WAYBACK_URL", "MAKE_INTERNAL_LINKS_RELATIVE", "OPTIMIZE_IMAGES", "MINIFY_CSS", "OPTIMIZE_HTML"):
        os.environ.pop(key, None)


def _process(dl, html, page="https://site.com/"):
    out, links = dl._process_html(html, page)
    return BeautifulSoup(out, "lxml"), links


class TestExternalReferencesLoseTheWaybackPrefix:
    def test_every_html_reference_gets_its_original_address(self):
        soup, links = _process(
            _make_dl(),
            (
                f'<html><head><script src="{WA}js_/https://cdn.other.com/x.js"></script>'
                f'<link rel="icon" href="{W}im_/https://cdn.other.com/fav.ico"></head><body>'
                f'<img src="{WA}im_/https://cdn.other.com/x.png" srcset="{WA}im_/https://cdn.other.com/x2.png 2x">'
                f'<iframe src="{WA}if_/https://www.youtube.com/embed/z"></iframe>'
                f'<video poster="{WA}im_/https://cdn.other.com/p.jpg"></video>'
                f'<table background="{WA}im_/https://cdn.other.com/t.gif"></table>'
                f'<div data-bg="{WA}im_/https://cdn.other.com/d.jpg"></div>'
                "</body></html>"
            ),
        )
        assert soup.script["src"] == "https://cdn.other.com/x.js"
        assert soup.find("link", rel="icon")["href"] == "https://cdn.other.com/fav.ico"
        assert soup.img["src"] == "https://cdn.other.com/x.png"
        assert soup.img["srcset"] == "https://cdn.other.com/x2.png 2x"
        assert soup.iframe["src"] == "https://www.youtube.com/embed/z"
        assert soup.video["poster"] == "https://cdn.other.com/p.jpg"
        assert soup.table["background"] == "https://cdn.other.com/t.gif"
        assert soup.div["data-bg"] == "https://cdn.other.com/d.jpg"
        assert "web.archive.org" not in str(soup)
        assert not any("other.com" in link for link in links)

    def test_css_url_and_import_get_their_original_address(self):
        dl = _make_dl()
        css = f'@import "{WA}cs_/https://cdn.other.com/a.css";.a{{background:url({WA}im_/https://cdn.other.com/b.png)}}'
        assert dl._rewrite_css_urls(css, "https://site.com/s.css") == (
            '@import "https://cdn.other.com/a.css";.a{background:url(https://cdn.other.com/b.png)}'
        )

    def test_inline_style_gets_its_original_address(self):
        soup, _ = _process(
            _make_dl(),
            f'<html><body><div style="background:url({W}im_/https://cdn.other.com/b.png)"></div></body></html>',
        )
        assert soup.div["style"] == "background:url(https://cdn.other.com/b.png)"

    def test_internal_references_still_go_local(self):
        soup, links = _process(_make_dl(), f'<html><body><img src="{WA}im_/https://site.com/a.png"></body></html>')
        assert soup.img["src"] == "a.png"
        assert links == ["https://site.com/a.png"]

    def test_external_sprite_keeps_its_address(self):
        soup, _ = _process(
            _make_dl(),
            f'<html><body><svg><use xlink:href="{W}im_/https://cdn.other.com/s.svg#icon"></use></svg></body></html>',
        )
        assert soup.find("use")["xlink:href"] == "https://cdn.other.com/s.svg#icon"

    def test_internal_iframe_in_wayback_form_survives_external_iframe_removal(self):
        soup, _ = _process(
            _make_dl(REMOVE_EXTERNAL_IFRAMES="true"),
            f'<html><body><iframe src="{WA}if_/https://site.com/frame.html"></iframe></body></html>',
        )
        os.environ.pop("REMOVE_EXTERNAL_IFRAMES", None)
        assert soup.iframe["src"] == "frame.html"

    def test_quoted_external_url_with_a_space_keeps_the_whole_address(self):
        css = f'.a{{background:url("{W}im_/https://cdn.other.com/a b.png")}}'
        assert _make_dl()._rewrite_css_urls(css, "https://site.com/s.css") == (
            '.a{background:url("https://cdn.other.com/a b.png")}'
        )


class TestUrlLikeTextStaysText:
    def test_text_attributes_are_not_rewritten_or_queued(self):
        soup, links = _process(
            _make_dl(),
            (
                '<html><head><meta name="description" content="https://site.com/desc"></head><body>'
                '<img alt="http://site.com/photo.jpg" title="https://site.com/t.jpg" src="/a.png">'
                '<input value="http://site.com/x"></body></html>'
            ),
        )
        assert soup.img["alt"] == "http://site.com/photo.jpg"
        assert soup.img["title"] == "https://site.com/t.jpg"
        assert soup.input["value"] == "http://site.com/x"
        assert soup.find("meta", attrs={"name": "description"})["content"] == "https://site.com/desc"
        assert links == ["https://site.com/a.png"]

    def test_url_attributes_still_go_local(self):
        soup, links = _process(
            _make_dl(),
            (
                '<html><head><meta property="og:image" content="https://site.com/og.png"></head><body>'
                '<form><button formaction="https://site.com/send">s</button></form>'
                '<div data-video_src="https://site.com/v.mp4"></div></body></html>'
            ),
        )
        assert soup.find("meta", property="og:image")["content"] == "og.png"
        assert soup.button["formaction"] == "send.html"
        assert soup.div["data-video_src"] == "v.mp4"
        assert "https://site.com/og.png" in links

    def test_every_image_meta_form_goes_local(self):
        soup, links = _process(
            _make_dl(),
            (
                '<html><head><meta property="og:image:secure_url" content="https://site.com/og.png">'
                '<meta property="og:image:url" content="https://site.com/og2.png">'
                '<meta name="twitter:image:src" content="https://site.com/tw.png">'
                '<meta itemprop="image" content="https://site.com/it.png"></head><body></body></html>'
            ),
        )
        assert [m["content"] for m in soup.find_all("meta")] == ["og.png", "og2.png", "tw.png", "it.png"]
        assert links == [f"https://site.com/{n}" for n in ("og.png", "og2.png", "tw.png", "it.png")]

    def test_base_href_resolves_srcset_and_formaction(self):
        soup, links = _process(
            _make_dl(),
            (
                '<html><head><base href="https://site.com/sub/"></head><body>'
                '<img srcset="a.png 1x, b.png 2x"><form><button formaction="go">g</button></form>'
                '<img alt="caption.png" src="c.png"></body></html>'
            ),
        )
        assert soup.find("img", srcset=True)["srcset"] == "sub/a.png 1x, sub/b.png 2x"
        assert soup.button["formaction"] == "sub/go.html"
        assert soup.find("img", alt=True)["alt"] == "caption.png"
        assert "https://site.com/sub/b.png" in links


class TestCommentsAndScripts:
    def test_site_comments_stay_and_wayback_comments_go(self):
        dl = _make_dl()
        out, _ = dl._process_html(
            (
                "<html><head><!--[if lt IE 9]><script src='h5.js'></script><![endif]--></head><body>"
                "<!-- ko if: shown --><p>x</p><!-- /ko -->"
                "<!-- BEGIN WAYBACK TOOLBAR INSERT --><!-- END WAYBACK TOOLBAR INSERT -->"
                "<!--\n FILE ARCHIVED ON 12:00:00 AND RETRIEVED FROM THE\n INTERNET ARCHIVE ON 13:00 -->"
                "<!-- playback timings (ms): captures_list: 1 --></body></html>"
            ),
            "https://site.com/",
        )
        assert "<!--[if lt IE 9]>" in out
        assert "<!-- ko if: shown -->" in out and "<!-- /ko -->" in out
        assert "WAYBACK" not in out and "ARCHIVED ON" not in out and "playback timings" not in out

    def test_conditional_comment_in_wayback_form_is_kept_and_rewritten(self):
        out, links = _make_dl()._process_html(
            (
                f'<html><head><!--[if lt IE 9]><script src="{WA}js_/https://site.com/h5.js"></script><![endif]-->'
                f'<!--[if lt IE 8]><link rel="stylesheet" href="{W}cs_/https://site.com/ie7.css"><![endif]-->'
                f'<!--[if IE]><script src="{W}js_/https://cdn.other.com/r.js"></script><![endif]-->'
                "</head><body></body></html>"
            ),
            "https://site.com/",
        )
        assert '<!--[if lt IE 9]><script src="h5.js"></script><![endif]-->' in out
        assert '<!--[if lt IE 8]><link rel="stylesheet" href="ie7.css"><![endif]-->' in out
        assert '<script src="https://cdn.other.com/r.js">' in out
        assert "/web/" not in out
        assert links == ["https://site.com/h5.js", "https://site.com/ie7.css"]

    def test_site_script_naming_the_archive_survives(self):
        soup, _ = _process(
            _make_dl(),
            (
                "<html><body>"
                '<script>var link = "https://web.archive.org/web/2019/https://site.com/"; var wombat = 1;</script>'
                '<script>__wm.init("https://web.archive.org/web");\n__wm.wombat("https://site.com/");</script>'
                "<script>window.RufflePlayer=window.RufflePlayer||{};"
                'window.RufflePlayer.config={"base":"https://web-static.archive.org/_static/js/ruffle/"};</script>'
                "<script>var v=archive_analytics.values;archive_analytics.send_pageview({});</script>"
                "</body></html>"
            ),
        )
        scripts = [s.string for s in soup.find_all("script")]
        assert scripts == ['var link = "https://web.archive.org/web/2019/https://site.com/"; var wombat = 1;']

    def test_site_ruffle_config_survives(self):
        soup, _ = _process(
            _make_dl(), "<html><body><script>window.RufflePlayer = window.RufflePlayer || {};</script></body></html>"
        )
        assert soup.script is not None


class TestCssFragments:
    def test_fragment_survives_relative_rewrite(self):
        dl = _make_dl()
        dl._current_page_url = "https://site.com/"
        css = ".a{mask:url(/img/sprite.svg#icon)}.b{filter:url(https://site.com/f.svg#blur)}"
        assert dl._rewrite_css_urls(css, "https://site.com/") == (
            ".a{mask:url(img/sprite.svg#icon)}.b{filter:url(f.svg#blur)}"
        )

    def test_fragment_survives_with_relative_links_off(self):
        dl = _make_dl(MAKE_INTERNAL_LINKS_RELATIVE="false")
        assert dl._rewrite_css_urls(".a{mask:url(/s.svg#i)}", "https://site.com/") == (
            ".a{mask:url(https://site.com/s.svg#i)}"
        )


class TestLegacyFontCleanupStaysInFontFace:
    def test_rules_outside_font_face_are_untouched(self):
        css = (
            '.q:before{content:",,"}.x{--src:url(a.eot)}.m{mask:url(m.svg) format("svg")}'
            ".i{background:url(icons.svg) no-repeat}"
        )
        assert _make_dl()._remove_legacy_font_formats_from_css(css) == css

    def test_font_with_only_legacy_sources_keeps_them(self):
        css = "@font-face{font-family:F;src:url(f.eot) format('embedded-opentype'),url(f.svg#F) format('svg')}"
        assert _make_dl()._remove_legacy_font_formats_from_css(css) == css

    def test_legacy_sources_with_query_or_fragment_go_when_a_modern_one_remains(self):
        css = (
            "@font-face{font-family:F;src:url(f.eot);src:url(f.eot?#iefix) format('embedded-opentype'),"
            "url(f.woff2) format('woff2'),url(f.svg#F) format('svg')}"
        )
        assert _make_dl()._remove_legacy_font_formats_from_css(css) == (
            "@font-face{font-family:F;src:url(f.woff2) format('woff2')}"
        )


class TestCorruptedFontMatchesTheWholePath:
    def test_same_file_name_in_another_folder_stays(self):
        dl = _make_dl()
        dl.corrupted_fonts.add("https://site.com/fonts/a.woff")
        css = "@font-face{src:url(../fonts/a.woff) format('woff'),url(../other/a.woff) format('woff')}"
        assert dl._remove_corrupted_fonts_from_css(css) == "@font-face{src:url(../other/a.woff) format('woff')}"

    def test_absolute_and_root_relative_references_match_exactly(self):
        dl = _make_dl()
        dl.corrupted_fonts.add("https://site.com/fonts/a.woff")
        css = (
            "@font-face{src:url(https://www.site.com/fonts/a.woff),url(/other/a.woff)}"
            "@font-face{src:url(/fonts/a.woff?v=2),url(https://cdn.other.com/fonts/a.woff)}"
        )
        assert dl._remove_corrupted_fonts_from_css(css) == (
            "@font-face{src:url(/other/a.woff)}@font-face{src:url(https://cdn.other.com/fonts/a.woff)}"
        )

    def test_google_font_local_path_matches(self):
        dl = _make_dl()
        dl.corrupted_fonts.add("https://fonts.gstatic.com/s/roboto/v1/r.woff2")
        css = "@font-face{src:url(../fonts.gstatic.com/s/roboto/v1/r.woff2) format('woff2'),url(r.ttf)}"
        assert dl._remove_corrupted_fonts_from_css(css) == "@font-face{src:url(r.ttf)}"

    def test_bare_file_name_without_a_stylesheet_names_no_foldered_font(self):
        dl = _make_dl()
        dl.corrupted_fonts.add("https://site.com/fonts/a.woff")
        css = "@font-face{src:url(a.woff),url(x/fonts/a.woff),url(../fonts/a.woff)}"
        assert dl._remove_corrupted_fonts_from_css(css) == "@font-face{src:url(a.woff),url(x/fonts/a.woff)}"

    def test_relative_reference_resolves_from_the_stylesheet(self):
        dl = _make_dl()
        dl.corrupted_fonts.add("https://site.com/fonts/a.woff")
        css = "@font-face{src:url(a.woff),url(../fonts/a.woff),url(b.woff)}"
        assert dl._remove_corrupted_fonts_from_css(css, "https://site.com/css/s.css") == (
            "@font-face{src:url(a.woff),url(b.woff)}"
        )
        assert dl._remove_corrupted_fonts_from_css(css, "https://site.com/fonts/f.css") == "@font-face{src:url(b.woff)}"

    def test_nothing_outside_font_face_changes(self):
        dl = _make_dl()
        dl.corrupted_fonts.add("https://site.com/fonts/a.woff")
        css = '.q:before{content:",,"}.b{background:url(/fonts/a.woff)}'
        assert dl._remove_corrupted_fonts_from_css(css) == css


class TestCssScanAndMinify:
    def test_commented_out_urls_are_not_queued(self):
        css = "/* .old{background:url(/old.png)}\n */ .a{background:url(/new.png)}"
        assert _make_dl()._extract_css_urls(css, "https://site.com/") == ["https://site.com/new.png"]

    def test_the_css_minifier_is_a_declared_dependency(self):
        """CI and the wheel install config/requirements.txt; an undeclared
        minifier makes MINIFY_CSS a silent no-op."""
        from pathlib import Path

        requirements = (Path(__file__).parent.parent / "config" / "requirements.txt").read_text()
        names = {re.split(r"[<>=!~\[;\s]", line.strip(), maxsplit=1)[0].lower() for line in requirements.splitlines()}
        assert "rcssmin" in names

    def test_minify_keeps_calc_and_supports_valid(self):
        dl = _make_dl(MINIFY_CSS="true")
        out = dl._minify_css(
            ".a { width: calc(1px + -2px); }\n@supports (display: grid) and (not (display: x)) { .b { c: d } }"
        )
        assert "calc(1px + -2px)" in out
        assert "not (display:x)" in out


class TestHtmlMinifyIsOptIn:
    def test_default_is_off_and_output_is_untouched(self):
        dl = _make_dl()
        assert dl.config.optimize_html is False
        html = "<div><span>a</span> <span>b</span></div>"
        assert dl._optimize_html(html) == html


class TestImageOptimizationKeepsWhatShapesTheImage:
    @staticmethod
    def _jpeg(progressive):
        from PIL import Image, ImageCms

        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        exif = Image.Exif()
        exif[0x0112] = 6  # orientation
        buf = BytesIO()
        Image.effect_noise((128, 128), 60).convert("RGB").save(
            buf, "JPEG", quality=100, icc_profile=profile, exif=exif.tobytes(), progressive=progressive
        )
        return buf.getvalue()

    def test_jpeg_keeps_profile_exif_and_progressive(self):
        from PIL import Image

        src = self._jpeg(progressive=True)
        out = _make_dl(OPTIMIZE_IMAGES="true")._optimize_image(src, "JPEG")
        assert len(out) < len(src)
        img = Image.open(BytesIO(out))
        assert img.info.get("icc_profile")
        assert img.getexif().get(0x0112) == 6
        assert img.info.get("progressive")

    def test_baseline_jpeg_stays_baseline(self):
        from PIL import Image

        out = _make_dl(OPTIMIZE_IMAGES="true")._optimize_image(self._jpeg(progressive=False), "JPEG")
        assert not Image.open(BytesIO(out)).info.get("progressive")

    def test_lossless_webp_is_left_alone(self):
        from PIL import Image

        buf = BytesIO()
        Image.effect_noise((64, 64), 60).convert("RGB").save(buf, "WEBP", lossless=True)
        src = buf.getvalue()
        assert _make_dl(OPTIMIZE_IMAGES="true")._optimize_image(src, "WEBP") == src
