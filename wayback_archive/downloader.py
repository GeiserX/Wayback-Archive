"""Core downloader module for Wayback-Archive."""

import codecs
import hashlib
import os
import posixpath
import re
import sys
import mimetypes
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, unquote, quote
from pathlib import Path
from typing import Optional, Set, Dict, List, Tuple
import requests
from requests.adapters import HTTPAdapter
from urllib3.exceptions import MaxRetryError
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup, Comment
from bs4.dammit import EncodingDetector
from wayback_archive.config import Config


class UnsafeOutputPathError(ValueError):
    """Raised when a downloaded URL would be written outside OUTPUT_DIR."""


def _host_matches(url: str, hosts) -> bool:
    """True when the URL's host is one of hosts or a subdomain of one.

    A URL with userinfo never matches: "trusted.host@elsewhere" connects to
    the host after the "@".
    """
    parsed = urlparse(url)
    if "@" in parsed.netloc:
        return False
    host = (parsed.hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in hosts)


class _PoliteRetry(Retry):
    """Waits out a 429 as Retry-After asks, but never longer than RETRY_AFTER_MAX."""

    RETRY_AFTER_MAX = 30
    # urllib3 also retries a 503 or 413 that carries Retry-After by default.
    RETRY_AFTER_STATUS_CODES = frozenset({429})

    def get_retry_after(self, response):
        retry_after = super().get_retry_after(response)
        return None if retry_after is None else min(retry_after, self.RETRY_AFTER_MAX)

    def increment(self, method=None, url=None, response=None, error=None, _pool=None, _stacktrace=None):
        # A 429 with memento-datetime is an archived capture, not throttling;
        # MaxRetryError makes urllib3 hand it back without retrying.
        if response is not None and response.headers.get("memento-datetime"):
            raise MaxRetryError(_pool, url, "archived capture")
        return super().increment(method, url, response, error, _pool, _stacktrace)


class WaybackDownloader:
    """Main downloader class for Wayback Machine archives."""

    # Google Fonts hosts: the stylesheet host and the font file host.
    GOOGLE_FONTS_CSS_HOSTS = ("fonts.googleapis.com",)
    GOOGLE_FONT_HOSTS = GOOGLE_FONTS_CSS_HOSTS + ("fonts.gstatic.com",)

    SQUARESPACE_CDN_HOSTS = (
        "static1.squarespace.com",
        "static.squarespace.com",
        "images.squarespace-cdn.com",
        "definitions.sqspcdn.com",
        "sqspcdn.com",
    )

    # The only hosts ever fetched from the live Internet, when Wayback does
    # not have the file. The archived site's own domain is never on it: it may
    # belong to someone else today, and what it serves now is not the archive.
    LIVE_FALLBACK_HOSTS = GOOGLE_FONT_HOSTS + ("code.jquery.com",) + SQUARESPACE_CDN_HOSTS

    # Trackers and ads are recognised by host and exact file name only, and
    # never on the archived site's own host: a word anywhere in the URL
    # (banner, popup, "ads." in threads.png) deleted the site's own files.
    # A host matches itself and its subdomains.
    TRACKER_HOSTS = (
        "google-analytics.com",
        "googletagmanager.com",
        "tagmanager.google.com",
        "facebook.net",
        "doubleclick.net",
        "googlesyndication.com",
    )
    # A host whose own name starts with one of these labels
    # (stats.wp.com, analytics.example.net).
    TRACKER_HOST_LABELS = ("analytics", "stats", "tracking")
    TRACKER_FILES = ("gtag.js", "ga.js", "analytics.js", "urchin.js")
    # Markers of the Google Analytics / Tag Manager snippets in inline code.
    TRACKER_INLINE_MARKERS = (
        "gtag('config'",
        'gtag("config"',
        "googletagmanager.com/gtm.js",
        "googleanalyticsobject",
        "_gaq.push",
    )

    AD_HOSTS = (
        "advertising.com",
        "doubleclick.net",
        "googlesyndication.com",
        "googleadservices.com",
    )
    AD_HOST_LABELS = ("ads", "adserver", "googleads")

    # Contact link patterns
    CONTACT_PATTERNS = [
        r"^mailto:",
        r"^tel:",
        r"^sms:",
        r"^whatsapp:",
        r"^callto:",
    ]

    # Extension to give a URL that carries none, chosen by how it was
    # referenced. A stylesheet or a script has to land on the right extension
    # or a web server sends the wrong Content-Type and the browser refuses
    # the file. Anything else keeps the historical .html: browsers sniff
    # images and media regardless, and guessing wrong there would rename
    # files that work today.
    EXTENSION_FOR_KIND = {
        "stylesheet": ".css",
        "script": ".js",
    }
    DEFAULT_EXTENSION = ".html"

    # Server-side page extensions. The archived file is the HTML the script
    # produced, so it is fetched as a page and stored with .html appended
    # (index.php -> index.php.html): a static server then sends it as HTML,
    # and /index.php can sit next to an /index.php/ directory.
    PAGE_EXTENSIONS = frozenset(
        {".php", ".asp", ".aspx", ".jsp", ".cfm", ".cgi", ".pl", ".shtml", ".phtml"}
    )

    # References that name no file to fetch.
    NON_FETCHABLE_PREFIXES = (
        "data:", "javascript:", "vbscript:", "mailto:", "tel:", "sms:",
        "whatsapp:", "callto:", "about:", "blob:",
    )

    def __init__(self, config: Config):
        """Initialize downloader with configuration."""
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
        # Wayback throttles with 429: wait and retry a few times. A 5xx, or
        # an archived 429, is not retried, since Wayback replays archived
        # error captures as such.
        self.session.mount("https://web.archive.org/", HTTPAdapter(max_retries=_PoliteRetry(
            total=3, connect=0, read=0, other=0, status_forcelist=[429],
            backoff_factor=2, respect_retry_after_header=True, raise_on_status=False,
        )))
        # Why the last download_file call failed when Wayback refused it:
        # "throttled" (429) or "connection" (no answer); None otherwise.
        self._last_failure: Optional[str] = None
        # Track corrupted font files (HTML error pages instead of actual fonts)
        self.corrupted_fonts: Set[str] = set()
        # Font URLs already probed this run, so each is fetched at most once
        # however many stylesheets name it.
        self._probed_fonts: Set[str] = set()
        # How each stored path was first referenced, so the extension a URL
        # gets is decided once and every later lookup agrees with it.
        self._path_kinds: Dict[str, str] = {}
        # The same answer keyed by the file finally written, so the download
        # loop can tell a stylesheet from a page when the URL cannot.
        self._kind_by_path: Dict[str, str] = {}
        # Charset named by the last response download_file read.
        self._last_charset: Optional[str] = None
        # The URL that response finally came from, after redirects.
        self._last_final_url: Optional[str] = None
        # CDX lookups for bad captures: how many this run, and how many
        # failed in a row. CDX is slow and often down, so both are capped.
        self._cdx_lookups = 0
        self._cdx_failures = 0
        self._parse_wayback_url()

    def _parse_wayback_url(self):
        """Parse the Wayback Machine URL to extract the original URL."""
        # Extract timestamp and URL from Wayback URL
        # Format: https://web.archive.org/web/TIMESTAMP[modifier_]/URL, where
        # the modifier is a replay mode such as if_ or id_ and archive.org is
        # an alias of web.archive.org.
        match = re.match(
            r"https?://(?:web\.)?archive\.org(?::(?:80|443))?/web/(\d+)(?:[a-z]+_?)?/(.+)",
            self.config.wayback_url,
        )
        if match:
            timestamp, original_url = match.groups()
            # Ensure original_url starts with http/https
            if not original_url.startswith(("http://", "https://")):
                original_url = "http://" + original_url
            # An explicit default port names the same site; keeping it made
            # every port-less link on the site look external.
            parsed_original = urlparse(original_url)
            netloc = self._strip_default_port(parsed_original.netloc, parsed_original.scheme)
            original_url = parsed_original._replace(netloc=netloc).geturl()
            self.config.base_url = original_url
            self.config.domain = netloc
            # Store original timestamp for timeframe fallback
            self.original_timestamp = timestamp
            # Parse timestamp to datetime for timeframe calculations. A short
            # timestamp (a year, a year and month) is valid Wayback input and
            # means the start of that period, so pad it with the earliest
            # valid month, day and time rather than zeros.
            padded = timestamp[:14] + "00000101000000"[len(timestamp[:14]):]
            try:
                if len(timestamp) < 4:
                    raise ValueError(timestamp)
                self.original_datetime = datetime.strptime(padded, '%Y%m%d%H%M%S')
            except ValueError:
                # Not a date (/web/2/, /web/99999999999999/): Wayback serves
                # the latest capture, so search around now.
                self.original_datetime = datetime.now()
        else:
            raise ValueError(
                "WAYBACK_URL must look like https://web.archive.org/web/<timestamp>/<url>, "
                f"got: {self.config.wayback_url}"
            )

    @staticmethod
    def _strip_default_port(netloc: str, scheme: str) -> str:
        """Drop :80 from an http netloc and :443 from an https one."""
        default = {"http": ":80", "https": ":443"}.get((scheme or "").lower())
        if default and netloc.endswith(default):
            return netloc[: -len(default)]
        return netloc

    def _is_internal_url(self, url: str) -> bool:
        """Check if URL is internal to the site.
        
        Returns False for special schemes (tel:, mailto:, javascript:, etc.)
        """
        # Skip special URL schemes that shouldn't be downloaded
        non_downloadable_schemes = (
            'tel:', 'mailto:', 'javascript:', 'data:', 
            'ftp:', 'file:', 'sms:', 'whatsapp:', '#'
        )
        url_lower = url.lower().strip()
        if url_lower.startswith(non_downloadable_schemes) or url_lower == '#':
            return False
        
        parsed = urlparse(url)
        
        # Also check the parsed scheme
        if parsed.scheme and parsed.scheme.lower() not in ('http', 'https', ''):
            return False
        
        url_domain = self._strip_default_port(parsed.netloc.lower(), parsed.scheme).removeprefix("www.")
        base_domain = self.config.domain.lower().removeprefix("www.")

        # Treat Squarespace CDN as internal so we rewrite and download those assets.
        if self._is_squarespace_cdn(url):
            return True

        return url_domain == base_domain or url_domain == ""

    def _is_squarespace_cdn(self, url: str) -> bool:
        """Check if URL is from Squarespace CDN (should be downloaded)."""
        return _host_matches(url, self.SQUARESPACE_CDN_HOSTS)

    def _is_google_fonts_css(self, url: str) -> bool:
        """Check if URL is a Google Fonts stylesheet (css?family=, css2?family=)."""
        return _host_matches(url, self.GOOGLE_FONTS_CSS_HOSTS) and "/css" in urlparse(url).path

    @staticmethod
    def _is_html_url(url: str, parsed=None) -> bool:
        """Determine if a URL likely points to an HTML page based on its path."""
        if parsed is None:
            parsed = urlparse(url)
        path_lower = parsed.path.lower()
        if not path_lower or path_lower == "/":
            return True
        if path_lower.endswith('.html') or path_lower.endswith('.htm'):
            return True
        ext = os.path.splitext(path_lower)[1]
        if ext in WaybackDownloader.PAGE_EXTENSIONS:
            return True
        if ext:
            return False
        non_html = {'.css', '.js', '.jpg', '.jpeg', '.png', '.gif', '.svg',
                    '.woff', '.woff2', '.ttf', '.eot', '.otf', '.ico',
                    '.json', '.xml', '.txt', '.pdf'}
        return not any(path_lower.endswith(e) for e in non_html)

    def _third_party_parts(self, url: str) -> Optional[Tuple[str, str]]:
        """(host, path) of a URL on another host, None for the site's own."""
        url = self._extract_original_url_from_path(url) or url
        parsed = urlparse("https:" + url if url.startswith("//") else url)
        host = (parsed.hostname or "").lower()
        if not host or host.removeprefix("www.") == (self.config.domain or "").lower().removeprefix("www."):
            return None
        return host, parsed.path

    def _matches_blocklist(self, url: str, hosts, labels, files=()) -> bool:
        parts = self._third_party_parts(url)
        if not parts:
            return False
        host, path = parts
        return (
            any(host == h or host.endswith("." + h) for h in hosts)
            or host.split(".")[0] in labels
            or posixpath.basename(path).lower() in files
        )

    def _is_tracker(self, url: str) -> bool:
        """Check if URL is a tracker/analytics script."""
        parts = self._third_party_parts(url)
        if parts and _host_matches("https://" + parts[0], ("facebook.com",)) and parts[1].rstrip("/") == "/tr":
            return True
        return self._matches_blocklist(url, self.TRACKER_HOSTS, self.TRACKER_HOST_LABELS, self.TRACKER_FILES)

    def _is_ad(self, url: str) -> bool:
        """Check if URL is an ad."""
        return self._matches_blocklist(url, self.AD_HOSTS, self.AD_HOST_LABELS)

    # One URL and nothing else: no whitespace, no JSON or script punctuation.
    _SINGLE_URL = re.compile(r"[^\s{}\[\]\"'<>;]+")

    def _is_single_url_attr(self, attr_name: str, value: str) -> bool:
        """
        True when an attribute value is plainly one URL.

        The catch-all passes used to rewrite any value that mentioned the
        site, which turned JSON settings, inline handlers and meta refresh
        content into a percent-encoded file name.
        """
        if attr_name.startswith("on") or attr_name in ("style", "srcset", "imagesrcset"):
            return False
        value = value.strip()
        return bool(self._SINGLE_URL.fullmatch(value)) and value.startswith(("http://", "https://", "/"))

    def _is_contact_link(self, url: str) -> bool:
        """Check if URL is a contact link."""
        for pattern in self.CONTACT_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False

    def _convert_to_wayback_url(self, url: str) -> str:
        """Convert a regular URL to a Wayback Machine URL.
        
        This method is kept for backward compatibility.
        For timeframe fallback, use _convert_to_wayback_url_with_timestamp().
        """
        return self._convert_to_wayback_url_with_timestamp(url)
    
    def _referenced_kind(self, url: str) -> Optional[str]:
        """
        What a URL was referenced as, if anything recorded it.

        Args:
            url: The URL about to be fetched.

        Returns:
            "stylesheet", "script", ... or None when nothing referenced it.
        """
        try:
            return self._kind_by_path.get(str(self._get_local_path(url)))
        except UnsafeOutputPathError:
            return None

    def _convert_to_wayback_url_with_timestamp(self, url: str, timestamp: str = None, use_iframe: bool = False) -> str:
        """Convert a regular URL to a Wayback Machine URL with optional timestamp.
        
        Args:
            url: The original URL
            timestamp: Optional timestamp (YYYYMMDDHHMMSS). If None, uses original timestamp.
            use_iframe: If True, use 'if_' prefix to get unwrapped HTML content (no Wayback interface)
        """
        parsed = urlparse(url)
        if (
            parsed.scheme in ("http", "https")
            and parsed.hostname == "web.archive.org"
            and "@" not in parsed.netloc
        ):
            return url
        
        if timestamp is None:
            timestamp = self.original_timestamp
        
        # For HTML pages, use 'if_' prefix to get unwrapped content (no Wayback interface)
        if use_iframe:
            return f"https://web.archive.org/web/{timestamp}if_/{url}"
        
        # Determine asset type prefix (im_, cs_, js_)
        path = parsed.path.lower()
        asset_prefix = ""

        # A URL with no extension gives the guesses below nothing to work
        # with, so Wayback serves its wrapped replay page instead of the raw
        # file. The element that referenced it knows better.
        # Compare the real extension: a substring test gave news.jsp js_.
        ext = os.path.splitext(os.path.basename(path))[1]
        if not ext or ext in self.PAGE_EXTENSIONS:
            prefix_for_kind = {"stylesheet": "cs_", "script": "js_", "image": "im_"}
            asset_prefix = prefix_for_kind.get(self._referenced_kind(url) or "", "")
            if asset_prefix:
                return f"https://web.archive.org/web/{timestamp}{asset_prefix}/{url}"

        if ext in (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp"):
            asset_prefix = "im_"
        elif ext in (".woff", ".woff2", ".ttf", ".eot", ".otf"):
            # Font files also use im_ prefix in Wayback Machine
            asset_prefix = "im_"
        elif ext == ".css":
            asset_prefix = "cs_"
        elif ext in (".js", ".mjs"):
            asset_prefix = "js_"
        
        if asset_prefix:
            return f"https://web.archive.org/web/{timestamp}{asset_prefix}/{url}"
        return f"https://web.archive.org/web/{timestamp}/{url}"

    def _make_relative_path(self, url: str, kind: str = "asset") -> str:
        """Convert absolute URL to relative path."""
        # CSS url() and data-* attributes point at the same files as HTML
        # attributes do, so they go through the same builder.
        return self._get_relative_link_path(url, kind)

    def _extract_original_url_from_path(self, path: str) -> Optional[str]:
        """Extract original URL from Wayback Machine path in HTML."""
        if not path or not isinstance(path, str):
            return None
        
        try:
            # Handle protocol-relative URLs: //web.archive.org/web/...
            if path.startswith("//"):
                path = "https:" + path
            
            # Pattern: /web/TIMESTAMP/https://original.com/path and replay variants
            # such as im_, cs_, js_, jm_, if_, and fw_.
            wayback_url_pattern = r"(?:https?://web\.archive\.org)?/web/\d+(?:[a-z]+_)?/(https?://[^\"\s'<>\)]+)"
            match = re.search(wayback_url_pattern, path)
            if match:
                extracted = match.group(1)
                extracted = extracted.rstrip('.,;:)\'"')
                return extracted
            
            # Pattern for mailto:/tel:/whatsapp: in wayback URLs
            # Handle both /web/... and https://web.archive.org/web/...
            wayback_protocol_pattern = r"(?:https?://web\.archive\.org)?/web/\d+[a-z]*/(mailto:|tel:|whatsapp:|sms:|callto:)(.+)"
            match = re.search(wayback_protocol_pattern, path)
            if match:
                protocol = match.group(1)
                rest = match.group(2).split("?")[0].split("&")[0]  # Remove query params
                return protocol + rest
        except Exception as e:
            # Silently fail - return None if extraction fails
            pass
        
        return None

    def _normalize_url(self, url: str, base_url: str) -> str:
        """Normalize URL and handle www/non-www conversion."""
        # data:, mailto: and the like are not addresses on any host; joining
        # them onto the page turned data:image/png;... into a local path.
        if url.strip().lower().startswith(self.NON_FETCHABLE_PREFIXES):
            return url
        # Extract original URL from wayback paths first (handles both absolute and relative)
        original = self._extract_original_url_from_path(url)
        if original:
            url = original
        # Handle relative URLs (but not wayback paths - those should have been extracted above)
        elif not url.startswith(("http://", "https://", "//")):
            # Check if it's a relative wayback path
            if url.startswith("/web/"):
                # Try to construct full URL first
                full_url = urljoin(base_url, url)
                original = self._extract_original_url_from_path(full_url)
                if original:
                    url = original
                else:
                    url = full_url
            else:
                url = urljoin(base_url, url)

        # Handle protocol-relative URLs
        # Use the scheme from base_url to preserve http/https consistency
        if url.startswith("//"):
            parsed_base = urlparse(base_url)
            scheme = parsed_base.scheme if parsed_base.scheme else "http"
            url = f"{scheme}:{url}"

        parsed = urlparse(url)
        parsed_base = urlparse(base_url)
        
        # For internal URLs, preserve the scheme from base_url to ensure consistency
        # This prevents http:// URLs from being converted to https://
        url_domain = self._strip_default_port(parsed.netloc.lower(), parsed.scheme).removeprefix("www.")
        base_domain = parsed_base.netloc.lower().removeprefix("www.")
        if url_domain == base_domain or url_domain == "":
            # Internal URL - use base_url scheme. Its default port goes with
            # the old scheme: http://site:80 is not https://site:80.
            if parsed_base.scheme and parsed.scheme != parsed_base.scheme:
                parsed = parsed._replace(
                    scheme=parsed_base.scheme,
                    netloc=self._strip_default_port(parsed.netloc, parsed.scheme),
                )

        # Handle www/non-www conversion
        if self.config.make_non_www and parsed.netloc.startswith("www."):
            parsed = parsed._replace(netloc=parsed.netloc[4:])
        elif self.config.make_www and not parsed.netloc.startswith("www.") and parsed.netloc:
            parsed = parsed._replace(netloc="www." + parsed.netloc)

        # Remove fragment and query string for file identification
        # This ensures URLs with different query params or fragments point to the same file
        # Preserve query string for asset URLs (e.g., format params on images)
        # but always drop fragments.
        url_normalized = parsed._replace(fragment="").geturl()

        return url_normalized

    # Path separators to split on. Backslash is included because Windows
    # resolves it as a separator, so a percent-decoded "\\" must not survive
    # inside a single path component.
    _PATH_SEPARATORS = re.compile(r"[/\\]")

    def _sanitize_output_relpath(self, path: str) -> str:
        """
        Collapse a URL-derived path into a safe path relative to output_dir.

        Archived pages are third-party content we do not control, so their
        URLs can contain "." and ".." segments - plain or percent-encoded -
        that would otherwise make the downloader write outside OUTPUT_DIR.
        This applies the same dot-segment removal a web server performs
        before serving a file (RFC 3986 section 5.2.4): "a/../b" becomes "b",
        and a ".." that would climb above the root is dropped.

        Args:
            path: A percent-decoded URL path, or a "domain/path" string.

        Returns:
            A relative path using "/" separators that cannot escape upwards.
        """
        # A drive letter or UNC prefix would make the later join absolute on
        # Windows. splitdrive is a no-op on POSIX.
        path = os.path.splitdrive(path)[1]

        segments: List[str] = []
        for segment in self._PATH_SEPARATORS.split(path):
            # NUL is not writable in a filename and would raise on open().
            segment = segment.replace("\x00", "")

            # Windows silently trims trailing dots and spaces from a path
            # component, so "..", ".. " and "..." all address the parent
            # there. Treat any dots-and-spaces-only component as a relative
            # reference rather than a real directory name.
            if not segment.strip(" ."):
                if ".." in segment and segments:
                    segments.pop()
                continue

            segments.append(segment)

        return "/".join(segments)

    def _encode_link_path(self, path: str) -> str:
        """
        Percent-encode a decoded path so it is a valid URL reference.

        On-disk paths are decoded; the links pointing at them must not be. A
        file named "a#b.png" written into a link verbatim makes the browser
        read "#b.png" as a fragment and fetch "a" instead, and "?" starts a
        query string the same way. Encoding fixes both, and the browser
        decodes it straight back to the real filename.

        Args:
            path: A decoded path, using "/" separators.

        Returns:
            The same path with reserved and non-ASCII characters escaped.
        """
        return quote(path, safe="/")

    def _note_reference_kind(self, url: str, kind: str) -> None:
        """
        Record what a URL is, whether or not its link gets rewritten.

        With make_internal_links_relative off nothing calls the link builder,
        so without this the download loop meets an extensionless stylesheet
        with no context, treats it as a page, and rewrites the CSS as HTML.

        Args:
            url: The normalized URL of the referenced resource.
            kind: "stylesheet", "script", ...
        """
        try:
            self._get_local_path(url, kind)
        except UnsafeOutputPathError:
            # The download loop will refuse this URL as well; nothing to note.
            pass

    def _place_in_output(
        self, path: str, kind: Optional[str], default_extension: str
    ) -> Path:
        """
        Resolve a URL-derived path inside output_dir, naming it by its kind.

        A path with no file extension gets one chosen by how the URL was
        first referenced, and that choice is remembered: the download loop
        resolves the same URL again with no context, and both answers have
        to name the same file.

        Args:
            path: Relative path derived from the URL.
            kind: How the URL was referenced, or None where not known.
            default_extension: Used when the kind says nothing - ".html" for
                site paths, "" for CDN paths that are stored verbatim.

        Returns:
            A path inside output_dir.
        """
        name = os.path.basename(path)
        if "." in name and os.path.splitext(name)[1].lower() not in self.PAGE_EXTENSIONS:
            return self._resolve_output_path(path)

        if kind and path not in self._path_kinds:
            self._path_kinds[path] = kind
        resolved_kind = self._path_kinds.get(path) or kind or ""
        extension = self.EXTENSION_FOR_KIND.get(resolved_kind, default_extension)

        if extension:
            directory = os.path.dirname(path)
            base = os.path.basename(path) or "index"
            path = os.path.join(directory, base + extension) if directory else base + extension

        resolved = self._resolve_output_path(path)
        if resolved_kind:
            self._kind_by_path[str(resolved)] = resolved_kind
        return resolved

    def _resolve_output_path(self, relative_path: str) -> Path:
        """
        Join a URL-derived path onto output_dir, guaranteeing containment.

        Args:
            relative_path: Path fragment derived from a downloaded URL.

        Returns:
            A path inside output_dir.

        Raises:
            UnsafeOutputPathError: If the result would land outside
                output_dir. _sanitize_output_relpath makes this unreachable
                for normal input; it is the backstop that keeps any future
                or platform-specific gap from becoming an arbitrary write.
        """
        output_dir = Path(self.config.output_dir)
        candidate = output_dir / self._sanitize_output_relpath(relative_path)

        root = os.path.realpath(output_dir)
        resolved = os.path.realpath(candidate)
        if resolved != root and not resolved.startswith(root + os.sep):
            raise UnsafeOutputPathError(
                f"refusing to write outside output directory: {candidate}"
            )

        return candidate

    def _get_local_path(self, url: str, kind: Optional[str] = None) -> Path:
        """
        Get local file path for a URL.
        This ensures consistent file naming that works with static file servers.
        Files are saved without query strings or fragments for clean URLs.

        Args:
            url: The URL to place on disk.
            kind: How the URL was referenced ("stylesheet", "script", "page",
                  ...). Only used to pick an extension for a URL that has
                  none. The first kind seen for a path wins, because the
                  download loop resolves the same URL again with no context
                  and both answers have to name the same file.

        Raises:
            UnsafeOutputPathError: If the URL resolves outside output_dir.
        """
        parsed = urlparse(url)
        
        # A Google Fonts stylesheet is chosen by its query (?family=...), so
        # the query is part of its name: one file per family set.
        if self._is_google_fonts_css(url):
            query_hash = hashlib.md5(parsed.query.encode()).hexdigest()[:8]
            return self._place_in_output(f"fonts.googleapis.com/css-{query_hash}.css", kind, "")

        # Special handling for Google Fonts - preserve domain structure
        if _host_matches(url, self.GOOGLE_FONT_HOSTS):
            # For Google Fonts, preserve the full domain and path structure
            # e.g., fonts.googleapis.com/css-abc123.css or fonts.gstatic.com/s/montserrat/v29/file.woff2
            domain_path = unquote(f"{parsed.netloc}{parsed.path}")
            # Remove leading slashes
            while domain_path.startswith("/"):
                domain_path = domain_path[1:]
            # Default to no extension: these paths are stored verbatim, and
            # only a known stylesheet or script earns one.
            return self._place_in_output(domain_path, kind, "")
        
        # Special handling for Squarespace CDN - preserve domain structure
        # This prevents CDN root URLs from overwriting index.html
        if self._is_squarespace_cdn(url):
            domain_path = unquote(f"{parsed.netloc}{parsed.path}")
            # Remove leading slashes
            while domain_path.startswith("/"):
                domain_path = domain_path[1:]
            # If no path, add index.html under the domain folder
            if not parsed.path or parsed.path == "/":
                domain_path = f"{parsed.netloc}/index.html"
            return self._place_in_output(domain_path, kind, "")
        
        path = unquote(parsed.path)

        # A trailing slash means a directory; record it before dot-segment
        # removal strips the trailing empty component.
        is_directory = not path or path.endswith("/")

        # Remove leading slashes, collapse duplicate slashes, and resolve
        # "." / ".." segments so archived content cannot escape output_dir.
        path = self._sanitize_output_relpath(path)

        # Directories get an index.html *inside* them. Replacing the whole
        # path here instead made every /section/ page overwrite the root
        # index.html, so only the last one archived survived.
        if is_directory or not path:
            path = posixpath.join(path, "index.html")

        # A path with no extension is treated as a page unless the reference
        # said otherwise.
        return self._place_in_output(path, kind, self.DEFAULT_EXTENSION)
    
    def _output_relative_url(self, path: Path) -> str:
        """
        Express a path inside output_dir as a root-relative URL path.

        Args:
            path: A path from _get_local_path, or one of its parent dirs.

        Returns:
            The path relative to output_dir, with a leading "/".
        """
        relative = path.relative_to(Path(self.config.output_dir))
        return "/" + "/".join(relative.parts)

    def _get_relative_link_path(self, url: str, kind: str = "page") -> str:
        """
        Get the link to write for a URL, relative to the current page.

        The target comes from _get_local_path rather than being worked out a
        second time, so a link cannot name a file the downloader does not
        write. Paths are relative to the page doing the linking, so the
        archive works opened straight from the filesystem with no web server.

        Args:
            url: The normalized URL to convert
            kind: How this reference uses the URL - "page", "stylesheet",
                  "script", "image" or "asset". Passed to _get_local_path,
                  which needs it only to pick an extension for a URL that
                  carries none.
        """
        parsed = urlparse(url)

        # Query and fragment belong to the reference, not to the file - except
        # for a Google Fonts stylesheet, whose query is in its file name.
        suffix = ""
        if parsed.query and not self._is_google_fonts_css(url):
            suffix += "?" + parsed.query
        if parsed.fragment:
            suffix += "#" + parsed.fragment

        path = self._output_relative_url(self._get_local_path(url, kind))

        # Hop from the directory holding the page that carries the link.
        current_url = getattr(self, "_current_page_url", None)
        if current_url:
            from_dir = self._output_relative_url(
                self._get_local_path(current_url).parent
            )
            path = posixpath.relpath(path, from_dir)

        return self._encode_link_path(path) + suffix

    def _to_relative_path(self, abs_path: str) -> str:
        """Convert a root-absolute path to one relative to the current page."""
        current_url = getattr(self, '_current_page_url', None)
        if not current_url or not abs_path.startswith("/"):
            return abs_path
        from_parsed = urlparse(current_url)
        from_path = unquote(from_parsed.path)
        if not from_path or from_path.endswith("/"):
            from_dir = from_path.rstrip("/") or "/"
        else:
            from_dir = posixpath.dirname(from_path)
        return posixpath.relpath(abs_path, from_dir or "/")

    # Offsets, in hours, of the other timestamps tried after a 404. Wayback
    # already answers any timestamp with the nearest capture, so a nearby
    # probe lands on the same answer; only a probe far enough away to have a
    # different nearest capture can find the file.
    FALLBACK_OFFSETS_HOURS = (-24, 24, -168)

    def _fallback_timestamps(self) -> List[str]:
        """The distinct timestamps to try after a 404, closest first."""
        timestamps = (
            (self.original_datetime + timedelta(hours=hours)).strftime('%Y%m%d%H%M%S')
            for hours in self.FALLBACK_OFFSETS_HOURS
        )
        return list(dict.fromkeys(timestamps))

    CDX_URL = "https://web.archive.org/cdx/search/cdx"
    CDX_MAX_LOOKUPS = 25
    CDX_MAX_CONSECUTIVE_FAILURES = 3
    # Only the exact titles: Cloudflare injects challenge-platform scripts
    # into normal pages too.
    CHALLENGE_TITLES = (
        b"<title>Just a moment...</title>",
        b"<title>Attention Required! | Cloudflare</title>",
    )

    def _bad_capture_reason(self, response) -> Optional[str]:
        """Why an archived answer is not the page, or None when it is.

        Wayback replays an archived 403 or 5xx with that status and a
        memento-datetime header; its own errors carry no such header, and a
        404 has its own search.
        """
        status = response.status_code
        if status >= 400 and status != 404 and response.headers.get("memento-datetime"):
            return f"archived HTTP {status}"
        if status == 200 and any(title in response.content[:16384] for title in self.CHALLENGE_TITLES):
            return "Cloudflare challenge page"
        return None

    def _nearest_good_timestamp(self, url: str, bad_timestamp: str) -> Optional[str]:
        """The timestamp of the capture of url with status 200 closest to the
        requested one, other than bad_timestamp, from one CDX query; None when
        there is none or CDX does not answer."""
        if (
            self._cdx_lookups >= self.CDX_MAX_LOOKUPS
            or self._cdx_failures >= self.CDX_MAX_CONSECUTIVE_FAILURES
        ):
            return None
        self._cdx_lookups += 1
        try:
            response = self.session.get(
                self.CDX_URL,
                params={
                    "url": url,
                    "output": "json",
                    "fl": "timestamp",
                    "filter": "statuscode:200",
                    "closest": self.original_datetime.strftime('%Y%m%d%H%M%S'),
                    "sort": "closest",
                    # A challenge archived as 200 passes the filter, so the
                    # closest row can be the bad capture itself.
                    "limit": "5",
                },
                timeout=30,
            )
            if response.status_code != 200:
                raise ValueError(f"CDX answered HTTP {response.status_code}")
            rows = response.json()
        except Exception:
            self._cdx_failures += 1
            if self._cdx_failures == self.CDX_MAX_CONSECUTIVE_FAILURES:
                print("         ⚠️  The Wayback CDX index is not answering; no more capture lookups this run", flush=True)
            return None
        self._cdx_failures = 0
        for row in rows[1:]:
            if row and str(row[0]) != bad_timestamp:
                return str(row[0])
        return None

    def _fetch_nearest_good_capture(self, url: str, reason: str, is_html_page: bool, bad_response) -> Optional[bytes]:
        """Replace a bad capture of url with the nearest good one, if any."""
        print(f"         ⚠️  Capture is {reason}; looking for the nearest good one", flush=True)
        # The capture Wayback served, which can differ from the one asked for.
        served = re.search(r"/web/(\d{14})", bad_response.url or "")
        bad_timestamp = served.group(1) if served else self.original_datetime.strftime('%Y%m%d%H%M%S')
        timestamp = self._nearest_good_timestamp(url, bad_timestamp)
        if not timestamp:
            print(f"         ⚠️  No good capture found", flush=True)
            return None
        fallback_url = self._convert_to_wayback_url_with_timestamp(url, timestamp, use_iframe=is_html_page)
        try:
            response = self.session.get(fallback_url, timeout=15, allow_redirects=True)
        except Exception:
            return None
        if response.status_code != 200 or self._bad_capture_reason(response):
            print(f"         ⚠️  The capture at {timestamp} is not usable either", flush=True)
            return None
        if url == self.config.base_url:
            # Assets resolve around the capture actually used.
            print(f"         Requested capture is {reason}; using nearest good capture {timestamp}", flush=True)
            self.original_timestamp = timestamp
            self.original_datetime = datetime.strptime(timestamp, '%Y%m%d%H%M%S')
        return self._body_of(response)

    def _is_corrupted_font(self, content: bytes, url: str) -> bool:
        """Check if a downloaded font file is actually an HTML error page.
        
        Wayback Machine sometimes returns HTML error pages instead of font files.
        This detects those cases.
        """
        # Check if it's a font file extension
        font_extensions = ('.woff', '.woff2', '.ttf', '.eot', '.otf', '.svg')
        if not any(url.lower().endswith(ext) for ext in font_extensions):
            return False
        
        # Check if content starts with HTML (error page)
        # HTML typically starts with <!doctype, <html, or <HTML
        content_start = content[:200].strip()
        if content_start.startswith((b'<!doctype', b'<!DOCTYPE', b'<html', b'<HTML')):
            return True
        
        return False
    
    def download_file(self, url: str) -> Optional[bytes]:
        """Download a file from the given URL with timeframe fallback.
        
        If the file returns 404 at the original timestamp, searches nearby
        timestamps to find when the file was available.
        If all Wayback attempts fail and the URL is on a well-known CDN
        (LIVE_FALLBACK_HOSTS), tries that CDN live.
        """
        self._last_charset = None
        self._last_failure = None
        # Determine if this is an HTML page (we should NOT fallback to live for HTML)
        parsed = urlparse(url)
        path_lower = parsed.path.lower()
        # A referenced stylesheet or script, or a Google Fonts stylesheet, is
        # never a page, whatever the URL looks like; asking for the iframe view
        # of one returns the Wayback wrapper rather than the file.
        is_html_page = (
            not self._is_google_fonts_css(url)
            and self._referenced_kind(url) not in ("stylesheet", "script")
            and self._is_html_url(url, parsed)
        )
        
        # For HTML pages, try the 'if_' version first to get unwrapped content
        # This avoids the Wayback Machine interface wrapper
        if is_html_page:
            wayback_url_if = self._convert_to_wayback_url_with_timestamp(url, use_iframe=True)
            try:
                response = self.session.get(
                    wayback_url_if, timeout=15, allow_redirects=True
                )
                reason = self._bad_capture_reason(response)
                if reason:
                    return self._fetch_nearest_good_capture(url, reason, is_html_page, response)
                if response.status_code == 429:
                    # Still throttled after the retries; the plain URL would be too.
                    self._last_failure = "throttled"
                    return None
                response.raise_for_status()
                content = self._body_of(response)
                
                # Verify it's actually HTML content, not an error page
                content_start = content[:200].strip()
                if content_start.startswith((b'<!doctype', b'<!DOCTYPE', b'<html', b'<HTML')):
                    # The if_ version still has Wayback scripts but also contains the actual page
                    # Check if it has actual page content (not just the wrapper interface)
                    try:
                        html_str = content.decode("utf-8", errors="replace")[:5000]
                        # Check if it's ONLY the wrapper (has Wayback Machine title AND no actual page content)
                        # The if_ version will have both Wayback scripts AND the actual page content
                        is_only_wrapper = (
                            "<title>Wayback Machine</title>" in html_str and
                            "<!-- This is Squarespace. -->" not in html_str and
                            "<body" not in html_str.lower() or
                            (html_str.count("<body") == 0 and "<!-- End Wayback Rewrite JS Include -->" not in html_str)
                        )
                        if not is_only_wrapper:
                            # Got content (even if it has Wayback scripts, it has the actual page)
                            return content
                    except Exception:
                        # If we can't decode, assume it's good
                        return content
            except requests.exceptions.ConnectionError:
                self._last_failure = "connection"
                return None
            except Exception:
                # If if_ version fails, fall through to regular download
                pass
        
        # Try original timestamp first (or fallback from if_)
        wayback_url = self._convert_to_wayback_url_with_timestamp(url)
        try:
            response = self.session.get(
                wayback_url, timeout=15, allow_redirects=True
            )
            reason = self._bad_capture_reason(response)
            if reason:
                return self._fetch_nearest_good_capture(url, reason, is_html_page, response)
            response.raise_for_status()
            content = self._body_of(response)
            
            # Check if font file is corrupted (HTML error page)
            if self._is_corrupted_font(content, url):
                # Mark as corrupted and don't return it
                normalized_url = self._normalize_url(url, self.config.base_url)
                self.corrupted_fonts.add(normalized_url)
                print(f"         ⚠️  Font file is corrupted (HTML error page) - will be removed from CSS", flush=True)
                return None
            
            return content
        except requests.exceptions.HTTPError as e:
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 404:
                # File not found at original timestamp, try a few others
                for timestamp in self._fallback_timestamps():
                    try:
                        variant_url = self._convert_to_wayback_url_with_timestamp(
                            url, timestamp, use_iframe=is_html_page
                        )
                        variant_response = self.session.get(
                            variant_url, timeout=10, allow_redirects=True
                        )
                        if variant_response.status_code == 200:
                            content = self._body_of(variant_response)
                            if self._is_corrupted_font(content, url):
                                normalized_url = self._normalize_url(url, self.config.base_url)
                                self.corrupted_fonts.add(normalized_url)
                                print(f"         ⚠️  Font file is corrupted (HTML error page) - will be removed from CSS", flush=True)
                                continue  # Try next timestamp
                            return content
                    except Exception:
                        continue

                # All Wayback attempts failed - try a well-known CDN live (only for assets, not HTML pages)
                if not is_html_page:
                    return self._fetch_from_live_cdn(url)
            elif e.response is not None and e.response.status_code == 429:
                self._last_failure = "throttled"
            # Other HTTP errors - skip silently
        except requests.exceptions.Timeout as e:
            if isinstance(e, requests.exceptions.ConnectionError):
                self._last_failure = "connection"
            # Timeout on Wayback - try a well-known CDN live (only for assets)
            if not is_html_page:
                return self._fetch_from_live_cdn(url)
        except requests.exceptions.ConnectionError:
            self._last_failure = "connection"
        except Exception:
            pass
        
        return None

    def _body_of(self, response) -> bytes:
        """The response body, remembering the charset its Content-Type named."""
        content_type = str(getattr(response, "headers", {}).get("Content-Type") or "")
        match = re.search(r"charset\s*=\s*[\"']?([\w.:-]+)", content_type, re.IGNORECASE)
        self._last_charset = match.group(1) if match else None
        self._last_final_url = getattr(response, "url", None)
        return response.content

    def _decode_text(self, content: bytes, charset: Optional[str] = None, is_html: bool = False) -> str:
        """
        Decode a page, stylesheet or script without dropping characters.

        Tries, in order: a byte order mark, UTF-8, the charset the HTTP
        response named, the document's own declaration (<meta charset>,
        @charset), then windows-1252 with replacement characters. Valid UTF-8
        is practically never Latin-1 text, and old servers labelled every
        response ISO-8859-1. Old European sites are mostly ISO-8859-1 and used
        to lose every accented letter. UTF-8 with a stray byte (a pasted
        windows-1252 quote) stays UTF-8 and loses only that byte.

        Args:
            content: The raw bytes.
            charset: The charset from the response's Content-Type, if any.
            is_html: Look for a <meta> declaration rather than @charset.
        """
        data, bom_encoding = EncodingDetector.strip_byte_order_mark(content)
        if is_html:
            declared = EncodingDetector.find_declared_encoding(data, is_html=True)
        else:
            match = re.match(rb"\s*@charset\s+[\"']([\w.:-]+)[\"']", data, re.IGNORECASE)
            declared = match.group(1).decode("ascii") if match else None

        for candidate in (bom_encoding, "utf-8", charset, declared):
            if not candidate:
                continue
            try:
                name = codecs.lookup(candidate).name
            except LookupError:
                continue
            # As browsers do: latin-1 and ascii labels mean windows-1252, and
            # a UTF-16 label without a byte order mark means UTF-8.
            if name in ("latin-1", "iso8859-1", "ascii"):
                name = "cp1252"
            elif name.startswith(("utf-16", "utf-32")) and candidate != bom_encoding:
                name = "utf-8"
            try:
                return data.decode(name)
            except UnicodeDecodeError:
                continue
        # At least as many valid multi-byte sequences as bad bytes: UTF-8
        # with a few stray bytes. Latin-1 text almost never forms one.
        text = data.decode("utf-8", errors="replace")
        bad = text.count("\ufffd")
        if sum(1 for c in text if c > "\x7f") - bad >= bad:
            return text
        return data.decode("cp1252", errors="replace")

    @staticmethod
    def _looks_like_markup(content: bytes) -> bool:
        """True when a body reads as HTML: text that opens with a tag, or
        names <html>, <head> or <body> near its start."""
        head = content[:1024]
        if b"\x00" in head:
            return False
        start = head.lstrip(b"\xef\xbb\xbf \t\r\n")
        return start.startswith(b"<") or re.search(rb"<(html|head|body)\b", head, re.I) is not None

    # Extensions of files that are never an HTML document.
    ASSET_EXTENSIONS = frozenset({
        ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp", ".tiff",
        ".woff", ".woff2", ".ttf", ".eot", ".otf", ".css", ".js", ".mjs",
    })

    def _is_html_instead_of_asset(self, content: bytes, url: str) -> bool:
        """
        True when an image, font, script or stylesheet came back as an HTML
        document - Wayback answers some asset requests with its own page.
        """
        ext = os.path.splitext(urlparse(url).path.lower())[1]
        expects_asset = (
            ext in self.ASSET_EXTENSIONS
            or self._is_google_fonts_css(url)
            or self._referenced_kind(url) in ("stylesheet", "script", "image")
        )
        if not expects_asset:
            return False
        start = content[:512].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
        return start.startswith((b"<!doctype html", b"<html"))

    def _fetch_from_live_cdn(self, url: str) -> Optional[bytes]:
        """Fetch a file Wayback does not have, if it lives on a well-known CDN.

        Anything not on LIVE_FALLBACK_HOSTS returns None without a request.
        Redirects are not followed, so an allowed host cannot send the request
        anywhere else.
        """
        if not _host_matches(url, self.LIVE_FALLBACK_HOSTS):
            return None
        try:
            print(f"         🔄 Wayback failed, trying CDN: {url[:80]}...", flush=True)
            live_response = self.session.get(url, timeout=10, allow_redirects=False)
            if live_response.status_code != 200:
                return None
            content = self._body_of(live_response)
        except Exception:
            return None

        # Check if font file is corrupted
        if self._is_corrupted_font(content, url):
            normalized_url = self._normalize_url(url, self.config.base_url)
            self.corrupted_fonts.add(normalized_url)
            print(f"         ⚠️  Font file is corrupted (HTML error page) - will be removed from CSS", flush=True)
            return None

        print(f"         ✓ Downloaded from CDN (live fallback)", flush=True)
        return content
    
    def _get_file_type_from_url(self, url: str) -> str:
        """Get a human-readable file type from URL."""
        parsed = urlparse(url)
        path = parsed.path.lower()
        
        # Check for Google Fonts CSS files (they don't have .css extension)
        if self._is_google_fonts_css(url):
            return "CSS"
        
        if path.endswith('.html') or path.endswith('.htm') or not os.path.splitext(path)[1]:
            return "HTML"
        elif path.endswith('.css'):
            return "CSS"
        elif path.endswith('.js') or path.endswith('.mjs'):
            return "JavaScript"
        elif any(path.endswith(ext) for ext in ['.woff', '.woff2', '.ttf', '.eot', '.otf', '.svg']):
            return "Font"
        elif any(path.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico']):
            return "Image"
        elif path.endswith('.json'):
            return "JSON"
        elif path.endswith('.xml'):
            return "XML"
        else:
            return "Asset"

    def _optimize_html(self, html: str) -> str:
        """Optimize HTML code."""
        if not self.config.optimize_html:
            return html

        try:
            import minify_html
            # minify-html is a Python 3.14+ compatible alternative to htmlmin
            # minify_html.minify() expects a string, not bytes
            return minify_html.minify(html, minify_js=False, minify_css=False)
        except Exception as e:
            print(f"Error optimizing HTML: {e}")
            return html

    def _minify_js(self, content: str) -> str:
        """Minify JavaScript."""
        if not self.config.minify_js:
            return content

        try:
            import rjsmin

            return rjsmin.jsmin(content)
        except Exception as e:
            print(f"Error minifying JS: {e}")
            return content

    def _check_and_remove_corrupted_fonts_in_css(self, css: str, base_url: str) -> str:
        """Proactively check font URLs in CSS and detect corrupted ones.
        
        This checks font files referenced in CSS to see if they're HTML error pages,
        even before they're queued for download.
        """
        # Probe the absolute URLs the stylesheet names, before the rewrite
        # turns them into local paths that no longer say which host they are on
        font_extensions = ('.woff', '.woff2', '.ttf', '.eot', '.otf', '.svg')
        for font_url in self._extract_css_urls(css, base_url):
            if not font_url.lower().endswith(font_extensions):
                continue

            # Skip if already known corrupted or already probed this run
            if font_url in self.corrupted_fonts or font_url in self._probed_fonts:
                continue
            self._probed_fonts.add(font_url)
            
            # Try to download and check if corrupted (with quick timeout)
            try:
                wayback_url = self._convert_to_wayback_url_with_timestamp(font_url)
                response = self.session.get(wayback_url, timeout=5, allow_redirects=True)
                if response.status_code == 200:
                    if self._is_corrupted_font(response.content, font_url):
                        self.corrupted_fonts.add(font_url)
                        print(f"         ⚠️  Detected corrupted font in CSS: {os.path.basename(font_url)}", flush=True)
            except Exception as e:
                # If we can't check, skip - it will be checked when actually downloaded
                # Don't print errors here to avoid spam
                pass
        
        return css
    
    def _remove_corrupted_fonts_from_css(self, css: str) -> str:
        """Remove references to corrupted font files from CSS.
        
        This prevents browsers from trying to load HTML error pages as fonts,
        which can break typography.
        """
        if not self.corrupted_fonts:
            return css
        
        # For each corrupted font, remove its references from CSS
        for corrupted_font_url in self.corrupted_fonts:
            font_filename = os.path.basename(urlparse(corrupted_font_url).path)
            if not font_filename:
                continue

            # One url() entry naming this file in any directory, with its
            # query or fragment, its format() and the comma joining it to the
            # entry before. [^"'()] keeps a match inside its own url(), so it
            # cannot run on into the rules that follow.
            pattern = (
                rf'(?:,\s*)?url\s*\(\s*["\']?(?:[^"\'()]*/)?{re.escape(font_filename)}'
                rf'(?:[?#][^"\'()]*)?["\']?\s*\)(?:\s*format\s*\([^)]*\))?'
            )
            css = re.sub(pattern, '', css, flags=re.IGNORECASE)
        
        # Clean up any double commas or trailing commas
        css = re.sub(r',\s*,+', ',', css)  # Multiple commas
        css = re.sub(r',\s*}', '}', css)  # Trailing comma before }
        css = re.sub(r'src:\s*,', 'src:', css)  # src: with leading comma
        css = re.sub(r'src:\s*;', '', css)  # Empty src:;
        
        return css
    
    def _remove_legacy_font_formats_from_css(self, css: str) -> str:
        """Remove .eot and .svg font format references from CSS.
        
        These legacy formats are often corrupted (HTML error pages) in Wayback Machine,
        and modern browsers don't need them - they'll use .woff2, .woff, and .ttf.
        """
        # Remove .eot references (with or without format)
        css = re.sub(r',\s*url\s*\(\s*["\']?[^"\'()]*\.eot["\']?\s*\)\s*(?:format\s*\([^)]+\))?', '', css, flags=re.IGNORECASE)
        css = re.sub(r'url\s*\(\s*["\']?[^"\'()]*\.eot["\']?\s*\)\s*(?:format\s*\([^)]+\))?', '', css, flags=re.IGNORECASE)
        css = re.sub(r'src:\s*url\s*\(\s*["\']?[^"\'()]*\.eot["\']?\s*\)\s*;', '', css, flags=re.IGNORECASE)
        
        # Remove .svg font format references (but keep .svg images)
        # Only remove if it's in a font context (has format("svg") or in @font-face)
        css = re.sub(r',\s*url\s*\(\s*["\']?[^"\'()]*\.svg["\']?\s*\)\s+format\s*\(["\']?svg["\']?\)', '', css, flags=re.IGNORECASE)
        css = re.sub(r'url\s*\(\s*["\']?[^"\'()]*\.svg["\']?\s*\)\s+format\s*\(["\']?svg["\']?\)', '', css, flags=re.IGNORECASE)
        
        # Clean up any double commas or trailing commas
        css = re.sub(r',\s*,+', ',', css)  # Multiple commas
        css = re.sub(r',\s*}', '}', css)  # Trailing comma before }
        css = re.sub(r'src:\s*,', 'src:', css)  # src: with leading comma
        css = re.sub(r'src:\s*;', '', css)  # Empty src:;
        
        return css
    
    def _minify_css(self, content: str) -> str:
        """Minify CSS."""
        if not self.config.minify_css:
            return content

        try:
            import cssmin

            return cssmin.cssmin(content)
        except Exception as e:
            print(f"Error minifying CSS: {e}")
            return content

    def _extract_css_urls(self, css: str, base_url: str) -> List[str]:
        """Extract URLs from CSS content."""
        urls = []
        
        # Extract @import URLs
        import_pattern = r'@import\s+(?:url\()?["\']?([^"\'()]+)["\']?\)?'
        for match in re.finditer(import_pattern, css, re.IGNORECASE):
            import_url = match.group(1).strip()
            # Extract from wayback URLs
            original = self._extract_original_url_from_path(import_url)
            if original:
                import_url = original
            normalized = self._normalize_url(import_url, base_url)
            if normalized not in urls:
                urls.append(normalized)
        
        # Extract url() references (images, fonts, etc.)
        url_pattern = r'url\s*\(\s*["\']?([^"\'()]+)["\']?\s*\)'
        for match in re.finditer(url_pattern, css, re.IGNORECASE):
            css_url = match.group(1).strip()
            # Skip data URIs and special protocols
            if not css_url.startswith(("data:", "javascript:", "vbscript:", "#")):
                # Extract from wayback URLs
                original = self._extract_original_url_from_path(css_url)
                if original:
                    css_url = original
                # Convert relative paths to absolute URLs using base_url
                # This is critical for font files referenced with relative paths in CSS
                if css_url.startswith("/") and not css_url.startswith("//"):
                    # Absolute path from domain root - construct full URL
                    from urllib.parse import urljoin
                    parsed_base = urlparse(base_url)
                    css_url = f"{parsed_base.scheme}://{parsed_base.netloc}{css_url}"
                normalized = self._normalize_url(css_url, base_url)
                if normalized not in urls:
                    urls.append(normalized)
        
        return urls

    def _rewrite_css_urls(self, css: str, base_url: str) -> str:
        """Rewrite URLs in CSS to relative paths."""
        def replace_css_url(match):
            """Rewrite a single CSS url() match to a relative local path."""
            full_match = match.group(0)
            url_part = match.group(1)
            
            # Extract original URL from wayback path
            original = self._extract_original_url_from_path(url_part)
            if original:
                url_part = original
            
            # Handle absolute paths starting with / in Google Fonts CSS files
            # These are relative to fonts.gstatic.com, not the site's domain
            if url_part.startswith("/") and not url_part.startswith("//"):
                # Check if this is a Google Fonts CSS file (base_url contains fonts.googleapis.com)
                if _host_matches(base_url, self.GOOGLE_FONTS_CSS_HOSTS):
                    # Convert to full Google Fonts URL
                    url_part = f"https://fonts.gstatic.com{url_part}"
                else:
                    # Regular absolute path - convert using base_url
                    parsed_base = urlparse(base_url)
                    url_part = f"{parsed_base.scheme}://{parsed_base.netloc}{url_part}"
            
            normalized = self._normalize_url(url_part, base_url)
            
            # Handle fonts.gstatic.com URLs - these need to be converted to local paths
            # to avoid CORS issues when loading from localhost
            is_google_font = _host_matches(normalized, self.GOOGLE_FONT_HOSTS)
            is_squarespace_cdn = self._is_squarespace_cdn(normalized)
            if self._is_internal_url(normalized) or is_google_font or is_squarespace_cdn:
                # @import names a stylesheet; a bare url() names an asset, and
                # the two want different extensions when the URL carries none.
                preceding = match.string[:match.start()].rstrip()
                reference_kind = "stylesheet" if preceding.endswith("@import") else "asset"
                if reference_kind == "stylesheet":
                    # Note it before the branch below, which does not run at
                    # all with relative links off - the imported stylesheet
                    # would then be downloaded as a page and rewritten as HTML.
                    # Only a stylesheet is worth pinning: recording "asset"
                    # would freeze the name for any later reference.
                    self._note_reference_kind(normalized, reference_kind)

                if self.config.make_internal_links_relative:
                    # For Google Fonts, construct relative path from the normalized URL
                    if is_google_font:
                        # Construct path directly from URL to avoid path duplication
                        parsed_font = urlparse(normalized)
                        if "fonts.gstatic.com" in parsed_font.netloc:
                            # Path will be like fonts.gstatic.com/s/montserrat/v29/...
                            # Check if path already contains the domain (avoid duplication)
                            font_path = parsed_font.path.lstrip("/")
                            if font_path.startswith("fonts.gstatic.com"):
                                relative_path = font_path
                            else:
                                relative_path = f"{parsed_font.netloc}/{font_path}"
                        elif "fonts.googleapis.com" in parsed_font.netloc:
                            # For Google Fonts CSS files
                            relative_path = parsed_font.path.lstrip("/")
                        else:
                            relative_path = parsed_font.path.lstrip("/")
                        # Ensure it starts with / for absolute paths
                        if not relative_path.startswith("/"):
                            relative_path = "/" + relative_path
                        new_path = relative_path
                    else:
                        new_path = self._make_relative_path(normalized, reference_kind)
                    return f"url({new_path})"
                return f"url({normalized})"
            
            # If it's a Squarespace CDN URL, still rewrite it to local path
            if is_squarespace_cdn:
                parsed_resource = urlparse(normalized)
                resource_path = f"{parsed_resource.netloc}{parsed_resource.path}"
                # Remove leading slashes
                while resource_path.startswith("/"):
                    resource_path = resource_path[1:]
                if self.config.make_internal_links_relative:
                    return f"url(/{resource_path})"
                return f"url({normalized})"
            
            return full_match
        
        def replace_bare_import(match):
            """Rewrite @import "path" - the form with no url() wrapper."""
            url_part = match.group(1).strip()
            if url_part.startswith(("data:", "javascript:", "#")):
                return match.group(0)

            original = self._extract_original_url_from_path(url_part)
            if original:
                url_part = original

            if url_part.startswith("/") and not url_part.startswith("//"):
                parsed_base = urlparse(base_url)
                url_part = f"{parsed_base.scheme}://{parsed_base.netloc}{url_part}"

            normalized = self._normalize_url(url_part, base_url)
            if not (self._is_internal_url(normalized) or self._is_squarespace_cdn(normalized)):
                return match.group(0)

            # Note it before the branch below, which does not run with
            # relative links off - the import would then be downloaded as a
            # page and rewritten as HTML.
            self._note_reference_kind(normalized, "stylesheet")

            if not self.config.make_internal_links_relative:
                return f'@import "{normalized}"'
            return f'@import "{self._make_relative_path(normalized, "stylesheet")}"'

        # @import may name its stylesheet directly, with no url() around it.
        # _extract_css_urls already follows that form, so the file was being
        # downloaded and then left unreferenced while the archived stylesheet
        # kept pointing at the live site.
        css = re.sub(
            r'@import\s+["\']([^"\']+)["\']',
            replace_bare_import,
            css,
            flags=re.IGNORECASE,
        )

        # Pattern to match url() with wayback URLs and absolute paths
        url_patterns = [
            r'url\s*\(\s*["\']?(https?://web\.archive\.org/web/\d+[a-z]*(?:im_|cs_|js_|jm_)/https?://[^"\'()]+)["\']?\s*\)',  # Absolute wayback (check first)
            r'url\s*\(\s*["\']?(/web/\d+[a-z]*(?:im_|cs_|js_|jm_)/https?://[^"\'()]+)["\']?\s*\)',  # Relative wayback
            r'url\s*\(\s*["\']?(https?://[^"\'()]+)["\']?\s*\)',  # Regular URLs
            r'url\s*\(\s*["\']?(/[^"\'()]+)["\']?\s*\)',  # Absolute paths (for Google Fonts CSS)
        ]
        
        for pattern in url_patterns:
            css = re.sub(pattern, replace_css_url, css, flags=re.IGNORECASE)
        
        return css

    def _extract_js_urls(self, js: str, base_url: str) -> List[str]:
        """Extract URLs from JavaScript content."""
        urls = []
        
        # More specific patterns to avoid false positives (like code snippets)
        patterns = [
            r'(?:fetch|XMLHttpRequest|axios\.get|axios\.post|\.load|\.ajax)\s*\(\s*["\']([^"\']+)["\']',  # Fetch/ajax calls
            r'\.src\s*=\s*["\']([^"\']+)["\']',  # src assignments
            r'\.href\s*=\s*["\']([^"\']+)["\']',  # href assignments
            r'url\s*[:=]\s*["\'](https?://[^"\']+)["\']',  # URL properties
            r'["\'](https?://[^"\']+\.(?:jpg|jpeg|png|gif|svg|webp|css|js|woff|woff2|ttf|eot|otf)[^"\']*)["\']',  # Asset URLs
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, js):
                js_url = match.group(1).strip()
                # Skip if it looks like code, not a URL
                if any(skip in js_url for skip in ["function", "return", "if", "else", "var ", "let ", "const "]):
                    continue
                if not js_url.startswith(("data:", "javascript:", "vbscript:", "#", "mailto:", "tel:", "//", "http", "https")):
                    continue
                if not js_url.startswith(("http://", "https://", "/")):
                    continue
                    
                original = self._extract_original_url_from_path(js_url)
                if original:
                    js_url = original
                normalized = self._normalize_url(js_url, base_url)
                if normalized not in urls and self._is_internal_url(normalized):
                    urls.append(normalized)
        
        return urls

    def _optimize_image(self, content: bytes, format: str = "JPEG") -> bytes:
        """Optimize image."""
        if not self.config.optimize_images:
            return content

        try:
            from PIL import Image
            from io import BytesIO

            img = Image.open(BytesIO(content))
            
            # Convert RGBA to RGB for JPEG
            if format.upper() == "JPEG" and img.mode == "RGBA":
                background = Image.new("RGB", img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            output = BytesIO()
            img.save(output, format=format, optimize=True, quality=85)
            return output.getvalue()
        except Exception as e:
            print(f"Error optimizing image: {e}")
            return content

    @staticmethod
    def _split_srcset(srcset: str) -> List[Tuple[str, str]]:
        """
        Split a srcset into (url, descriptor) candidates, as browsers do.

        A URL is a run of non-whitespace, so a comma inside it
        (Cloudinary's w_400,c_fill) stays part of it; candidates are
        separated by the comma after a descriptor or at the end of a URL.
        """
        candidates = []
        pos = 0
        while True:
            pos = re.compile(r"[\s,]*").match(srcset, pos).end()
            if pos >= len(srcset):
                return candidates
            url = re.compile(r"\S+").match(srcset, pos).group()
            pos += len(url)
            descriptor = ""
            if url.endswith(","):
                url = url.rstrip(",")
            else:
                descriptor = re.compile(r"[^,]*").match(srcset, pos).group()
                pos += len(descriptor)
                descriptor = descriptor.strip()
            candidates.append((url, descriptor))

    def _rewrite_srcset(self, srcset: str, base_url: str, links_to_follow: List[str]) -> str:
        """Rewrite every srcset candidate to its local path and queue it."""
        srcset_parts = []
        for url_part, descriptor in self._split_srcset(srcset):
            item = f"{url_part} {descriptor}" if descriptor else url_part
            descriptor = f" {descriptor}" if descriptor else ""
            original_srcset = url_part
            # Extract wayback URL if present
            original = self._extract_original_url_from_path(url_part)
            if original:
                url_part = original

            normalized_srcset = self._normalize_url(url_part, base_url)
            is_squarespace_cdn = self._is_squarespace_cdn(normalized_srcset) or self._is_squarespace_cdn(original_srcset)

            if not (self._is_internal_url(normalized_srcset) or is_squarespace_cdn):
                # Keep external URLs as-is
                srcset_parts.append(item)
                continue

            # Queue for download
            if normalized_srcset not in self.config.visited_urls:
                links_to_follow.append(url_part)

            # Rewrite to local path
            if not self.config.make_internal_links_relative:
                self._note_reference_kind(normalized_srcset, "image")
                srcset_parts.append(f"{normalized_srcset}{descriptor}")
            elif is_squarespace_cdn:
                parsed_resource = urlparse(normalized_srcset)
                resource_path = f"{parsed_resource.netloc}{parsed_resource.path}"
                # Preserve query string if present
                if parsed_resource.query:
                    resource_path += "?" + parsed_resource.query
                while resource_path.startswith("/"):
                    resource_path = resource_path[1:]
                srcset_parts.append(f"{self._to_relative_path(f'/{resource_path}')}{descriptor}")
            else:
                relative_path = self._get_relative_link_path(normalized_srcset, "image")
                srcset_parts.append(f"{relative_path}{descriptor}")
        return ", ".join(srcset_parts)

    def _process_html(self, html: str, base_url: str) -> tuple[str, List[str]]:
        """Process HTML content and extract links."""
        self._current_page_url = base_url
        soup = BeautifulSoup(html, "lxml")
        links_to_follow: List[str] = []

        # <base href> changes what relative references resolve against, so
        # resolve against it. The links written below are relative to the
        # page's own file, and a base left in the output would re-base them.
        base_tag = soup.find("base", href=True)
        if base_tag is not None:
            base_url = self._normalize_url(base_tag["href"], base_url)
            del base_tag["href"]
            if not base_tag.attrs:
                base_tag.decompose()

        # Remove Wayback Machine banner, scripts, and styles
        elements_to_remove = []
        for element in soup.find_all(["iframe", "div", "script", "link"], id=True):
            if element is None:
                continue
            try:
                element_id = element.get("id")
                if element_id and any(banner_id in str(element_id).lower() for banner_id in ["wm-ipp", "wm-bipp", "wm-toolbar", "wm-ipp-base"]):
                    elements_to_remove.append(element)
            except (AttributeError, TypeError):
                continue
        for element in elements_to_remove:
            element.decompose()
        
        # Remove wayback machine script tags by src
        # But preserve cookie consent scripts (cookieyes, etc.) even if they come from external CDNs
        for script in soup.find_all("script", src=True):
            src = script.get("src", "")
            # Preserve cookie consent scripts
            if "cookieyes" in src.lower() or "cookie-consent" in src.lower():
                continue
            # The toolbar is served from archive.org outside /web/ (today
            # web-static.archive.org/_static/). The page's own scripts replay
            # through web.archive.org/web/..., so that host alone says
            # nothing: matching it deleted the site's scripts.
            parsed_src = urlparse(src)
            is_archive_host = (parsed_src.hostname or "").endswith("archive.org")
            if (
                (is_archive_host and not parsed_src.path.startswith("/web/"))
                or src.startswith(("/_static/", "/static/js/"))
                or "bundle-playback.js" in src or "wombat.js" in src or "ruffle.js" in src
            ):
                script.decompose()
        
        # Remove wayback machine link tags by href (but keep internal links that need processing)
        for link in soup.find_all("link", href=True):
            if link is None:
                continue
            href = link.get("href", "")
            if not href:
                continue
            # Only remove wayback machine banner/styles, not internal assets that need processing
            if "banner-styles.css" in href or "iconochive.css" in href or "web-static.archive.org" in href:
                link.decompose()
            # For /web/ paths, we'll process them below, don't remove here
        
        # Remove wayback-specific meta tags and scripts
        for meta in soup.find_all("meta"):
            if meta is None:
                continue
            meta_property = meta.get("property")
            meta_content = meta.get("content", "")
            if meta_property == "og:url" and meta_content and "web.archive.org" in str(meta_content):
                meta.decompose()
        
        # Remove inline wayback scripts (__wm, __wm.wombat, RufflePlayer)
        for script in soup.find_all("script"):
            if script.string:
                script_content = script.string
                if any(pattern in script_content for pattern in ["__wm", "wombat", "RufflePlayer", "web.archive.org"]):
                    script.decompose()
        
        # Add Static object stub if needed (for Squarespace sites)
        # Check if any script references Static but it's not defined
        needs_static_stub = False
        for script in soup.find_all("script"):
            if script.string and ("Static." in script.string or "window.Static" in script.string):
                needs_static_stub = True
                break
        
        if needs_static_stub:
            # Find the first script tag and add stub before it, or add after SQUARESPACE_ROLLUPS if present
            first_script = soup.find("script")
            if first_script:
                static_stub = soup.new_string("\n")
                static_script = soup.new_tag("script")
                static_script.string = "window.Static = window.Static || {}; window.Static.SQUARESPACE_CONTEXT = window.Static.SQUARESPACE_CONTEXT || { showAnnouncementBar: false };"
                # Try to insert after SQUARESPACE_ROLLUPS script if it exists
                rollups_script = None
                for script in soup.find_all("script"):
                    if script.string and "SQUARESPACE_ROLLUPS" in script.string:
                        rollups_script = script
                        break
                if rollups_script:
                    rollups_script.insert_after(static_script)
                else:
                    first_script.insert_before(static_script)
        
        # Remove comments
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Remove trackers and analytics
        if self.config.remove_trackers:
            for script in soup.find_all("script", src=True):
                if script is None:
                    continue
                script_src = script.get("src")
                if script_src and self._is_tracker(script_src):
                    script.decompose()

            # Remove inline tracking scripts (Google Analytics, gtag, dataLayer)
            # Note: Cookie consent scripts (like cookieyes) are preserved as they're part of site functionality
            for script in soup.find_all("script"):
                if script.string:
                    script_text = script.string.lower()
                    # Only remove tracking scripts, not cookie consent functionality
                    if any(marker in script_text for marker in self.TRACKER_INLINE_MARKERS):
                        # Skip cookieyes and cookie consent scripts - preserve them
                        if "cookieyes" not in script_text and "cookie consent" not in script_text:
                            script.decompose()
            
            # Note: Cookie popups and consent UI are preserved - they're part of site functionality

        # Remove ads
        if self.config.remove_ads:
            for element in soup.find_all(["script", "iframe", "img"], src=True):
                if self._is_ad(element["src"]):
                    element.decompose()

        # Remove external iframes
        if self.config.remove_external_iframes:
            for iframe in soup.find_all("iframe", src=True):
                if not self._is_internal_url(iframe["src"]):
                    iframe.decompose()

        # Process frames (<frame src="...">) and internal iframes
        # Frame-based pages (using <frameset>/<frame>) won't render without their frame content
        for frame in soup.find_all(["frame", "iframe"], src=True):
            src = frame.get("src", "")
            if not src:
                continue
            # Extract wayback URL first
            original = self._extract_original_url_from_path(src)
            if original:
                src = original
            # Keep original URL with query strings for downloading
            original_url = src
            # Normalize for checking and final output
            normalized_url = self._normalize_url(src, base_url)

            if self._is_internal_url(normalized_url):
                if self.config.make_internal_links_relative:
                    # Frame content is HTML pages
                    frame["src"] = self._get_relative_link_path(normalized_url, "page")
                else:
                    frame["src"] = normalized_url

                if normalized_url not in self.config.visited_urls:
                    links_to_follow.append(original_url)

        # Process links
        for link in soup.find_all("a", href=True):
            if link is None:
                continue
            href = link.get("href", "")
            if not href:
                continue
            # A same-page fragment or a script link names no other page.
            if href.startswith("#") or href.strip().lower().startswith(("javascript:", "data:", "blob:", "about:")):
                continue
            
            # Check if this link is inside a floating buttons container BEFORE processing
            is_floating_button = False
            parent_classes = []
            parent = link.find_parent()
            while parent and parent.name:  # parent.name checks if it's a valid tag
                parent_class = parent.get("class")
                if parent_class:
                    if isinstance(parent_class, list):
                        parent_classes.extend(parent_class)
                    else:
                        parent_classes.append(str(parent_class))
                parent_id = parent.get("id", "")
                if parent_id and "sp-footeredu" in str(parent_id):
                    is_floating_button = True
                parent = parent.find_parent()
            
            is_floating_button = is_floating_button or any("botonesflotantes" in str(cls).lower() for cls in parent_classes)
            
            # For floating button links, preserve them as-is (don't process wayback URLs)
            if is_floating_button:
                # Extract wayback URL from href if present, but preserve tel:/mailto: protocols
                if href.startswith("https://web.archive.org/web/") or href.startswith("http://web.archive.org/web/") or href.startswith("/web/"):
                    # Extract protocol-relative URL from wayback path (e.g., /web/TIMESTAMP/tel:xxx)
                    wayback_protocol_pattern = r"/web/\d+[a-z]*/(tel:|mailto:|whatsapp:)(.+)"
                    match = re.search(wayback_protocol_pattern, href)
                    if match:
                        protocol = match.group(1)
                        path = match.group(2)
                        # Remove query params if present in the path
                        if "?" in path:
                            path = path.split("?")[0]
                        href = protocol + path
                        link["href"] = href
                    else:
                        # Check if it's a direct mailto: link in wayback URL
                        # Handle both relative (/web/TIMESTAMP/mailto:...) and absolute (https://web.archive.org/web/TIMESTAMP/mailto:...)
                        mailto_direct_patterns = [
                            r"/web/\d+[a-z]*/(mailto:[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
                            r"https?://web\.archive\.org/web/\d+[a-z]*/(mailto:[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"
                        ]
                        mailto_extracted = False
                        for pattern in mailto_direct_patterns:
                            mailto_direct_match = re.search(pattern, href)
                            if mailto_direct_match:
                                href = mailto_direct_match.group(1)
                                link["href"] = href
                                mailto_extracted = True
                                break
                        
                        if not mailto_extracted:
                            # Check if it's an email address hidden in an https:// URL
                            # Pattern: /web/TIMESTAMP/https://domain.com/email@domain.com
                            mailto_pattern = r"/web/\d+[a-z]*/https?://[^/]+/([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"
                            mailto_match = re.search(mailto_pattern, href)
                            if mailto_match:
                                email = mailto_match.group(1)
                                href = f"mailto:{email}"
                                link["href"] = href
                            else:
                                # Try regular extraction
                                original = self._extract_original_url_from_path(href)
                                if original:
                                    # Check if extracted URL looks like an email address (domain.com/email@domain.com -> mailto:)
                                    if "@" in original and "/" in original and not original.startswith("mailto:"):
                                        email_part = original.split("/")[-1]
                                        if "@" in email_part:
                                            href = f"mailto:{email_part}"
                                            link["href"] = href
                                    else:
                                        href = original
                                        link["href"] = href
                # Skip further processing for floating buttons - preserve them
                continue
            
            # Extract wayback URL first (for non-floating-button links)
            original = self._extract_original_url_from_path(href)
            if original:
                href = original
            # Keep original URL with query strings for downloading - normalize later for file paths
            original_url = href
            # Normalize only for checking if internal/external
            parsed_original = urlparse(original_url)
            normalized_for_check = parsed_original._replace(fragment="", query="").geturl()
            # Check if internal using normalized version
            is_internal = self._is_internal_url(normalized_for_check)

            # Handle contact links (but preserve floating buttons and icon groups - already handled above)
            # Check if link is in an icon group before removing contact links
            parent = link.parent
            is_in_icon_group = False
            while parent is not None:
                parent_classes = parent.get("class", [])
                if parent_classes:
                    if isinstance(parent_classes, list):
                        parent_classes_str = " ".join(parent_classes)
                    else:
                        parent_classes_str = str(parent_classes)
                    if "sppb-icons-group-list" in parent_classes_str or "icons-group" in parent_classes_str.lower():
                        is_in_icon_group = True
                        break
                parent = parent.parent if hasattr(parent, 'parent') else None
            
            if self.config.remove_clickable_contacts and self._is_contact_link(original_url) and not is_floating_button and not is_in_icon_group:
                if self.config.remove_external_links_remove_anchors:
                    link.decompose()
                else:
                    link["href"] = "#"
                continue

            # Handle external links (but preserve floating button contact links and contact links when not removing them)
            if not is_internal:
                # Preserve contact links (tel:, mailto:) when remove_clickable_contacts is False
                if self._is_contact_link(original_url) and not self.config.remove_clickable_contacts:
                    # Update href to the extracted URL (removes wayback prefix)
                    link["href"] = original_url
                    continue
                
                # Don't remove/modify contact links in floating buttons
                if is_floating_button and self._is_contact_link(original_url):
                    # Keep the original href for floating button contact links
                    continue
                
                # Preserve button links (sppb-btn classes) - these are styled buttons that should remain functional
                link_classes = link.get("class", [])
                if link_classes and isinstance(link_classes, list):
                    link_classes_str = " ".join(link_classes)
                elif link_classes:
                    link_classes_str = str(link_classes)
                else:
                    link_classes_str = ""
                
                is_button_link = "sppb-btn" in link_classes_str or "btn" in link_classes_str
                if is_button_link:
                    # Preserve button links - just clean up the href (remove wayback prefix)
                    link["href"] = original_url
                    continue
                
                # Preserve links in icon groups (sppb-icons-group-list) - these are social media icons
                # Check if the link is inside an icon group list
                parent = link.parent
                is_in_icon_group = False
                while parent is not None:
                    parent_classes = parent.get("class", [])
                    if parent_classes:
                        if isinstance(parent_classes, list):
                            parent_classes_str = " ".join(parent_classes)
                        else:
                            parent_classes_str = str(parent_classes)
                        if "sppb-icons-group-list" in parent_classes_str or "icons-group" in parent_classes_str.lower():
                            is_in_icon_group = True
                            break
                    parent = parent.parent if hasattr(parent, 'parent') else None
                
                if is_in_icon_group:
                    # Preserve icon group links - just clean up the href (remove wayback prefix)
                    link["href"] = original_url
                    continue
                
                if self.config.remove_external_links_remove_anchors:
                    link.decompose()
                elif self.config.remove_external_links_keep_anchors:
                    # Drop the link but keep what it wrapped: text, images, markup
                    link.unwrap()
                else:
                    link["href"] = original_url
                continue

            # Process internal links - normalize for final HTML output
            normalized_url = self._normalize_url(original_url, base_url)
            # Normalizing drops the fragment; the link keeps it.
            fragment = "#" + parsed_original.fragment if parsed_original.fragment else ""
            if self.config.make_internal_links_relative:
                # Use _get_relative_link_path to ensure links match saved file paths
                relative_path = self._get_relative_link_path(normalized_url, "page")
                link["href"] = relative_path + fragment
            else:
                if self.config.make_non_www or self.config.make_www:
                    link["href"] = normalized_url + fragment

            # Add to links to follow - use original URL with query strings for downloading
            # Track by normalized URL to avoid downloading same file multiple times
            if normalized_url not in self.config.visited_urls:
                links_to_follow.append(original_url)

        # <meta http-equiv="refresh" content="5; url=...">: a redirect page.
        # Rewrite its target like a link and keep the delay.
        for meta in soup.find_all("meta", content=True):
            if str(meta.get("http-equiv", "")).lower() != "refresh":
                continue
            match = re.match(r"^\s*(\d+)\s*[;,]\s*url\s*=\s*['\"]?(.*?)['\"]?\s*$", meta["content"], re.IGNORECASE)
            if not match:
                continue
            delay, target = match.groups()
            target = self._extract_original_url_from_path(target) or target
            normalized_url = self._normalize_url(target, base_url)
            if self._is_internal_url(normalized_url):
                if self.config.make_internal_links_relative:
                    target = self._get_relative_link_path(normalized_url, "page")
                else:
                    target = normalized_url
                if normalized_url not in self.config.visited_urls:
                    links_to_follow.append(normalized_url)
            meta["content"] = f"{delay}; url={target}"

        # Process images
        for img in soup.find_all("img", src=True):
            src = img["src"]
            # Keep original src before processing (for Squarespace CDN detection)
            original_src = src
            # Extract wayback URL first
            original = self._extract_original_url_from_path(src)
            if original:
                src = original
            # Keep original URL with query strings for downloading
            original_url = src
            # Normalize for checking and final output
            normalized_url = self._normalize_url(src, base_url)

            # Check if it's Squarespace CDN (should be downloaded even though external)
            is_squarespace_cdn = self._is_squarespace_cdn(normalized_url) or self._is_squarespace_cdn(original_src)

            if self._is_internal_url(normalized_url) or is_squarespace_cdn:
                if self.config.make_internal_links_relative:
                    # Images are assets, don't add .html extension
                    if is_squarespace_cdn:
                        # For Squarespace CDN, preserve domain structure
                        parsed_img = urlparse(normalized_url)
                        img_path = f"{parsed_img.netloc}{parsed_img.path}"
                        # Remove leading slashes
                        while img_path.startswith("/"):
                            img_path = img_path[1:]
                        img["src"] = self._to_relative_path(f"/{img_path}")
                    else:
                        img["src"] = self._get_relative_link_path(normalized_url, "image")
                else:
                    img["src"] = normalized_url

                if normalized_url not in self.config.visited_urls:
                    links_to_follow.append(original_url)

        # Process HTML background attributes (legacy <body>, <table>, <td>, <tr>, <th>)
        for elem in soup.find_all(["body", "table", "td", "tr", "th"], attrs={"background": True}):
            bg = elem.get("background", "")
            if not bg:
                continue
            original = self._extract_original_url_from_path(bg)
            if original:
                bg = original
            original_url = bg
            normalized_url = self._normalize_url(bg, base_url)
            if self._is_internal_url(normalized_url):
                if self.config.make_internal_links_relative:
                    elem["background"] = self._get_relative_link_path(normalized_url, "image")
                else:
                    elem["background"] = normalized_url
                if normalized_url not in self.config.visited_urls:
                    links_to_follow.append(original_url)

        # Process srcset everywhere (img, picture > source, link
        # imagesrcset, lazy-load data-srcset): every candidate is rewritten
        # and downloaded, since the browser may pick any of them over src.
        for attr_name in ("srcset", "imagesrcset", "data-srcset"):
            for element in soup.find_all(attrs={attr_name: True}):
                srcset = element.get(attr_name, "")
                if isinstance(srcset, str) and srcset.strip():
                    element[attr_name] = self._rewrite_srcset(srcset, base_url, links_to_follow)

        # Process CSS links
        for link in soup.find_all("link", rel="stylesheet", href=True):
            href = link.get("href", "")
            if not href:
                continue
            # Keep original href before processing (for Google Fonts detection)
            original_href = href
            # Extract wayback URL first
            original = self._extract_original_url_from_path(href)
            if original:
                href = original
            # Keep original URL with query strings for downloading
            original_url = href
            # Normalize for checking and final output
            normalized_url = self._normalize_url(href, base_url)

            # Handle external links (e.g., Google Fonts, Squarespace CDN)
            # For Google Fonts and Squarespace CDN files available on Wayback Machine, download them
            # to ensure fonts and styles load correctly locally
            if not self._is_internal_url(normalized_url):
                # Check if this is a Google Fonts CSS file available on Wayback Machine
                # The original_href might be a wayback path like //web.archive.org/web/...cs_/http://fonts.googleapis.com/...
                is_google_font = _host_matches(normalized_url, self.GOOGLE_FONTS_CSS_HOSTS) or _host_matches(original_href, self.GOOGLE_FONTS_CSS_HOSTS)
                is_squarespace_cdn = self._is_squarespace_cdn(normalized_url) or self._is_squarespace_cdn(original_href)
                
                if is_google_font or is_squarespace_cdn:
                    # Extract original URL from wayback path if present (use original_href which has the wayback path)
                    original_resource_url = self._extract_original_url_from_path(original_href)
                    if not original_resource_url:
                        # If extraction failed, try using the already-extracted href
                        original_resource_url = href if (is_google_font and _host_matches(href, self.GOOGLE_FONTS_CSS_HOSTS)) or (is_squarespace_cdn and self._is_squarespace_cdn(href)) else None
                    if original_resource_url:
                        # Add to queue to download from Wayback Machine
                        links_to_follow.append(original_resource_url)
                        resource_type = "Google Fonts CSS" if is_google_font else "Squarespace CDN"
                        print(f"         📥 Queued {resource_type} for download: {original_resource_url[:80]}...", flush=True)
                        # Point the HTML at the file _get_local_path stores
                        # it as (for Google Fonts, css-<hash of query>.css).
                        if self.config.make_internal_links_relative:
                            target = original_resource_url
                            if not is_google_font:
                                target = urlparse(target)._replace(fragment="", query="").geturl()
                            link["href"] = self._get_relative_link_path(target, "asset")
                        else:
                            link["href"] = self._to_relative_path(
                                self._output_relative_url(self._get_local_path(original_resource_url))
                            )
                        continue
                
                # A stylesheet is part of the page, not a link to another
                # site: the external-link flags leave it. Drop the Wayback
                # prefix, which points nowhere offline.
                link["href"] = normalized_url if normalized_url.startswith(("http://", "https://")) else href
                continue

            # Note what this is before the branch: with relative links off
            # nothing below records it, and the download loop would treat an
            # extensionless stylesheet as a page.
            self._note_reference_kind(normalized_url, "stylesheet")

            if self.config.make_internal_links_relative:
                # CSS files are assets, preserve extension
                link["href"] = self._get_relative_link_path(normalized_url, "stylesheet")
            else:
                link["href"] = normalized_url

            if normalized_url not in self.config.visited_urls:
                links_to_follow.append(original_url)

        # Process script tags
        for script in soup.find_all("script", src=True):
            if script is None:
                continue
            src = script.get("src", "")
            if not src:
                continue
            # Extract wayback URL first
            original = self._extract_original_url_from_path(src)
            if original:
                src = original
            # Keep original URL with query strings for downloading
            original_url = src
            # Normalize for checking and final output
            normalized_url = self._normalize_url(src, base_url)

            if self._is_internal_url(normalized_url):
                self._note_reference_kind(normalized_url, "script")

                if self.config.make_internal_links_relative:
                    # JavaScript files are assets, preserve extension
                    script["src"] = self._get_relative_link_path(normalized_url, "script")
                else:
                    script["src"] = normalized_url

                if normalized_url not in self.config.visited_urls:
                    links_to_follow.append(original_url)

        # Process SVG use elements with xlink:href attributes
        for use_elem in soup.find_all("use"):
            xlink_href = use_elem.get("xlink:href") or use_elem.get("href")
            original_xlink = str(xlink_href) if xlink_href else ""
            if xlink_href:
                # Extract wayback URL if present
                original = self._extract_original_url_from_path(str(xlink_href))
                if original:
                    xlink_href = original
                # Remove wayback paths from xlink:href - just keep the fragment/anchor
                # Format: /web/20250818034506im_/https://qqnailspa.com/#email-icon -> #email-icon
                if "/web/" in original_xlink:
                    # Extract just the fragment part
                    if "#" in str(xlink_href):
                        target, fragment = str(xlink_href).split("#", 1)
                        fragment = "#" + fragment
                        # Remove query params from fragment if present
                        if "?" in fragment:
                            fragment = fragment.split("?")[0]
                        # <use> can only point into an SVG document. A page
                        # URL means a symbol on this page; anything else is a
                        # sprite file, which is kept and downloaded.
                        normalized_target = self._normalize_url(target, base_url)
                        if (
                            target
                            and not self._is_html_url(normalized_target)
                            and self._is_internal_url(normalized_target)
                        ):
                            if self.config.make_internal_links_relative:
                                fragment = self._get_relative_link_path(normalized_target, "image") + fragment
                            else:
                                fragment = normalized_target + fragment
                            if normalized_target not in self.config.visited_urls:
                                links_to_follow.append(normalized_target)
                        use_elem["xlink:href"] = fragment
                        if use_elem.get("href"):
                            use_elem["href"] = fragment
                    elif str(xlink_href).startswith("#"):
                        # Already a fragment, just clean it
                        fragment = str(xlink_href).split("?")[0] if "?" in str(xlink_href) else str(xlink_href)
                        use_elem["xlink:href"] = fragment
                        if use_elem.get("href"):
                            use_elem["href"] = fragment

        # Process other link tags (favicon, etc.) - but skip stylesheets as they're handled above
        for link in soup.find_all("link", href=True):
            if link is None:
                continue
            link_rel = link.get("rel")
            # Skip stylesheets as they're already processed above
            if link_rel and (link_rel == ["stylesheet"] or (isinstance(link_rel, list) and "stylesheet" in link_rel)):
                continue
            href = link.get("href", "")
            if not href:
                continue
            # Extract wayback URL first
            original = self._extract_original_url_from_path(href)
            if original:
                href = original
            normalized_url = self._normalize_url(href, base_url)

            is_squarespace_cdn = self._is_squarespace_cdn(normalized_url)
            if self._is_internal_url(normalized_url) or is_squarespace_cdn:
                if self.config.make_internal_links_relative:
                    if is_squarespace_cdn:
                        parsed_asset = urlparse(normalized_url)
                        asset_path = f"{parsed_asset.netloc}{parsed_asset.path}"
                        if parsed_asset.query:
                            asset_path += "?" + parsed_asset.query
                        while asset_path.startswith("/"):
                            asset_path = asset_path[1:]
                        link["href"] = self._to_relative_path(f"/{asset_path}")
                    else:
                        link["href"] = self._make_relative_path(normalized_url)
                else:
                    link["href"] = normalized_url

                if normalized_url not in self.config.visited_urls:
                    links_to_follow.append(normalized_url)

        # Process inline styles (background-image, etc.)
        for element in soup.find_all(style=True):
            style = element["style"]
            # Extract URLs from inline styles
            style_urls = self._extract_css_urls(style, base_url)
            for style_url in style_urls:
                is_squarespace_cdn = self._is_squarespace_cdn(style_url)
                if style_url not in self.config.visited_urls and (self._is_internal_url(style_url) or is_squarespace_cdn):
                    links_to_follow.append(style_url)
            
            # Rewrite URLs in inline styles. This is the same job
            # _rewrite_css_urls already does for <style> blocks and .css files.
            # The hand-rolled version that used to live here only matched
            # Wayback-form URLs, so a plain url(http://site/bg.png) was
            # downloaded but never repointed at the local copy - the archived
            # page kept calling out to the live site.
            if "web.archive.org" in style or "/web/" in style or "url(" in style:
                new_style = self._rewrite_css_urls(style, base_url)
                # Remove references to corrupted fonts from inline styles
                new_style = self._remove_corrupted_fonts_from_css(new_style)
                element["style"] = new_style

        # Process <style> tags in HTML (not just inline styles)
        for style_tag in soup.find_all("style"):
            if style_tag.string:
                css_content = style_tag.string
                # Extract URLs from style tag content
                style_urls = self._extract_css_urls(css_content, base_url)
                for style_url in style_urls:
                    is_squarespace_cdn = self._is_squarespace_cdn(style_url)
                    if style_url not in self.config.visited_urls and (self._is_internal_url(style_url) or is_squarespace_cdn):
                        links_to_follow.append(style_url)
                
                # Rewrite URLs in style tag CSS
                css_content = self._rewrite_css_urls(css_content, base_url)
                # Remove references to corrupted fonts
                css_content = self._remove_corrupted_fonts_from_css(css_content)
                style_tag.string = css_content

        # The two passes below rewrite URLs left in any attribute. Whatever
        # they point at locally has to be downloaded too, except navigation
        # (<a>, <form>, <base>, <link>), which the passes above handle.
        def rewrite_attr_url(element, attr_name, attr_value):
            # Extract original URL if it's a wayback path
            original = self._extract_original_url_from_path(attr_value)
            if original:
                attr_value = original

            # Normalize and convert to relative path if internal or Squarespace CDN
            normalized = self._normalize_url(attr_value, base_url)
            is_sqcdn_norm = self._is_squarespace_cdn(normalized)
            if not (self._is_internal_url(normalized) or is_sqcdn_norm):
                return
            kind = "image" if attr_name == "poster" or element.name in ("img", "image", "input") else "asset"
            if self.config.make_internal_links_relative:
                if is_sqcdn_norm:
                    parsed_asset = urlparse(normalized)
                    asset_path = f"{parsed_asset.netloc}{parsed_asset.path}"
                    if parsed_asset.query:
                        asset_path += "?" + parsed_asset.query
                    while asset_path.startswith("/"):
                        asset_path = asset_path[1:]
                    element[attr_name] = self._to_relative_path(f"/{asset_path}")
                else:
                    element[attr_name] = self._get_relative_link_path(normalized, kind)
            else:
                # Keep normalized URL but ensure it uses the correct scheme
                element[attr_name] = normalized
                if kind == "image":
                    self._note_reference_kind(normalized, kind)
            if element.name not in ("a", "form", "base", "link") and normalized not in self.config.visited_urls:
                links_to_follow.append(attr_value)

        # Process data-* attributes that contain URLs (e.g., data-video_src, data-src, data-href, etc.)
        # Convert domain URLs to relative paths to match Wayback Machine behavior
        for element in soup.find_all(True):  # All elements
            if not hasattr(element, 'attrs') or not element.attrs:
                continue
            for attr_name, attr_value in list(element.attrs.items()):
                if attr_name.startswith('data-') and isinstance(attr_value, str) and self._is_single_url_attr(attr_name, attr_value):
                    # Check if attribute contains a domain URL
                    if (self.config.domain and self.config.domain in attr_value) or self._is_squarespace_cdn(attr_value):
                        rewrite_attr_url(element, attr_name, attr_value.strip())

        # Convert any remaining domain references in text content and attributes to relative paths
        # This handles cases where domain URLs appear in href, src, or other attributes
        parsed_base = urlparse(base_url)
        base_domain = parsed_base.netloc.lower().removeprefix("www.")
        
        for element in soup.find_all(True):  # All elements
            for attr_name, attr_value in list(element.attrs.items()):
                if not (isinstance(attr_value, str) and self._is_single_url_attr(attr_name, attr_value)):
                    continue
                attr_value = attr_value.strip()
                if base_domain in attr_value.lower() or self._is_squarespace_cdn(attr_value) or "web.archive.org" in attr_value or attr_value.startswith("/web/"):
                    # Check if it's a full URL with the domain or a Squarespace CDN URL
                    is_squarespace_cdn = self._is_squarespace_cdn(attr_value)
                    if attr_value.startswith(("http://", "https://", "/web/")) or is_squarespace_cdn or "web.archive.org" in attr_value:
                        rewrite_attr_url(element, attr_name, attr_value)

        # Get processed HTML
        processed_html = str(soup)
        processed_html = self._optimize_html(processed_html)

        # Every append above records the reference as written, which may be
        # relative to this page. Resolve them here, in one place, so the
        # queue only ever holds absolute URLs.
        crawl_urls: List[str] = []
        for link_url in links_to_follow:
            crawl_url = self._crawl_url(link_url, base_url)
            if crawl_url and crawl_url not in crawl_urls:
                crawl_urls.append(crawl_url)

        return processed_html, crawl_urls

    def _tracking_key(self, url: str) -> str:
        """The visited/queued key for a URL: the file it is stored as."""
        try:
            return str(self._get_local_path(url))
        except UnsafeOutputPathError:
            return url

    def _crawl_url(self, url: str, base_url: str) -> Optional[str]:
        """
        The absolute URL to fetch for a reference found on a page.

        Wayback's if_ replay leaves relative links as written, and a raw
        "foo/" sent to Wayback is read as the host "foo".

        Args:
            url: The reference as written, possibly a Wayback path.
            base_url: The URL of the page carrying the reference.

        Returns:
            An absolute http(s) URL without fragment, or None for references
            that name nothing to fetch (data:, mailto:, "#top", ...).
        """
        url = (url or "").strip()
        if not url or url.startswith("#") or url.lower().startswith(self.NON_FETCHABLE_PREFIXES):
            return None
        url = self._extract_original_url_from_path(url) or url
        parsed = urlparse(urljoin(base_url, url))
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return None
        return parsed._replace(fragment="").geturl()

    MAX_CONSECUTIVE_REFUSALS = 5

    def _follow_start_redirect(self, url: str) -> str:
        """When the start capture redirected to another host, crawl that host.

        Otherwise every link on the page looks external and the archive is
        one broken page. Returns the URL the page actually came from.
        """
        final = self._extract_original_url_from_path(self._last_final_url or "")
        if not final:
            return url
        parsed = urlparse(final)
        host = self._strip_default_port(parsed.netloc.lower(), parsed.scheme)
        if not host or host.removeprefix("www.") == self.config.domain.lower().removeprefix("www."):
            return url
        print(f"         ⚠️  The capture of {url} redirects to {final}; archiving {host} instead", flush=True)
        self.config.base_url = final
        self.config.domain = host
        return final

    def download(self):
        """Main download method."""
        # Create output directory
        Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)

        # Start with the main page
        start_url = self.config.base_url
        queue = [start_url]
        # Visited and queued URLs are keyed by the file they are stored as:
        # http/https and www twins, or ?v= cache-busters, are one file and are
        # fetched once, while each Google Fonts family set has its own file.
        queued_keys = {self._tracking_key(self.config.base_url)}

        def enqueue(link_url: str) -> None:
            key = self._tracking_key(link_url)
            if key not in self.config.visited_urls and key not in queued_keys:
                queued_keys.add(key)
                queue.append(link_url)

        files_downloaded = 0
        files_failed = 0
        files_skipped = 0
        # Requests in a row that Wayback throttled or did not answer. Past
        # MAX_CONSECUTIVE_REFUSALS the run stops rather than hammer it.
        consecutive_refusals = 0
        stop_reason = None

        print(f"\n{'='*70}", flush=True)
        print(f"Wayback-Archive Downloader", flush=True)
        print(f"{'='*70}", flush=True)
        print(f"Starting URL: {self.config.base_url}", flush=True)
        print(f"Output directory: {self.config.output_dir}", flush=True)
        if self.config.max_files:
            print(f"⚠️  TEST MODE: Limited to {self.config.max_files} files", flush=True)
        print(f"{'='*70}\n", flush=True)

        while queue:
            # Check if we've reached the file limit (for testing). Failed
            # attempts count too, or a limited run could make hundreds of
            # requests past the limit.
            if self.config.max_files and len(self.config.visited_urls) >= self.config.max_files:
                print(f"\n{'='*70}", flush=True)
                print(f"⚠️  Reached MAX_FILES limit ({self.config.max_files}) - stopping download", flush=True)
                print(f"{'='*70}", flush=True)
                break
            
            queue_size = len(queue)
            url = queue.pop(0)
            
            # Skip fragment-only URLs (like #page, #section, etc.)
            if url.startswith("#"):
                continue
            
            try:
                local_path = self._get_local_path(url)
            except UnsafeOutputPathError as e:
                # Archived content asked us to write outside OUTPUT_DIR. Skip
                # this file and keep archiving the rest of the site.
                files_failed += 1
                print(f"         ⛔ Refused unsafe path for {url}: {e}", flush=True)
                continue
            normalized_for_tracking = str(local_path)

            if normalized_for_tracking in self.config.visited_urls:
                files_skipped += 1
                continue

            # Show status
            file_type = self._get_file_type_from_url(url)
            current_file_num = len(self.config.visited_urls) + 1
            limit_info = f" (limit: {self.config.max_files})" if self.config.max_files else ""
            print(f"[{current_file_num}{limit_info}] Downloading {file_type}: {url}", flush=True)
            if queue_size > 1:
                print(f"         Queue: {queue_size - 1} files remaining", flush=True)
            
            self.config.visited_urls.add(normalized_for_tracking)

            content = self.download_file(url)
            refusal = self._last_failure
            if content or not refusal:
                consecutive_refusals = 0
            if not content:
                # Try CDN fallback for critical jQuery files if Wayback fails:
                # the version the URL names (x.y also as x.y.0), then 3.7.1.
                # A ?ver= is often WordPress's version, not jQuery's.
                if "jquery.min.js" in url.lower() and "cdn" not in url.lower():
                    match = re.search(
                        r"jquery[-./@]?v?(\d+\.\d+(?:\.\d+)?)|[?&]ver=(\d+\.\d+(?:\.\d+)?)", url, re.I
                    )
                    versions = []
                    if match:
                        named = match.group(1) or match.group(2)
                        versions = [named] + ([named + ".0"] if named.count(".") == 1 else [])
                    for version in dict.fromkeys(versions + ["3.7.1"]):
                        if version == "3.7.1" and "3.7.1" not in versions:
                            print(f"         jQuery version unknown or not on code.jquery.com; substituting 3.7.1", flush=True)
                        content = self._fetch_from_live_cdn(f"https://code.jquery.com/jquery-{version}.min.js")
                        if content:
                            break
                
                if not content:
                    files_failed += 1
                    print(f"         ⚠️  Failed to download", flush=True)
                    # Only a file no fallback could save counts as refused.
                    if refusal:
                        consecutive_refusals += 1
                        if consecutive_refusals >= self.MAX_CONSECUTIVE_REFUSALS:
                            stop_reason = (
                                f"Stopped: the Wayback Machine refused {consecutive_refusals} requests in a row "
                                f"(last: {refusal}); try again later"
                            )
                            break
                    continue

            if self._is_html_instead_of_asset(content, url):
                files_failed += 1
                print(f"         ⚠️  Failed: got an HTML page instead of the file", flush=True)
                continue
            if url == start_url:
                url = self._follow_start_redirect(url)
            charset = self._last_charset
            
            # Show file size
            size_kb = len(content) / 1024
            if size_kb < 1024:
                print(f"         ✓ Downloaded ({size_kb:.1f} KB)", flush=True)
            else:
                print(f"         ✓ Downloaded ({size_kb/1024:.1f} MB)", flush=True)
            
            files_downloaded += 1

            # Determine file type with robust detection
            try:
                parsed = urlparse(url)
                content_type, _ = mimetypes.guess_type(parsed.path)
                # A server-side page is whatever its script sent (mimetypes
                # calls .pl text/plain), so let the content decide.
                if os.path.splitext(parsed.path.lower())[1] in self.PAGE_EXTENSIONS:
                    content_type = None
                
                # Better content type detection from URL path
                # Check for Google Fonts CSS files first (they don't have .css extension)
                if self._is_google_fonts_css(url):
                    content_type = "text/css"
                elif not content_type:
                    path_lower = parsed.path.lower()
                    # Check for specific extensions
                    if path_lower.endswith(".css") or "/.css" in path_lower:
                        content_type = "text/css"
                    elif path_lower.endswith((".js", ".mjs")) or "/.js" in path_lower:
                        content_type = "application/javascript"
                    elif any(path_lower.endswith(ext) for ext in [".woff", ".woff2", ".ttf", ".eot", ".otf"]):
                        content_type = "font/woff2"  # Font file
                    elif any(path_lower.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp", ".tiff"]):
                        content_type = "image/jpeg"  # Default, will be refined from actual content
                    elif path_lower.endswith(".json"):
                        content_type = "application/json"
                    elif path_lower.endswith(".xml"):
                        content_type = "application/xml"
                    elif path_lower.endswith(".pdf"):
                        content_type = "application/pdf"
                    elif any(path_lower.endswith(ext) for ext in [".mp4", ".webm", ".ogg"]):
                        content_type = "video/mp4"
                    elif any(path_lower.endswith(ext) for ext in [".mp3", ".wav", ".ogg"]):
                        content_type = "audio/mpeg"
                
                # Try to detect from actual content if still unknown
                if not content_type and len(content) > 0:
                    content_stripped = content.lstrip()
                    if content_stripped.startswith((b'<!DOCTYPE', b'<!doctype', b'<html', b'<HTML')):
                        content_type = "text/html"
                    elif content_stripped.startswith((b'/*', b'@charset')) or b'@media' in content[:200]:
                        content_type = "text/css"
                    elif content_stripped.startswith(b'<?xml') or b'<svg' in content[:200]:
                        content_type = "image/svg+xml"
                    elif content.startswith(b'\x89PNG'):
                        content_type = "image/png"
                    elif content.startswith(b'\xff\xd8\xff'):
                        content_type = "image/jpeg"
                    elif content.startswith(b'GIF'):
                        content_type = "image/gif"
                    elif content.startswith(b'RIFF') and b'WEBP' in content[:12]:
                        content_type = "image/webp"
            except Exception as e:
                print(f"Warning: Error detecting content type for {url}: {e}")
                content_type = None
            
            try:
                local_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                # A name too long for the filesystem, or one already taken by
                # a file, costs this file only, not the rest of the run.
                files_downloaded -= 1
                files_failed += 1
                print(f"         ⛔ Cannot store {url}: {e}", flush=True)
                continue
            
            # A URL with no extension tells us nothing about its type, but the
            # element that referenced it does. Without this an extensionless
            # stylesheet sniffs as a page and gets rewritten as HTML - saved
            # under .css but wrapped in <body>, with its @import untouched.
            if not content_type:
                referenced_kind = self._kind_by_path.get(str(local_path))
                if referenced_kind == "stylesheet":
                    content_type = "text/css"
                elif referenced_kind == "script":
                    content_type = "application/javascript"

            try:
                # Check for Google Fonts CSS files first (they don't have .css extension)
                is_google_fonts_css = self._is_google_fonts_css(url)
                
                # Process based on content type - be more conservative about what we treat as HTML
                # A script can answer with a PDF, JSON or CSV, so a server-side
                # URL is a page only when its body is markup.
                is_html = (
                    not is_google_fonts_css and (
                        content_type == "text/html" or
                        (
                            not content_type
                            and self._is_html_url(url, parsed)
                            and (
                                os.path.splitext(parsed.path.lower())[1] not in self.PAGE_EXTENSIONS
                                or self._looks_like_markup(content)
                            )
                        )
                    )
                )
                
                if is_html:
                    # Process HTML
                    try:
                        print(f"         Processing HTML and extracting links...", flush=True)
                        # Saved as UTF-8; bs4 rewrites the <meta charset> to match.
                        html = self._decode_text(content, charset, is_html=True)

                        processed_html, new_links = self._process_html(html, url)
                        if new_links:
                            print(f"         Found {len(new_links)} new links to download", flush=True)
                    except Exception as e:
                        print(f"Error processing HTML for {url}: {e}")
                        import traceback
                        traceback.print_exc()
                        # Still save the raw HTML if processing fails
                        try:
                            with open(local_path, "wb") as f:
                                f.write(content)
                            self.config.downloaded_files[url] = str(local_path)
                        except Exception as save_error:
                            files_downloaded -= 1
                            files_failed += 1
                            print(f"Error saving file {local_path}: {save_error}")
                        continue

                    # Save HTML
                    try:
                        with open(local_path, "w", encoding="utf-8", errors="replace") as f:
                            f.write(processed_html)
                        self.config.downloaded_files[url] = str(local_path)
                    except Exception as e:
                        files_downloaded -= 1
                        files_failed += 1
                        print(f"Error saving HTML to {local_path}: {e}")
                        continue

                    for link_url in new_links:
                        enqueue(link_url)

                elif content_type == "text/css":
                    # Process CSS. It is saved as UTF-8, so its @charset has
                    # to say so or the browser decodes it the old way.
                    css = re.sub(
                        r'^\s*@charset\s+["\'][^"\']*["\']\s*;',
                        '@charset "utf-8";',
                        self._decode_text(content, charset),
                        count=1,
                        flags=re.IGNORECASE,
                    )
                    original_css = css
                    
                    try:
                        print(f"         Processing CSS and extracting resources...", flush=True)
                        # Extract URLs from CSS (images, fonts, @import, etc.)
                        css_urls = self._extract_css_urls(css, url)
                        if css_urls:
                            print(f"         Found {len(css_urls)} resources in CSS", flush=True)
                        for css_url in css_urls:
                            # Handle fonts.gstatic.com URLs - these are external but available on Wayback Machine
                            # They need to be downloaded to avoid CORS issues
                            is_google_font = _host_matches(css_url, self.GOOGLE_FONT_HOSTS)
                            is_squarespace_cdn = self._is_squarespace_cdn(css_url)
                            if self._is_internal_url(css_url) or is_google_font or is_squarespace_cdn:
                                queue_length = len(queue)
                                enqueue(css_url)
                                if is_google_font and len(queue) > queue_length:
                                    print(f"         📥 Queued Google Font file for download: {css_url[:80]}...", flush=True)
                        
                        # Check font URLs in CSS and detect corrupted ones proactively,
                        # while the CSS still names the real URLs. This ensures we
                        # catch corrupted fonts even if they haven't been downloaded yet
                        css = self._check_and_remove_corrupted_fonts_in_css(css, url)

                        # Rewrite URLs in CSS to relative paths. A stylesheet's
                        # url() references resolve against the stylesheet's own
                        # location, so make that the current page for the
                        # rewrite - otherwise every link is computed from
                        # whichever HTML page happened to be processed last.
                        previous_page_url = getattr(self, "_current_page_url", None)
                        self._current_page_url = url
                        try:
                            css = self._rewrite_css_urls(css, url)
                        finally:
                            self._current_page_url = previous_page_url
                        
                        # Remove references to already-detected corrupted fonts
                        css = self._remove_corrupted_fonts_from_css(css)
                        
                        # Proactively remove .eot and .svg font format references
                        # These are often corrupted (HTML error pages) and modern browsers don't need them
                        # Browsers will use .woff2, .woff, and .ttf which are more reliable
                        css = self._remove_legacy_font_formats_from_css(css)
                        
                        css = self._minify_css(css)
                    except Exception as e:
                        print(f"Warning: Error processing CSS for {url}: {e}")
                        # Use original content if processing fails
                        css = original_css

                    try:
                        with open(local_path, "w", encoding="utf-8", errors="replace") as f:
                            f.write(css)
                        self.config.downloaded_files[url] = str(local_path)
                    except Exception as e:
                        files_downloaded -= 1
                        files_failed += 1
                        print(f"Error saving CSS to {local_path}: {e}")
                        continue

                elif content_type in ("application/javascript", "text/javascript"):
                    # Process JavaScript
                    js = self._decode_text(content, charset)
                    
                    print(f"         Processing JavaScript and extracting URLs...", flush=True)
                    # Extract URLs from JavaScript (may contain fetch, XMLHttpRequest, etc.)
                    js_urls = self._extract_js_urls(js, url)
                    if js_urls:
                        print(f"         Found {len(js_urls)} URLs in JavaScript", flush=True)
                    for js_url in js_urls:
                        if self._is_internal_url(js_url):
                            enqueue(js_url)
                    
                    js = self._minify_js(js)

                    with open(local_path, "w", encoding="utf-8") as f:
                        f.write(js)

                    self.config.downloaded_files[url] = str(local_path)

                elif content_type and content_type.startswith("image/"):
                    # Process images
                    format_map = {
                        "image/jpeg": "JPEG",
                        "image/png": "PNG",
                        "image/gif": "GIF",
                        "image/webp": "WEBP",
                    }
                    img_format = format_map.get(content_type, "JPEG")
                    optimized = self._optimize_image(content, img_format)

                    with open(local_path, "wb") as f:
                        f.write(optimized)

                    self.config.downloaded_files[url] = str(local_path)

                elif content_type and content_type.startswith("font/"):
                    # Save font files as-is
                    with open(local_path, "wb") as f:
                        f.write(content)
                    self.config.downloaded_files[url] = str(local_path)

                else:
                    # Save as-is
                    with open(local_path, "wb") as f:
                        f.write(content)

                    self.config.downloaded_files[url] = str(local_path)
            except Exception as e:
                # One file that cannot be processed or written fails alone.
                files_downloaded -= 1
                files_failed += 1
                print(f"Error processing {url}: {e}")
                continue

        if files_downloaded == 0 and not stop_reason:
            # The start page failed, so nothing else was found. Say so rather
            # than report an empty archive as complete.
            raise RuntimeError(
                f"Nothing was saved: no usable capture of {self.config.base_url} could be downloaded"
            )

        print(f"\n{'='*70}", flush=True)
        print(f"Download stopped early" if stop_reason else f"Download Complete!", flush=True)
        print(f"{'='*70}", flush=True)
        print(f"Output directory: {self.config.output_dir}", flush=True)
        print(f"Files successfully downloaded: {files_downloaded}", flush=True)
        print(f"Files failed: {files_failed}", flush=True)
        print(f"Files skipped (duplicates): {files_skipped}", flush=True)
        if self.corrupted_fonts:
            print(f"Corrupted fonts detected and removed: {len(self.corrupted_fonts)}", flush=True)
        print(f"Total files processed: {len(self.config.visited_urls)}", flush=True)
        print(f"{'='*70}\n", flush=True)
        if stop_reason:
            raise RuntimeError(stop_reason)

