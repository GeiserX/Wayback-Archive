"""Core downloader module for Wayback-Archive."""

import os
import re
import mimetypes
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse, unquote
from pathlib import Path
from typing import Optional, Set, Dict, List, Tuple
import requests
from bs4 import BeautifulSoup, Comment
from wayback_archive.config import Config


class WaybackDownloader:
    """Main downloader class for Wayback Machine archives."""

    # Common tracker/analytics patterns
    TRACKER_PATTERNS = [
        r"google-analytics\.com",
        r"googletagmanager\.com",
        r"facebook\.net",
        r"doubleclick\.net",
        r"googleads\.g\.doubleclick\.net",
        r"googlesyndication\.com",
        r"facebook\.com/tr",
        r"analytics\.",
        r"stats\.",
        r"tracking\.",
        r"tagmanager\.google\.com",
        r"gtag\.js",
        r"ga\.js",
        r"analytics\.js",
    ]

    # Common ad patterns
    AD_PATTERNS = [
        r"ads\.",
        r"advertising\.com",
        r"doubleclick\.net",
        r"googlesyndication\.com",
        r"googleads\.",
        r"adserver\.",
        r"banner",
        r"popup",
        r"sponsor",
    ]

    # Contact link patterns
    CONTACT_PATTERNS = [
        r"^mailto:",
        r"^tel:",
        r"^sms:",
        r"^whatsapp:",
        r"^callto:",
    ]

    def __init__(self, config: Config):
        """Initialize downloader with configuration."""
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
        self._parse_wayback_url()

    def _parse_wayback_url(self):
        """Parse the Wayback Machine URL to extract the original URL."""
        # Extract timestamp and URL from Wayback URL
        # Format: https://web.archive.org/web/TIMESTAMP/URL
        match = re.match(
            r"https?://web\.archive\.org/web/(\d+[a-z]*)/(.+)", self.config.wayback_url
        )
        if match:
            timestamp, original_url = match.groups()
            # Ensure original_url starts with http/https
            if not original_url.startswith(("http://", "https://")):
                original_url = "http://" + original_url
            self.config.base_url = original_url
            self.config.domain = urlparse(original_url).netloc
            # Store original timestamp for timeframe fallback
            self.original_timestamp = timestamp
            # Parse timestamp to datetime for timeframe calculations
            try:
                numeric_part = re.match(r'(\d+)', timestamp).group(1)
                if len(numeric_part) >= 14:
                    self.original_datetime = datetime.strptime(numeric_part[:14], '%Y%m%d%H%M%S')
                else:
                    # Pad with zeros if needed
                    padded = numeric_part + '0' * (14 - len(numeric_part))
                    self.original_datetime = datetime.strptime(padded, '%Y%m%d%H%M%S')
            except (ValueError, AttributeError):
                # Fallback to current time if parsing fails
                self.original_datetime = datetime.now()
        else:
            raise ValueError(f"Invalid Wayback URL format: {self.config.wayback_url}")

    def _is_internal_url(self, url: str) -> bool:
        """Check if URL is internal to the site."""
        parsed = urlparse(url)
        url_domain = parsed.netloc.lower().lstrip("www.")
        base_domain = self.config.domain.lower().lstrip("www.")
        return url_domain == base_domain or url_domain == ""

    def _is_tracker(self, url: str) -> bool:
        """Check if URL is a tracker/analytics script."""
        for pattern in self.TRACKER_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False

    def _is_ad(self, url: str) -> bool:
        """Check if URL is an ad."""
        for pattern in self.AD_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        return False

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
    
    def _convert_to_wayback_url_with_timestamp(self, url: str, timestamp: str = None) -> str:
        """Convert a regular URL to a Wayback Machine URL with optional timestamp.
        
        Args:
            url: The original URL
            timestamp: Optional timestamp (YYYYMMDDHHMMSS). If None, uses original timestamp.
        """
        if url.startswith("http://web.archive.org") or url.startswith("https://web.archive.org"):
            return url
        
        if timestamp is None:
            timestamp = self.original_timestamp
        
        # Determine asset type prefix (im_, cs_, js_)
        parsed = urlparse(url)
        path = parsed.path.lower()
        asset_prefix = ""
        if any(ext in path for ext in [".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp"]):
            asset_prefix = "im_"
        elif any(ext in path for ext in [".css"]):
            asset_prefix = "cs_"
        elif any(ext in path for ext in [".js"]):
            asset_prefix = "js_"
        
        if asset_prefix:
            return f"https://web.archive.org/web/{timestamp}{asset_prefix}/{url}"
        return f"https://web.archive.org/web/{timestamp}/{url}"

    def _make_relative_path(self, url: str) -> str:
        """Convert absolute URL to relative path."""
        parsed = urlparse(url)
        path = parsed.path
        if parsed.query:
            path += "?" + parsed.query
        if parsed.fragment:
            path += "#" + parsed.fragment
        return path or "/"

    def _extract_original_url_from_path(self, path: str) -> Optional[str]:
        """Extract original URL from Wayback Machine path in HTML."""
        if not path or not isinstance(path, str):
            return None
        
        try:
            # Handle protocol-relative URLs: //web.archive.org/web/...
            if path.startswith("//"):
                path = "https:" + path
            
            # Pattern: /web/TIMESTAMPim_/https://original.com/path or /web/TIMESTAMPcs_/ or /web/TIMESTAMPjs_/ or /web/TIMESTAMPjm_/
            wayback_asset_pattern = r"/web/\d+[a-z]*(?:im_|cs_|js_|jm_)/(https?://[^\"\s'<>\)]+)"
            match = re.search(wayback_asset_pattern, path)
            if match:
                extracted = match.group(1)
                # Clean up any trailing characters that might have been captured
                extracted = extracted.rstrip('.,;:)\'"')
                return extracted
            
            # Pattern: /web/TIMESTAMP/https://original.com/path (for pages)
            wayback_page_pattern = r"/web/\d+[a-z]*/(https?://[^\"\s'<>\)]+)"
            match = re.search(wayback_page_pattern, path)
            if match:
                extracted = match.group(1)
                extracted = extracted.rstrip('.,;:)\'"')
                return extracted
            
            # Pattern for mailto:/tel:/whatsapp: in wayback URLs
            wayback_protocol_pattern = r"/web/\d+[a-z]*/(mailto:|tel:|whatsapp:|sms:|callto:)(.+)"
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
        if url.startswith("//"):
            url = "https:" + url

        parsed = urlparse(url)

        # Handle www/non-www conversion
        if self.config.make_non_www and parsed.netloc.startswith("www."):
            parsed = parsed._replace(netloc=parsed.netloc[4:])
        elif self.config.make_www and not parsed.netloc.startswith("www.") and parsed.netloc:
            parsed = parsed._replace(netloc="www." + parsed.netloc)

        # Remove fragment and query string for file identification
        # This ensures URLs with different query params or fragments point to the same file
        url_normalized = parsed._replace(fragment="", query="").geturl()

        return url_normalized

    def _get_local_path(self, url: str) -> Path:
        """
        Get local file path for a URL.
        This ensures consistent file naming that works with static file servers.
        Files are saved without query strings or fragments for clean URLs.
        """
        parsed = urlparse(url)
        path = unquote(parsed.path)
        
        # Remove leading slash
        if path.startswith("/"):
            path = path[1:]

        # Default to index.html for directories
        if not path or path.endswith("/"):
            path = "index.html"

        # Determine if this is likely a page (HTML) or an asset
        # Check if it has a known asset extension
        known_asset_extensions = {
            ".css", ".js", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", 
            ".ico", ".woff", ".woff2", ".ttf", ".eot", ".otf", ".pdf", ".zip",
            ".mp4", ".mp3", ".avi", ".mov", ".wmv", ".flv", ".pdf", ".doc", ".docx"
        }
        
        has_extension = "." in os.path.basename(path)
        is_asset = False
        if has_extension:
            ext = os.path.splitext(path)[1].lower()
            is_asset = ext in known_asset_extensions

        # Add .html extension if no extension and it's not an asset (treat as page)
        if not has_extension and not is_asset:
            # If the path doesn't have a file extension, treat it as a page
            dir_part = os.path.dirname(path) if os.path.dirname(path) else ""
            base_part = os.path.basename(path) if os.path.basename(path) else "index"
            if dir_part:
                path = os.path.join(dir_part, base_part + ".html")
            else:
                path = base_part + ".html"

        return Path(self.config.output_dir) / path
    
    def _get_relative_link_path(self, url: str, is_page: bool = True) -> str:
        """
        Get relative link path that matches where the file will be saved.
        This ensures href/src attributes point to the correct file paths.
        
        Args:
            url: The normalized URL to convert
            is_page: If True, adds .html extension to paths without extensions.
                     If False, preserves the original extension (for assets).
        """
        parsed = urlparse(url)
        path = unquote(parsed.path)
        
        # Keep leading slash for absolute paths from root
        # Python's http.server handles leading slashes correctly
        
        # Default to / for root
        if not path or path.endswith("/"):
            return "/"
        
        # Determine if this has an asset extension (for better detection)
        known_asset_extensions = {
            ".css", ".js", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", 
            ".ico", ".woff", ".woff2", ".ttf", ".eot", ".otf", ".pdf", ".zip",
            ".mp4", ".mp3", ".avi", ".mov", ".wmv", ".flv", ".pdf", ".doc", ".docx"
        }
        
        has_extension = "." in os.path.basename(path)
        is_asset = False
        if has_extension:
            ext = os.path.splitext(path)[1].lower()
            is_asset = ext in known_asset_extensions
        
        # For pages without extensions, add .html to match saved file
        # For assets, preserve original extension
        # Only add .html if explicitly a page AND has no extension
        if is_page and not has_extension and not is_asset:
            # Add .html extension to match saved file
            path = path + ".html"
        elif not is_page and not has_extension:
            # For assets without extension, preserve as-is (let server handle it)
            pass
        
        # Ensure leading slash for absolute paths
        if not path.startswith("/"):
            path = "/" + path
        
        # Preserve query string and fragment if present
        # These are preserved in links even though files are saved without them
        if parsed.query:
            path += "?" + parsed.query
        if parsed.fragment:
            path += "#" + parsed.fragment
        
        return path

    def _generate_timestamp_variants(self, hours_range: int = 24, step_hours: int = 1) -> List[str]:
        """Generate timestamp variants for timeframe search.
        
        Args:
            hours_range: How many hours before/after to search
            step_hours: Step size in hours between attempts
            
        Returns:
            List of timestamp strings (YYYYMMDDHHMMSS format)
        """
        timestamps = []
        base_time = self.original_datetime
        
        # Try timestamps before and after the original
        for hours_offset in range(-hours_range, hours_range + 1, step_hours):
            if hours_offset == 0:
                continue  # Skip the original timestamp (already tried)
            variant_time = base_time + timedelta(hours=hours_offset)
            timestamp_str = variant_time.strftime('%Y%m%d%H%M%S')
            timestamps.append(timestamp_str)
        
        # Sort by proximity to original (closest first)
        timestamps.sort(key=lambda ts: abs((datetime.strptime(ts, '%Y%m%d%H%M%S') - base_time).total_seconds()))
        
        return timestamps

    def _convert_to_wayback_url_with_timestamp(self, url: str, timestamp: str = None) -> str:
        """Convert a regular URL to a Wayback Machine URL with optional timestamp.
        
        Args:
            url: The original URL
            timestamp: Optional timestamp (YYYYMMDDHHMMSS). If None, uses original timestamp.
        """
        if url.startswith("http://web.archive.org") or url.startswith("https://web.archive.org"):
            return url
        
        if timestamp is None:
            timestamp = self.original_timestamp
        
        # Determine asset type prefix (im_, cs_, js_)
        parsed = urlparse(url)
        path = parsed.path.lower()
        asset_prefix = ""
        if any(ext in path for ext in [".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico", ".bmp"]):
            asset_prefix = "im_"
        elif any(ext in path for ext in [".css"]):
            asset_prefix = "cs_"
        elif any(ext in path for ext in [".js"]):
            asset_prefix = "js_"
        
        if asset_prefix:
            return f"https://web.archive.org/web/{timestamp}{asset_prefix}/{url}"
        return f"https://web.archive.org/web/{timestamp}/{url}"

    def download_file(self, url: str) -> Optional[bytes]:
        """Download a file from the given URL with timeframe fallback.
        
        If the file returns 404, tries nearby timestamps (hours before/after).
        Expands search window if still not found.
        """
        # Try original timestamp first
        wayback_url = self._convert_to_wayback_url_with_timestamp(url)
        try:
            response = self.session.get(
                wayback_url, timeout=30, allow_redirects=self.config.keep_redirections
            )
            response.raise_for_status()
            return response.content
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                # File not found, try timeframe fallback
                print(f"File not found at original timestamp, searching nearby timestamps for {url}...")
                
                # Start with small range and expand
                found = False
                for search_range in [6, 24, 72, 168]:  # 6h, 24h, 3d, 1w
                    timestamps = self._generate_timestamp_variants(hours_range=search_range, step_hours=max(1, search_range // 12))
                    
                    for timestamp in timestamps[:10]:  # Limit to 10 closest variants per range
                        try:
                            variant_url = self._convert_to_wayback_url_with_timestamp(url, timestamp)
                            variant_response = self.session.get(
                                variant_url, timeout=30, allow_redirects=self.config.keep_redirections
                            )
                            if variant_response.status_code == 200:
                                print(f"  Found at timestamp {timestamp} (offset: {(datetime.strptime(timestamp, '%Y%m%d%H%M%S') - self.original_datetime).total_seconds() / 3600:.1f}h)")
                                found = True
                                return variant_response.content
                        except requests.exceptions.RequestException:
                            continue
                    
                    # If found in this range, break outer loop
                    if found:
                        break
                
                if not found:
                    print(f"  Could not find {url} in nearby timeframes")
            else:
                # Other HTTP error
                print(f"Error downloading {url}: {e}")
        except Exception as e:
            print(f"Error downloading {url}: {e}")
        
        return None

    def _optimize_html(self, html: str) -> str:
        """Optimize HTML code."""
        if not self.config.optimize_html:
            return html

        try:
            import htmlmin

            return htmlmin.minify(
                html,
                remove_comments=True,
                remove_empty_space=True,
                remove_all_empty_space=False,
                reduce_empty_attributes=True,
                reduce_boolean_attributes=True,
            )
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
                normalized = self._normalize_url(css_url, base_url)
                if normalized not in urls:
                    urls.append(normalized)
        
        return urls

    def _rewrite_css_urls(self, css: str, base_url: str) -> str:
        """Rewrite URLs in CSS to relative paths."""
        def replace_css_url(match):
            full_match = match.group(0)
            url_part = match.group(1)
            
            # Extract original URL from wayback path
            original = self._extract_original_url_from_path(url_part)
            if original:
                url_part = original
            
            normalized = self._normalize_url(url_part, base_url)
            
            if self._is_internal_url(normalized):
                if self.config.make_internal_links_relative:
                    new_path = self._make_relative_path(normalized)
                    return f"url({new_path})"
                return f"url({normalized})"
            
            return full_match
        
        # Pattern to match url() with wayback URLs
        url_patterns = [
            r'url\s*\(\s*["\']?(/web/\d+[a-z]*(?:im_|cs_|js_|jm_)/https?://[^"\'()]+)["\']?\s*\)',  # Relative wayback
            r'url\s*\(\s*["\']?(https?://web\.archive\.org/web/\d+[a-z]*(?:im_|cs_|js_|jm_)/https?://[^"\'()]+)["\']?\s*\)',  # Absolute wayback
            r'url\s*\(\s*["\']?(https?://[^"\'()]+)["\']?\s*\)',  # Regular URLs
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

    def _process_html(self, html: str, base_url: str) -> tuple[str, List[str]]:
        """Process HTML content and extract links."""
        soup = BeautifulSoup(html, "lxml")
        links_to_follow: List[str] = []

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
        for script in soup.find_all("script", src=True):
            src = script.get("src", "")
            if "web.archive.org" in src or "web-static.archive.org" in src or "bundle-playback.js" in src or "wombat.js" in src or "ruffle.js" in src:
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
        
        # Remove comments
        for comment in soup.findAll(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Remove trackers and analytics
        if self.config.remove_trackers:
            for script in soup.find_all("script", src=True):
                if script is None:
                    continue
                script_src = script.get("src")
                if script_src and self._is_tracker(script_src):
                    script.decompose()

            # Remove inline tracking scripts (Google Analytics, gtag, dataLayer, cookie consent)
            for script in soup.find_all("script"):
                if script.string:
                    script_text = script.string.lower()
                    if any(pattern in script_text for pattern in self.TRACKER_PATTERNS + [
                        "gtag", "datalayer", "google-analytics", "cookieyes", "cookie consent",
                        "cookie banner", "cookiebar"
                    ]):
                        script.decompose()
            
            # Remove cookie consent divs/banners
            for element in soup.find_all(["div", "section"], class_=True):
                element_classes = element.get("class")
                if element_classes:
                    classes = " ".join(element_classes if isinstance(element_classes, list) else [element_classes]).lower()
                    if any(banner in classes for banner in ["cookie", "consent", "cookiebar", "cookie-banner", "cookieyes"]):
                        element.decompose()
            
            # Remove cookie consent buttons/links
            for element in soup.find_all(["button", "a"], class_=True):
                element_classes = element.get("class")
                if element_classes:
                    classes = " ".join(element_classes if isinstance(element_classes, list) else [element_classes]).lower()
                    if any(btn in classes for btn in ["cookie", "consent", "accept", "reject"]):
                        element.decompose()

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

        # Process links
        for link in soup.find_all("a", href=True):
            if link is None:
                continue
            href = link.get("href", "")
            if not href:
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
            normalized_url = self._normalize_url(href, base_url)

            # Handle contact links (but preserve floating buttons - already handled above)
            if self.config.remove_clickable_contacts and self._is_contact_link(href) and not is_floating_button:
                if self.config.remove_external_links_remove_anchors:
                    link.decompose()
                else:
                    link["href"] = "#"
                continue

            # Handle external links (but preserve floating button contact links)
            if not self._is_internal_url(normalized_url):
                # Don't remove/modify contact links in floating buttons
                if is_floating_button and self._is_contact_link(href):
                    # Keep the original href for floating button contact links
                    continue
                
                if self.config.remove_external_links_remove_anchors:
                    link.decompose()
                elif self.config.remove_external_links_keep_anchors:
                    link["href"] = "#"
                    # Keep the text but remove link
                    text = link.get_text()
                    link.replace_with(text)
                continue

            # Process internal links
            if self.config.make_internal_links_relative:
                # Use _get_relative_link_path to ensure links match saved file paths
                relative_path = self._get_relative_link_path(normalized_url, is_page=True)
                link["href"] = relative_path
            else:
                if self.config.make_non_www or self.config.make_www:
                    link["href"] = normalized_url

            # Add to links to follow
            if normalized_url not in self.config.visited_urls:
                links_to_follow.append(normalized_url)

        # Process images
        for img in soup.find_all("img", src=True):
            src = img["src"]
            # Extract wayback URL first
            original = self._extract_original_url_from_path(src)
            if original:
                src = original
            normalized_url = self._normalize_url(src, base_url)

            if self._is_internal_url(normalized_url):
                if self.config.make_internal_links_relative:
                    # Images are assets, don't add .html extension
                    img["src"] = self._get_relative_link_path(normalized_url, is_page=False)
                else:
                    img["src"] = normalized_url

                if normalized_url not in self.config.visited_urls:
                    links_to_follow.append(normalized_url)

        # Process CSS links
        for link in soup.find_all("link", rel="stylesheet", href=True):
            href = link.get("href", "")
            if not href:
                continue
            # Extract wayback URL first
            original = self._extract_original_url_from_path(href)
            if original:
                href = original
            normalized_url = self._normalize_url(href, base_url)

            # Handle external links (e.g., Google Fonts)
            if not self._is_internal_url(normalized_url):
                # Remove external links if configured
                if self.config.remove_external_links_remove_anchors:
                    link.decompose()
                elif self.config.remove_external_links_keep_anchors:
                    # Keep but remove wayback URLs - convert to direct external URL
                    link["href"] = normalized_url if normalized_url.startswith(("http://", "https://")) else href
                continue

            if self.config.make_internal_links_relative:
                # CSS files are assets, preserve extension
                link["href"] = self._get_relative_link_path(normalized_url, is_page=False)
            else:
                link["href"] = normalized_url

            if normalized_url not in self.config.visited_urls:
                links_to_follow.append(normalized_url)

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
            normalized_url = self._normalize_url(src, base_url)

            if self._is_internal_url(normalized_url):
                if self.config.make_internal_links_relative:
                    # JavaScript files are assets, preserve extension
                    script["src"] = self._get_relative_link_path(normalized_url, is_page=False)
                else:
                    script["src"] = normalized_url

                if normalized_url not in self.config.visited_urls:
                    links_to_follow.append(normalized_url)

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

            if self._is_internal_url(normalized_url):
                if self.config.make_internal_links_relative:
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
                if style_url not in self.config.visited_urls and self._is_internal_url(style_url):
                    links_to_follow.append(style_url)
            
            # Rewrite URLs in inline styles - handle url() functions
            if "web.archive.org" in style or "/web/" in style or "url(" in style:
                def replace_url_in_style(match):
                    full_match = match.group(0)
                    url_part = match.group(1) if len(match.groups()) > 0 else full_match
                    
                    # Extract original URL from wayback path
                    original = self._extract_original_url_from_path(url_part)
                    if original:
                        url_part = original
                    elif "web.archive.org" in url_part:
                        # Try extracting from absolute wayback URL
                        match_obj = re.search(r"/web/\d+[a-z]*(?:im_|cs_|js_|jm_)/(https?://[^\"\s'()]+)", url_part)
                        if match_obj:
                            url_part = match_obj.group(1)
                    
                    normalized = self._normalize_url(url_part, base_url)
                    
                    if self._is_internal_url(normalized):
                        if self.config.make_internal_links_relative:
                            new_path = self._make_relative_path(normalized)
                            return f"url({new_path})"
                        return f"url({normalized})"
                    
                    return full_match
                
                # Pattern for url() with wayback URLs in inline styles
                url_patterns = [
                    r'url\s*\(\s*["\']?(/web/\d+[a-z]*(?:im_|cs_|js_|jm_)/https?://[^"\'()]+)["\']?\s*\)',  # Relative wayback
                    r'url\s*\(\s*["\']?(https?://web\.archive\.org/web/\d+[a-z]*(?:im_|cs_|js_|jm_)/https?://[^"\'()]+)["\']?\s*\)',  # Absolute wayback
                    r'url\s*\(\s*["\']?(https?://web\.archive\.org/[^"\'()]+)["\']?\s*\)',  # Simple web.archive.org URL
                ]
                new_style = style
                for pattern in url_patterns:
                    new_style = re.sub(pattern, replace_url_in_style, new_style, flags=re.IGNORECASE)
                element["style"] = new_style

        # Process <style> tags in HTML (not just inline styles)
        for style_tag in soup.find_all("style"):
            if style_tag.string:
                css_content = style_tag.string
                # Extract URLs from style tag content
                style_urls = self._extract_css_urls(css_content, base_url)
                for style_url in style_urls:
                    if style_url not in self.config.visited_urls and self._is_internal_url(style_url):
                        links_to_follow.append(style_url)
                
                # Rewrite URLs in style tag CSS
                css_content = self._rewrite_css_urls(css_content, base_url)
                style_tag.string = css_content

        # Get processed HTML
        processed_html = str(soup)
        processed_html = self._optimize_html(processed_html)

        return processed_html, links_to_follow

    def download(self):
        """Main download method."""
        # Create output directory
        Path(self.config.output_dir).mkdir(parents=True, exist_ok=True)

        # Start with the main page
        queue = [self.config.base_url]

        while queue:
            url = queue.pop(0)

            if url in self.config.visited_urls:
                continue

            print(f"Downloading: {url}")
            self.config.visited_urls.add(url)

            content = self.download_file(url)
            if not content:
                continue

            # Determine file type with robust detection
            try:
                parsed = urlparse(url)
                content_type, _ = mimetypes.guess_type(parsed.path)
                
                # Better content type detection from URL path
                if not content_type:
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
                    # Check content signatures
                    if content.startswith(b'<!DOCTYPE') or content.startswith(b'<html') or content.startswith(b'<HTML'):
                        content_type = "text/html"
                    elif content.startswith(b'/*') or content.startswith(b'@charset') or b'@media' in content[:200]:
                        content_type = "text/css"
                    elif content.startswith(b'<?xml') or b'<svg' in content[:200]:
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
            
            local_path = self._get_local_path(url)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            try:
                # Process based on content type - be more conservative about what we treat as HTML
                is_html = (
                    content_type == "text/html" or 
                    (not content_type and (
                        url.endswith(".html") or 
                        url.endswith(".htm") or
                        (parsed.path and not os.path.splitext(parsed.path)[1] and "?" not in url and not any(parsed.path.lower().endswith(ext) for ext in [".css", ".js", ".json", ".xml", ".txt"]))
                    ))
                )
                
                if is_html:
                    # Process HTML
                    try:
                        # Try to decode as UTF-8, fallback to latin-1 or detect encoding
                        try:
                            html = content.decode("utf-8", errors="strict")
                        except UnicodeDecodeError:
                            try:
                                html = content.decode("utf-8", errors="ignore")
                            except Exception:
                                # Last resort: try latin-1 which can decode any byte sequence
                                html = content.decode("latin-1", errors="ignore")
                        
                        processed_html, new_links = self._process_html(html, url)
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
                            print(f"Error saving file {local_path}: {save_error}")
                        continue

                    # Save HTML
                    try:
                        with open(local_path, "w", encoding="utf-8", errors="replace") as f:
                            f.write(processed_html)
                        self.config.downloaded_files[url] = str(local_path)
                    except Exception as e:
                        print(f"Error saving HTML to {local_path}: {e}")
                        continue

                    # Add new links to queue (deduplicate)
                    for link_url in new_links:
                        if link_url not in self.config.visited_urls and link_url not in queue:
                            queue.append(link_url)

                elif content_type == "text/css":
                    # Process CSS
                    try:
                        css = content.decode("utf-8", errors="ignore")
                    except Exception:
                        css = content.decode("latin-1", errors="ignore")
                    
                    try:
                        # Extract URLs from CSS (images, fonts, @import, etc.)
                        css_urls = self._extract_css_urls(css, url)
                        for css_url in css_urls:
                            if css_url not in self.config.visited_urls and css_url not in queue and self._is_internal_url(css_url):
                                queue.append(css_url)
                        
                        # Rewrite URLs in CSS to relative paths
                        css = self._rewrite_css_urls(css, url)
                        
                        css = self._minify_css(css)
                    except Exception as e:
                        print(f"Warning: Error processing CSS for {url}: {e}")
                        # Use original content if processing fails
                        css = content.decode("utf-8", errors="ignore")

                    try:
                        with open(local_path, "w", encoding="utf-8", errors="replace") as f:
                            f.write(css)
                        self.config.downloaded_files[url] = str(local_path)
                    except Exception as e:
                        print(f"Error saving CSS to {local_path}: {e}")
                        continue

                elif content_type in ("application/javascript", "text/javascript"):
                    # Process JavaScript
                    js = content.decode("utf-8", errors="ignore")
                    
                    # Extract URLs from JavaScript (may contain fetch, XMLHttpRequest, etc.)
                    js_urls = self._extract_js_urls(js, url)
                    for js_url in js_urls:
                        if js_url not in self.config.visited_urls and self._is_internal_url(js_url):
                            queue.append(js_url)
                    
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
                print(f"Error processing {url}: {e}")
                continue

        print(f"\nDownload complete! Files saved to: {self.config.output_dir}")
        print(f"Total files downloaded: {len(self.config.downloaded_files)}")

