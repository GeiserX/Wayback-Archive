"""Configuration management for Wayback-Archive."""

import math
import os

_TRUE = ("true", "1", "yes", "on")
_FALSE = ("false", "0", "no", "off")


def get_bool_env(key: str, default: bool = False) -> bool:
    """Get boolean environment variable."""
    value = os.getenv(key, "").lower()
    return value in ("true", "1", "yes", "on") if value else default


def get_str_env(key: str, default: str | None = None) -> str | None:
    """Get string environment variable."""
    return os.getenv(key, default)


class Config:
    """Configuration class for Wayback-Archive.

    Every option comes from, in order: an explicit override
    (Config(optimize_html=False), which is how the command-line flags and
    the Python API set it), the environment variable, then the default.
    An invalid value is collected in self.errors and reported by validate().
    """

    # The on/off options, set from BOOL_OPTIONS in __init__.
    optimize_html: bool
    optimize_images: bool
    minify_js: bool
    minify_css: bool
    remove_trackers: bool
    remove_ads: bool
    remove_clickable_contacts: bool
    remove_external_iframes: bool
    remove_external_links_keep_anchors: bool
    remove_external_links_remove_anchors: bool
    make_internal_links_relative: bool
    make_non_www: bool
    make_www: bool

    # (attribute, environment variable, default) of every on/off option.
    BOOL_OPTIONS = (
        ("optimize_html", "OPTIMIZE_HTML", False),  # opt-in: minifying drops spaces that render between inline elements
        ("optimize_images", "OPTIMIZE_IMAGES", False),
        ("minify_js", "MINIFY_JS", False),
        ("minify_css", "MINIFY_CSS", False),
        ("remove_trackers", "REMOVE_TRACKERS", True),
        ("remove_ads", "REMOVE_ADS", True),
        ("remove_clickable_contacts", "REMOVE_CLICKABLE_CONTACTS", True),
        ("remove_external_iframes", "REMOVE_EXTERNAL_IFRAMES", False),
        ("remove_external_links_keep_anchors", "REMOVE_EXTERNAL_LINKS_KEEP_ANCHORS", True),
        ("remove_external_links_remove_anchors", "REMOVE_EXTERNAL_LINKS_REMOVE_ANCHORS", False),
        ("make_internal_links_relative", "MAKE_INTERNAL_LINKS_RELATIVE", True),
        ("make_non_www", "MAKE_NON_WWW", True),
        ("make_www", "MAKE_WWW", False),
    )
    # (attribute, environment variable, default) of the other options.
    VALUE_OPTIONS = (
        ("wayback_url", "WAYBACK_URL", None),
        ("output_dir", "OUTPUT_DIR", "./output"),
        ("max_files", "MAX_FILES", None),
        ("request_delay", "REQUEST_DELAY", 0.0),
    )
    # Every environment variable Config reads.
    ENV_VARS = tuple(env for _, env, _ in BOOL_OPTIONS + VALUE_OPTIONS)

    def __init__(self, **overrides):
        known = {name for name, _, _ in self.BOOL_OPTIONS + self.VALUE_OPTIONS}
        unknown = sorted(set(overrides) - known)
        if unknown:
            raise TypeError(f"unknown option(s): {', '.join(unknown)}")
        self.errors: list[str] = []
        explicit = set()

        for name, env, default in self.BOOL_OPTIONS:
            value, label = self._raw(overrides, name, env)
            if value is None:
                setattr(self, name, default)
                continue
            explicit.add(name)
            if isinstance(value, bool):
                setattr(self, name, value)
                continue
            text = str(value).strip().lower()
            if text in _TRUE:
                setattr(self, name, True)
            elif text in _FALSE:
                setattr(self, name, False)
            else:
                setattr(self, name, default)
                self.errors.append(f"{label} must be one of true/false/1/0/yes/no/on/off, got {value!r}")

        if self.make_www:
            if self.make_non_www and "make_non_www" in explicit:
                self.errors.append("MAKE_WWW and MAKE_NON_WWW cannot both be true")
            # Asking for www means never stripping it; with the MAKE_NON_WWW
            # default still on, every host was flipped both ways.
            self.make_non_www = False

        # Required
        value, _ = self._raw(overrides, "wayback_url", "WAYBACK_URL")
        self.wayback_url: str | None = None if value is None else str(value)

        # Output
        value, _ = self._raw(overrides, "output_dir", "OUTPUT_DIR")
        self.output_dir: str = "./output" if value is None else str(value)

        # Download limit (for testing): how many files to try. Unset or
        # empty means unlimited; anything but a positive integer is an error.
        value, label = self._raw(overrides, "max_files", "MAX_FILES")
        self.max_files: int | None = None
        if value is not None:
            text = str(value).strip()
            if not isinstance(value, bool) and text.isascii() and text.isdigit() and int(text) > 0:
                self.max_files = int(text)
            else:
                self.errors.append(f"{label} must be a positive whole number, got {value!r}")

        # Seconds to wait between requests to the Wayback Machine.
        value, label = self._raw(overrides, "request_delay", "REQUEST_DELAY")
        self.request_delay: float = 0.0
        if value is not None:
            try:
                delay = float(str(value).strip())
            except ValueError:
                delay = -1.0
            if isinstance(value, bool) or not math.isfinite(delay) or delay < 0:
                self.errors.append(f"{label} must be a number of seconds, 0 or more, got {value!r}")
            else:
                self.request_delay = delay

        # Internal state
        self.base_url: str | None = None
        self.domain: str | None = None
        self.visited_urls: set = set()
        self.downloaded_files: dict = {}  # URL -> local path mapping

    @staticmethod
    def _raw(overrides: dict, name: str, env: str):
        """The value an option was given and what to call it in an error: the
        override when there is one, else the environment variable. None or a
        blank string means not given, so the default applies."""
        for value, label in ((overrides.get(name), name), (os.getenv(env), env)):
            if value is not None and str(value).strip():
                return value, label
        return None, env

    def validate(self) -> tuple[bool, str | None]:
        """Validate configuration."""
        if not self.wayback_url:
            return False, "a Wayback URL is required: pass it as the first argument or set WAYBACK_URL"
        if self.errors:
            return False, self.errors[0]
        return True, None

    def __repr__(self) -> str:
        """String representation of config."""
        return f"Config(wayback_url={self.wayback_url}, output_dir={self.output_dir})"
