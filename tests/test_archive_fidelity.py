"""Regression tests for archives that did not faithfully reproduce the site.

Three defects lived here, all invisible because nothing asserted the *whole*
path or the *whole* rewritten document:

* every ``/section/`` page was written to the root ``index.html``, so a site
  archived down to a single file;
* inline ``style="...url(...)"`` was only rewritten for Wayback-form URLs, so a
  plain one stayed pointed at the live site;
* rewritten links were not percent-encoded, so a file named ``a#b.png`` was
  linked as a fragment;
* a stylesheet's ``url()`` links were made relative to the last HTML page
  processed instead of to the stylesheet itself.
"""

import io
import contextlib
import os
import re
from urllib.parse import unquote

import pytest
from wayback_archive.config import Config
from wayback_archive.downloader import WaybackDownloader


def _make_downloader(output_dir=None):
    """Create a downloader with a clean environment."""
    os.environ["WAYBACK_URL"] = (
        "https://web.archive.org/web/20250417203037/http://example.com/"
    )
    config = Config()
    if output_dir is not None:
        config.output_dir = str(output_dir)
    return WaybackDownloader(config)


class TestDirectoryPagesGetTheirOwnIndex:
    """A trailing-slash URL is a directory, not the site root."""

    def setup_method(self):
        """Set up test fixtures."""
        self.downloader = _make_downloader("/tmp/wayback-archive-fidelity")

    def teardown_method(self):
        """Clean up after tests."""
        os.environ.pop("WAYBACK_URL", None)

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("http://example.com/", "index.html"),
            ("http://example.com/blog/", "blog/index.html"),
            ("http://example.com/blog/2024/", "blog/2024/index.html"),
            ("http://example.com/a//b//", "a/b/index.html"),
        ],
    )
    def test_directory_url_lands_inside_that_directory(self, url, expected):
        """The whole path matters here, not just the filename."""
        local_path = self.downloader._get_local_path(url)
        assert local_path == self.downloader._resolve_output_path(expected)

    def test_sections_do_not_collide_with_the_root(self):
        """Two directory pages and the root must be three different files."""
        paths = {
            self.downloader._get_local_path(url)
            for url in (
                "http://example.com/",
                "http://example.com/blog/",
                "http://example.com/about/",
            )
        }
        assert len(paths) == 3

    @pytest.mark.parametrize(
        "url", ["http://example.com/blog/", "http://example.com/a/b/"]
    )
    def test_link_and_file_agree_for_directory_urls(self, url):
        """The link written into the HTML must name the file on disk."""
        self.downloader._current_page_url = "http://example.com/"
        link = self.downloader._get_relative_link_path(url, "page")
        local_path = self.downloader._get_local_path(url)
        assert self.downloader._resolve_output_path(unquote(link)) == local_path


class TestWholeSiteSurvivesArchiving:
    """End-to-end: a site of directory pages must not collapse to one file."""

    def teardown_method(self):
        """Clean up after tests."""
        os.environ.pop("WAYBACK_URL", None)

    def test_every_page_is_kept(self, tmp_path):
        """Each page keeps its own file instead of overwriting the root."""
        pages = {
            "http://example.com/": b"<html><body><h1>ROOT</h1>"
            b'<a href="http://example.com/blog/">b</a>'
            b'<a href="http://example.com/about/">a</a></body></html>',
            "http://example.com/blog/": b"<html><body><h1>BLOG</h1></body></html>",
            "http://example.com/about/": b"<html><body><h1>ABOUT</h1></body></html>",
        }

        output_dir = tmp_path / "output"
        downloader = _make_downloader(output_dir)
        downloader.download_file = lambda url: pages.get(url, b"ASSET")
        with contextlib.redirect_stdout(io.StringIO()):
            downloader.download()

        written = {
            str(p.relative_to(output_dir)): p.read_text("utf-8", "replace")
            for p in output_dir.rglob("*")
            if p.is_file()
        }

        assert set(written) == {"index.html", "blog/index.html", "about/index.html"}
        assert "ROOT" in written["index.html"]
        assert "BLOG" in written["blog/index.html"]
        assert "ABOUT" in written["about/index.html"]


class TestInlineStyleUrlsArePointedAtLocalFiles:
    """An inline style must not keep calling out to the live site."""

    def setup_method(self):
        """Set up test fixtures."""
        self.downloader = _make_downloader("/tmp/wayback-archive-fidelity")
        self.downloader._current_page_url = "http://example.com/"

    def teardown_method(self):
        """Clean up after tests."""
        os.environ.pop("WAYBACK_URL", None)

    def test_plain_url_in_inline_style_is_rewritten(self):
        """A plain http:// url() was previously left untouched."""
        html = (
            '<html><body><div style="background:url(http://example.com/bg.png)">'
            "</div></body></html>"
        )
        processed, _ = self.downloader._process_html(html, "http://example.com/")

        assert "http://example.com/bg.png" not in processed
        assert "url(bg.png)" in processed

    def test_plain_url_in_inline_style_is_queued_for_download(self):
        """The asset the style points at still gets fetched."""
        html = (
            '<html><body><div style="background:url(http://example.com/bg.png)">'
            "</div></body></html>"
        )
        _, links = self.downloader._process_html(html, "http://example.com/")

        assert "http://example.com/bg.png" in links

    def test_wayback_url_in_inline_style_still_rewritten(self):
        """The case the old hand-rolled patterns did handle must keep working."""
        html = (
            '<html><body><div style="background:url(https://web.archive.org/web/'
            '20250417203037im_/http://example.com/bg.png)"></div></body></html>'
        )
        processed, _ = self.downloader._process_html(html, "http://example.com/")

        assert "web.archive.org" not in processed
        assert "url(bg.png)" in processed

    def test_inline_style_matches_style_tag_handling(self):
        """The same declaration should rewrite the same way in both places."""
        inline = (
            '<html><body><div style="background:url(http://example.com/d/bg.png)">'
            "</div></body></html>"
        )
        block = (
            "<html><head><style>body{background:url(http://example.com/d/bg.png)}"
            "</style></head><body></body></html>"
        )
        inline_out, _ = self.downloader._process_html(inline, "http://example.com/")
        block_out, _ = self.downloader._process_html(block, "http://example.com/")

        assert "url(d/bg.png)" in inline_out
        assert "url(d/bg.png)" in block_out


class TestLinksArePercentEncoded:
    """On-disk names are decoded; the links pointing at them must not be."""

    def setup_method(self):
        """Set up test fixtures."""
        self.downloader = _make_downloader("/tmp/wayback-archive-fidelity")
        self.downloader._current_page_url = "http://example.com/"

    def teardown_method(self):
        """Clean up after tests."""
        os.environ.pop("WAYBACK_URL", None)

    @pytest.mark.parametrize(
        "url,filename,link",
        [
            # '#' would otherwise start a fragment and '?' a query string,
            # so the browser would request the wrong file entirely.
            ("http://example.com/a%23b.png", "a#b.png", "a%23b.png"),
            ("http://example.com/a%3Fb.png", "a?b.png", "a%3Fb.png"),
            ("http://example.com/img%20name.png", "img name.png", "img%20name.png"),
            ("http://example.com/caf%C3%A9.png", "café.png", "caf%C3%A9.png"),
        ],
    )
    def test_reserved_characters_are_escaped(self, url, filename, link):
        """The file keeps its real name and the link escapes it."""
        assert self.downloader._get_local_path(url).name == filename
        assert self.downloader._get_relative_link_path(url, "asset") == link

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/a%23b.png",
            "http://example.com/img%20name.png",
            "http://example.com/a%2fb.png",
            "http://example.com/caf%C3%A9.png",
            "http://example.com/plain.png",
        ],
    )
    def test_both_rewriters_agree(self, url):
        """HTML attributes and CSS url() must produce the same link."""
        assert self.downloader._get_relative_link_path(
            url, "asset"
        ) == self.downloader._make_relative_path(url)

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/a%23b.png",
            "http://example.com/img%20name.png",
            "http://example.com/a%2fb.png",
            "http://example.com/deep/caf%C3%A9.png",
            "http://example.com/a%2e%2e/escaped.png",
        ],
    )
    def test_link_decodes_back_to_the_written_file(self, url):
        """Decoding a link the way a browser does must find the real file."""
        link = self.downloader._get_relative_link_path(url, "asset")
        resolved = self.downloader._resolve_output_path(unquote(link))
        assert resolved == self.downloader._get_local_path(url)

    def test_query_and_fragment_are_not_escaped(self):
        """Only the path is escaped; a real query string stays a query string."""
        link = self.downloader._get_relative_link_path(
            "http://example.com/page?q=1#sec", "page"
        )
        assert link.endswith("?q=1#sec")


class TestStylesheetLinksAreRelativeToTheStylesheet:
    """A stylesheet's url() resolves against the stylesheet, not the last page."""

    def teardown_method(self):
        """Clean up after tests."""
        os.environ.pop("WAYBACK_URL", None)

    def test_css_url_points_at_the_real_asset(self, tmp_path):
        """The link must resolve from the .css file's own directory."""
        pages = {
            "http://example.com/": b"<html><head>"
            b'<link rel="stylesheet" href="http://example.com/assets/site.css">'
            b'</head><body><a href="http://example.com/blog/2024/hello/">p</a>'
            b"</body></html>",
            # A page nested several levels deep, archived before the stylesheet,
            # is what used to supply the wrong "from" directory.
            "http://example.com/blog/2024/hello/": b"<html><body>post</body></html>",
            "http://example.com/assets/site.css": (
                b"body{background:url(http://example.com/i/tile.png)}"
            ),
        }

        output_dir = tmp_path / "output"
        downloader = _make_downloader(output_dir)
        downloader.download_file = lambda url: pages.get(url, b"ASSET")
        with contextlib.redirect_stdout(io.StringIO()):
            downloader.download()

        css_file = output_dir / "assets" / "site.css"
        match = re.search(r"url\(([^)]+)\)", css_file.read_text("utf-8"))
        assert match, "stylesheet lost its url() reference"

        target = (css_file.parent / unquote(match.group(1))).resolve()
        assert target == (output_dir / "i" / "tile.png").resolve()
        assert target.exists()


class TestCdnAndFontLinksNameRealFiles:
    """Every branch of the path builders must agree with its link builder."""

    def setup_method(self):
        """Set up test fixtures."""
        self.downloader = _make_downloader("/tmp/wayback-archive-fidelity")
        self.downloader._current_page_url = "http://example.com/"

    def teardown_method(self):
        """Clean up after tests."""
        os.environ.pop("WAYBACK_URL", None)

    @pytest.mark.parametrize(
        "url",
        [
            # A CDN root is saved as index.html inside the domain folder; the
            # link used to name the folder instead.
            "https://images.squarespace-cdn.com/",
            "https://images.squarespace-cdn.com/content/v1/abc/a%20b.png",
            "https://static1.squarespace.com/static/file.js",
            "https://fonts.gstatic.com/s/mont/v29/f.woff2",
            "https://fonts.gstatic.com/s/mont/v29/a%20b.woff2",
        ],
    )
    def test_link_resolves_to_the_written_file(self, url):
        """Decoding the link must land on the file the downloader writes."""
        link = self.downloader._get_relative_link_path(url, "asset")
        resolved = self.downloader._resolve_output_path(unquote(link.split("?")[0]))
        assert resolved == self.downloader._get_local_path(url)


class TestEveryLinkNamesItsFile:
    """A sweep over URL shapes, because hand-picked fixtures kept missing cases.

    Each of the defects above was a disagreement between the code that decides
    where a file is written and the code that writes the link to it. This
    checks the whole matrix at once rather than one shape at a time.
    """

    PATHS = [
        "/", "/a", "/a/", "/a/b", "/a/b/", "/a/b/c.png", "/a/b/c.html",
        "/index.html", "/a//b", "/a//b//", "/deep/nest/ed/dir/",
        "/img%20name.png", "/a%23hash.png", "/a%3Fq.png", "/caf%C3%A9.png",
        "/100%25.png", "/a%2fb.png", "/a%5cb.png", "/%2e%2e/up.png",
        "/../up.png", "/a/../b.png", "/dot.dir/file", "/UPPER/Case.PNG",
        "/a+b.png", "/a&b.png", "/a=b.png", "/a,b.png", "/~tilde/x.png",
    ]

    PAGES = [
        "http://example.com/",
        "http://example.com/a/",
        "http://example.com/a/b/",
        "http://example.com/a/b/page.html",
    ]

    def setup_method(self):
        """Set up test fixtures."""
        self.downloader = _make_downloader("/tmp/wayback-archive-fidelity")

    def teardown_method(self):
        """Clean up after tests."""
        os.environ.pop("WAYBACK_URL", None)

    def test_every_link_resolves(self):
        """Resolve each link from its page's directory and land on the file.

        Both reference kinds are swept. The kind used to change the link
        without changing the file, which is how an extensionless asset ended
        up saved as image/12345.html and linked as image/12345.
        """
        mismatches = []
        for page in self.PAGES:
            self.downloader._current_page_url = page
            page_dir = os.path.dirname(str(self.downloader._get_local_path(page)))
            for path in self.PATHS:
                url = "http://example.com" + path
                local = self.downloader._get_local_path(url)
                for kind in ("page", "asset"):
                    link = self.downloader._get_relative_link_path(url, kind)
                    resolved = os.path.normpath(os.path.join(page_dir, unquote(link)))
                    if resolved != str(local):
                        mismatches.append(
                            f"from {page} -> {url} (kind={kind}): "
                            f"{link!r} gives {resolved}, file is {local}"
                        )

        assert not mismatches, "links that do not name their file:\n" + "\n".join(mismatches)

    def test_both_builders_stay_in_step(self):
        """The CSS builder and the HTML builder must not drift apart again."""
        self.downloader._current_page_url = "http://example.com/a/b/"
        for path in self.PATHS:
            url = "http://example.com" + path
            assert self.downloader._make_relative_path(
                url
            ) == self.downloader._get_relative_link_path(url, "asset"), url


class TestExtensionlessAssetsGetTheRightExtension:
    """A URL with no extension is named by how it was referenced.

    A stylesheet or script saved as .html is served as text/html, and a
    browser in standards mode refuses it. Images and media are sniffed, so
    those keep the historical .html rather than risk renaming files that
    already work.
    """

    def setup_method(self):
        """Set up test fixtures."""
        self.downloader = _make_downloader("/tmp/wayback-archive-fidelity")

    def teardown_method(self):
        """Clean up after tests."""
        os.environ.pop("WAYBACK_URL", None)

    @pytest.mark.parametrize(
        "kind,expected",
        [
            ("stylesheet", "css/main.css"),
            ("script", "css/main.js"),
            ("page", "css/main.html"),
            ("image", "css/main.html"),
            ("asset", "css/main.html"),
            (None, "css/main.html"),
        ],
    )
    def test_extension_follows_the_reference(self, kind, expected):
        """Only the MIME-critical kinds change the name."""
        path = self.downloader._get_local_path("http://example.com/css/main", kind)
        assert path == self.downloader._resolve_output_path(expected)

    def test_a_real_extension_is_never_overridden(self):
        """A URL that already names its type keeps that name."""
        path = self.downloader._get_local_path(
            "http://example.com/a/style.css", "script"
        )
        assert path == self.downloader._resolve_output_path("a/style.css")

    def test_the_first_reference_decides_and_later_lookups_agree(self):
        """The download loop resolves the same URL with no kind at all.

        If it got a different answer the link would name a file that was
        never written, which is the whole class of bug this guards.
        """
        url = "http://example.com/css/main"
        first = self.downloader._get_local_path(url, "stylesheet")
        assert self.downloader._get_local_path(url) == first
        assert self.downloader._get_local_path(url, "page") == first
        assert first.name == "main.css"


class TestExtensionlessAssetsEndToEnd:
    """The archived page must reference files that exist, with usable types."""

    def teardown_method(self):
        """Clean up after tests."""
        os.environ.pop("WAYBACK_URL", None)

    def test_stylesheet_and_script_land_on_their_own_extensions(self, tmp_path):
        """A whole archive of extensionless assets resolves and is typed."""
        page = (
            b"<html><head>"
            b'<link rel="stylesheet" href="http://example.com/css/main">'
            b"</head><body>"
            b'<img src="http://example.com/image/12345">'
            b'<script src="http://example.com/js/bundle"></script>'
            b"</body></html>"
        )

        def fake_download_file(url):
            """Serve each asset without touching the network."""
            if url == "http://example.com/":
                return page
            if "css" in url:
                return b"body{color:red}"
            if "js" in url:
                return b"var x=1;"
            return b"\x89PNG\r\n\x1a\n"

        output_dir = tmp_path / "output"
        downloader = _make_downloader(output_dir)
        downloader.download_file = fake_download_file
        with contextlib.redirect_stdout(io.StringIO()):
            downloader.download()

        written = {str(p.relative_to(output_dir)) for p in output_dir.rglob("*") if p.is_file()}
        assert "css/main.css" in written
        assert "js/bundle.js" in written

        index = (output_dir / "index.html").read_text("utf-8")
        references = re.findall(r'(?:href|src)=["\']?([^"\'>\s]+)', index)
        assert references, "the page lost its references"
        for reference in references:
            assert not reference.startswith("http"), f"{reference} still points at the live site"
            assert (output_dir / unquote(reference)).exists(), f"{reference} names no file"
