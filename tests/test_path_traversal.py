"""Regression tests for path traversal in URL-to-file-path resolution.

Archived pages are third-party content, so any ``..`` reaching the file
writer must stay inside ``OUTPUT_DIR``. GHSA-mw6m-6mxq-gmj5 (CVE pending)
covered the percent-encoded ``<img src>`` case; these tests pin every
traversal shape that reaches the same sink.
"""

import os
import pytest
from wayback_archive.config import Config
from wayback_archive.downloader import UnsafeOutputPathError, WaybackDownloader


class TestSanitizeOutputRelpath:
    """Test dot-segment removal on URL-derived paths."""

    def setup_method(self):
        """Set up test fixtures."""
        os.environ["WAYBACK_URL"] = (
            "https://web.archive.org/web/20250417203037/http://example.com/"
        )
        self.config = Config()
        self.downloader = WaybackDownloader(self.config)

    def teardown_method(self):
        """Clean up after tests."""
        os.environ.pop("WAYBACK_URL", None)

    @pytest.mark.parametrize(
        "raw,expected",
        [
            # Ordinary paths are untouched.
            ("a/b/c.png", "a/b/c.png"),
            ("/a/b/c.png", "a/b/c.png"),
            ("a//b.png", "a/b.png"),
            (".htaccess", ".htaccess"),
            ("img name.png", "img name.png"),
            ("v1.2.3/lib.js", "v1.2.3/lib.js"),
            # Dot segments collapse the way a web server resolves them.
            ("a/./b.png", "a/b.png"),
            ("a/../b.png", "b.png"),
            ("../escape.txt", "escape.txt"),
            ("../../../etc/passwd", "etc/passwd"),
            ("a/../../escape.txt", "escape.txt"),
            # Backslash is a separator on Windows, so it cannot survive whole.
            ("a\\..\\..\\escape.txt", "escape.txt"),
            # Windows trims trailing dots and spaces from a component.
            ("a/.. /escape.txt", "escape.txt"),
            ("a/../escape.txt", "escape.txt"),
            # Everything can collapse away entirely.
            ("..", ""),
            ("/", ""),
            ("", ""),
        ],
    )
    def test_sanitize(self, raw, expected):
        """Dot segments collapse without ever escaping the root."""
        assert self.downloader._sanitize_output_relpath(raw) == expected

    def test_nul_byte_is_stripped(self):
        """NUL cannot appear in a filename and must not reach open()."""
        assert self.downloader._sanitize_output_relpath("a\x00b.png") == "ab.png"


class TestResolveOutputPath:
    """Test the containment backstop around output_dir."""

    def setup_method(self):
        """Set up test fixtures."""
        os.environ["WAYBACK_URL"] = (
            "https://web.archive.org/web/20250417203037/http://example.com/"
        )
        self.config = Config()
        self.config.output_dir = "/tmp/wayback-archive-test-output"
        self.downloader = WaybackDownloader(self.config)

    def teardown_method(self):
        """Clean up after tests."""
        os.environ.pop("WAYBACK_URL", None)

    def test_benign_path_resolves_inside_output_dir(self):
        """A normal asset path lands where it always did."""
        resolved = self.downloader._resolve_output_path("a/b/c.png")
        assert str(resolved) == "/tmp/wayback-archive-test-output/a/b/c.png"

    @pytest.mark.parametrize(
        "escaping", ["../escape.txt", "a/../../escape.txt", "/etc/passwd"]
    )
    def test_backstop_rejects_escaping_path(self, escaping):
        """With sanitizing disabled, the containment check still refuses.

        This is the positive control for the guard: if the check could not
        fail, it would not be protecting anything.
        """
        self.downloader._sanitize_output_relpath = lambda path: path
        with pytest.raises(UnsafeOutputPathError):
            self.downloader._resolve_output_path(escaping)

    def test_backstop_allows_benign_path(self):
        """The containment check does not reject legitimate paths."""
        self.downloader._sanitize_output_relpath = lambda path: path
        resolved = self.downloader._resolve_output_path("a/b/c.png")
        assert str(resolved) == "/tmp/wayback-archive-test-output/a/b/c.png"


class TestGetLocalPathContainment:
    """Test that every _get_local_path branch stays inside output_dir."""

    def setup_method(self):
        """Set up test fixtures."""
        os.environ["WAYBACK_URL"] = (
            "https://web.archive.org/web/20250417203037/http://example.com/"
        )
        self.config = Config()
        self.config.output_dir = "/tmp/wayback-archive-test-output"
        self.downloader = WaybackDownloader(self.config)

    def teardown_method(self):
        """Clean up after tests."""
        os.environ.pop("WAYBACK_URL", None)

    @pytest.mark.parametrize(
        "url",
        [
            # The reported vector: percent-encoded traversal.
            "http://example.com/%2e%2e/outside.txt",
            "http://example.com/a/%2e%2e/%2e%2e/etc/evil.txt",
            # Plain traversal in an absolute URL is never normalized away.
            "http://example.com/../outside.txt",
            # Percent-encoded backslashes traverse on Windows.
            "http://example.com/a%5c..%5c..%5cevil.txt",
            # The Google Fonts branch builds its own path.
            "http://fonts.googleapis.com/../../evil.css",
            "http://fonts.gstatic.com/../../evil.woff2",
        ],
    )
    def test_traversal_stays_inside_output_dir(self, url):
        """No URL shape may resolve above the output directory."""
        local_path = self.downloader._get_local_path(url)
        root = os.path.realpath(self.config.output_dir)
        assert os.path.realpath(local_path).startswith(root + os.sep)

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("http://example.com/", "index.html"),
            ("http://example.com/a/b/c.png", "a/b/c.png"),
            ("http://example.com/blog/post", "blog/post.html"),
            ("http://example.com/img%20name.png", "img name.png"),
            (
                "http://fonts.gstatic.com/s/mont/v29/f.woff2",
                "fonts.gstatic.com/s/mont/v29/f.woff2",
            ),
        ],
    )
    def test_normal_urls_are_unchanged(self, url, expected):
        """Containment must not move files that were never a problem."""
        local_path = self.downloader._get_local_path(url)
        assert local_path == self.downloader._resolve_output_path(expected)

    @pytest.mark.parametrize(
        "url,link",
        [
            ("http://example.com/a/../b.png", "b.png"),
            # Before the fix this link pointed inside output while the file
            # itself was written above it.
            ("http://example.com/../outside.txt", "outside.txt"),
            ("http://example.com/%2e%2e/outside.txt", "outside.txt"),
        ],
    )
    def test_rewritten_link_matches_written_file(self, url, link):
        """A collapsed URL's link points at the file that gets written."""
        self.downloader._current_page_url = "http://example.com/"
        local_path = self.downloader._get_local_path(url)

        assert self.downloader._get_relative_link_path(url, is_page=False) == link
        # The link is relative to the root page, so resolving it against the
        # output root must land on the exact file the downloader writes.
        assert os.path.realpath(
            os.path.join(self.config.output_dir, link)
        ) == os.path.realpath(local_path)


class TestDownloadTraversalEndToEnd:
    """Reproduce GHSA-mw6m-6mxq-gmj5 through the real download() path."""

    def teardown_method(self):
        """Clean up after tests."""
        os.environ.pop("WAYBACK_URL", None)

    @pytest.mark.parametrize(
        "payload_path",
        ["%2e%2e/outside-marker.txt", "../outside-marker.txt"],
    )
    def test_img_src_traversal_cannot_write_outside_output_dir(
        self, tmp_path, payload_path
    ):
        """An <img src> traversal must not create a file outside OUTPUT_DIR."""
        output_dir = tmp_path / "output"
        outside = tmp_path / "outside-marker.txt"

        os.environ["WAYBACK_URL"] = (
            "https://web.archive.org/web/20250417203037/http://example.com/"
        )
        config = Config()
        config.output_dir = str(output_dir)
        config.max_files = 2

        downloader = WaybackDownloader(config)
        html = (
            '<html><body><img src="http://example.com/'
            f'{payload_path}"></body></html>'
        ).encode()

        def fake_download_file(url):
            """Serve the malicious page without touching the network."""
            if url == "http://example.com/":
                return html
            return b"TRAVERSAL-MARKER\n"

        downloader.download_file = fake_download_file
        downloader.download()

        assert not outside.exists(), "wrote outside OUTPUT_DIR"
        assert (output_dir / "outside-marker.txt").read_bytes() == b"TRAVERSAL-MARKER\n"
