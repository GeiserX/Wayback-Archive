"""Regression tests for archives that did not faithfully reproduce the site.

Three defects lived here, all invisible because nothing asserted the *whole*
path or the *whole* rewritten document:

* every ``/section/`` page was written to the root ``index.html``, so a site
  archived down to a single file;
* inline ``style="...url(...)"`` was only rewritten for Wayback-form URLs, so a
  plain one stayed pointed at the live site;
* rewritten links were not percent-encoded, so a file named ``a#b.png`` was
  linked as a fragment.
"""

import io
import contextlib
import os
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
        link = self.downloader._get_relative_link_path(url, is_page=True)
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
        assert self.downloader._get_relative_link_path(url, is_page=False) == link

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
            url, is_page=False
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
        link = self.downloader._get_relative_link_path(url, is_page=False)
        resolved = self.downloader._resolve_output_path(unquote(link))
        assert resolved == self.downloader._get_local_path(url)

    def test_query_and_fragment_are_not_escaped(self):
        """Only the path is escaped; a real query string stays a query string."""
        link = self.downloader._get_relative_link_path(
            "http://example.com/page?q=1#sec", is_page=True
        )
        assert link.endswith("?q=1#sec")
