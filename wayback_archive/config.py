"""Configuration management for Wayback-Archive."""

import os
from typing import Optional, Tuple
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def get_bool_env(key: str, default: bool = False) -> bool:
    """Get boolean environment variable."""
    value = os.getenv(key, "").lower()
    return value in ("true", "1", "yes", "on") if value else default


def get_str_env(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get string environment variable."""
    return os.getenv(key, default)


class Config:
    """Configuration class for Wayback-Archive."""

    def __init__(self):
        # Required
        self.wayback_url: Optional[str] = get_str_env("WAYBACK_URL")

        # Output
        self.output_dir: str = get_str_env("OUTPUT_DIR", "./output")

        # HTML optimization
        self.optimize_html: bool = get_bool_env("OPTIMIZE_HTML", True)

        # Image optimization
        self.optimize_images: bool = get_bool_env("OPTIMIZE_IMAGES", False)

        # Minification
        self.minify_js: bool = get_bool_env("MINIFY_JS", False)
        self.minify_css: bool = get_bool_env("MINIFY_CSS", False)

        # Content removal
        self.remove_trackers: bool = get_bool_env("REMOVE_TRACKERS", True)
        self.remove_ads: bool = get_bool_env("REMOVE_ADS", True)
        self.remove_clickable_contacts: bool = get_bool_env("REMOVE_CLICKABLE_CONTACTS", True)
        self.remove_external_iframes: bool = get_bool_env("REMOVE_EXTERNAL_IFRAMES", False)

        # External links handling
        self.remove_external_links_keep_anchors: bool = get_bool_env(
            "REMOVE_EXTERNAL_LINKS_KEEP_ANCHORS", True
        )
        self.remove_external_links_remove_anchors: bool = get_bool_env(
            "REMOVE_EXTERNAL_LINKS_REMOVE_ANCHORS", False
        )

        # Link conversion
        self.make_internal_links_relative: bool = get_bool_env("MAKE_INTERNAL_LINKS_RELATIVE", True)
        self.make_non_www: bool = get_bool_env("MAKE_NON_WWW", True)
        self.make_www: bool = get_bool_env("MAKE_WWW", False)

        # Redirections
        self.keep_redirections: bool = get_bool_env("KEEP_REDIRECTIONS", False)

        # Download limit (for testing - set MAX_FILES to limit downloads)
        max_files_str = get_str_env("MAX_FILES")
        self.max_files: Optional[int] = int(max_files_str) if max_files_str and max_files_str.isdigit() else None

        # Internal state
        self.base_url: Optional[str] = None
        self.domain: Optional[str] = None
        self.visited_urls: set = set()
        self.downloaded_files: dict = {}  # URL -> local path mapping

    def validate(self) -> tuple[bool, Optional[str]]:
        """Validate configuration."""
        if not self.wayback_url:
            return False, "WAYBACK_URL environment variable is required"
        return True, None

    def __repr__(self) -> str:
        """String representation of config."""
        return f"Config(wayback_url={self.wayback_url}, output_dir={self.output_dir})"

