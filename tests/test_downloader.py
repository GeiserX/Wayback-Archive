"""Tests for downloader module."""

import os
import pytest
from unittest.mock import Mock, patch, MagicMock
from wayback_archive.config import Config
from wayback_archive.downloader import WaybackDownloader


class TestWaybackDownloader:
    """Test downloader class."""

    def setup_method(self):
        """Set up test fixtures."""
        os.environ["WAYBACK_URL"] = "https://web.archive.org/web/20250417203037/http://example.com/"
        self.config = Config()
        self.downloader = WaybackDownloader(self.config)

    def teardown_method(self):
        """Clean up after tests."""
        os.environ.pop("WAYBACK_URL", None)

    def test_parse_wayback_url(self):
        """Test Wayback URL parsing."""
        assert self.downloader.config.base_url == "http://example.com/"
        assert self.downloader.config.domain == "example.com"

    def test_is_internal_url(self):
        """Test internal URL detection."""
        assert self.downloader._is_internal_url("http://example.com/page") is True
        assert self.downloader._is_internal_url("http://www.example.com/page") is True
        assert self.downloader._is_internal_url("http://other.com/page") is False
        assert self.downloader._is_internal_url("/relative/page") is True

    def test_is_tracker(self):
        """Test tracker detection."""
        assert self.downloader._is_tracker("https://www.google-analytics.com/ga.js") is True
        assert self.downloader._is_tracker("https://example.com/script.js") is False

    def test_is_ad(self):
        """Test ad detection."""
        assert self.downloader._is_ad("https://ads.example.com/banner.jpg") is True
        assert self.downloader._is_ad("https://example.com/image.jpg") is False

    def test_is_contact_link(self):
        """Test contact link detection."""
        assert self.downloader._is_contact_link("mailto:test@example.com") is True
        assert self.downloader._is_contact_link("tel:+1234567890") is True
        assert self.downloader._is_contact_link("http://example.com") is False

    def test_convert_to_wayback_url(self):
        """Test Wayback URL conversion."""
        wayback_url = self.downloader._convert_to_wayback_url("http://example.com/page")
        assert "web.archive.org" in wayback_url
        assert "20250417203037" in wayback_url

    def test_normalize_url(self):
        """Test URL normalization."""
        # Test relative to absolute
        normalized = self.downloader._normalize_url("/page", "http://example.com/")
        assert normalized == "http://example.com/page"

        # Test www removal
        normalized = self.downloader._normalize_url("http://www.example.com/page", "http://example.com/")
        assert "www." not in normalized

    def test_make_relative_path(self):
        """Test relative path conversion."""
        path = self.downloader._make_relative_path("http://example.com/page.html")
        assert path == "/page.html"

    def test_get_local_path(self):
        """Test local path generation."""
        path = self.downloader._get_local_path("http://example.com/page.html")
        assert "page.html" in str(path)
        assert path.name == "page.html"

    @patch("wayback_archive.downloader.requests.Session.get")
    def test_download_file(self, mock_get):
        """Test file downloading."""
        mock_response = Mock()
        mock_response.content = b"test content"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        content = self.downloader.download_file("http://example.com/page")
        assert content == b"test content"

    def test_optimize_html(self):
        """Test HTML optimization."""
        html = "<html><body>  <p>Test</p>  </body></html>"
        optimized = self.downloader._optimize_html(html)
        assert len(optimized) <= len(html)

    def test_minify_js(self):
        """Test JavaScript minification."""
        js = """
        function test() {
            var x = 1;
            return x;
        }
        """
        minified = self.downloader._minify_js(js)
        assert len(minified) <= len(js)

    def test_minify_css(self):
        """Test CSS minification."""
        css = """
        body {
            margin: 0;
            padding: 0;
        }
        """
        minified = self.downloader._minify_css(css)
        assert len(minified) <= len(css)

