"""Tests for configuration module."""

import os
import pytest
from wayback_archive.config import Config


class TestConfig:
    """Test configuration class."""

    def test_default_values(self):
        """Test default configuration values."""
        os.environ.pop("WAYBACK_URL", None)
        config = Config()
        
        assert config.optimize_html is True
        assert config.optimize_images is False
        assert config.minify_js is False
        assert config.minify_css is False
        assert config.remove_trackers is True
        assert config.remove_ads is True
        assert config.remove_external_links_keep_anchors is True
        assert config.remove_external_links_remove_anchors is False
        assert config.remove_clickable_contacts is True
        assert config.remove_external_iframes is False
        assert config.make_internal_links_relative is True
        assert config.make_non_www is True
        assert config.make_www is False
        assert config.keep_redirections is False
        assert config.output_dir == "./output"

    def test_env_variables(self):
        """Test environment variable parsing."""
        os.environ["WAYBACK_URL"] = "https://web.archive.org/web/20250417203037/http://example.com/"
        os.environ["OPTIMIZE_HTML"] = "false"
        os.environ["OPTIMIZE_IMAGES"] = "true"
        os.environ["MINIFY_JS"] = "true"
        os.environ["MINIFY_CSS"] = "true"
        os.environ["REMOVE_TRACKERS"] = "false"
        os.environ["OUTPUT_DIR"] = "/tmp/test"

        config = Config()

        assert config.wayback_url == "https://web.archive.org/web/20250417203037/http://example.com/"
        assert config.optimize_html is False
        assert config.optimize_images is True
        assert config.minify_js is True
        assert config.minify_css is True
        assert config.remove_trackers is False
        assert config.output_dir == "/tmp/test"

        # Cleanup
        os.environ.pop("WAYBACK_URL", None)
        os.environ.pop("OPTIMIZE_HTML", None)
        os.environ.pop("OPTIMIZE_IMAGES", None)
        os.environ.pop("MINIFY_JS", None)
        os.environ.pop("MINIFY_CSS", None)
        os.environ.pop("REMOVE_TRACKERS", None)
        os.environ.pop("OUTPUT_DIR", None)

    def test_validate_missing_url(self):
        """Test validation with missing URL."""
        os.environ.pop("WAYBACK_URL", None)
        config = Config()
        
        is_valid, error = config.validate()
        assert is_valid is False
        assert "WAYBACK_URL" in error

    def test_validate_with_url(self):
        """Test validation with URL."""
        os.environ["WAYBACK_URL"] = "https://web.archive.org/web/20250417203037/http://example.com/"
        config = Config()
        
        is_valid, error = config.validate()
        assert is_valid is True
        assert error is None

        # Cleanup
        os.environ.pop("WAYBACK_URL", None)

