"""Core downloader module for Wayback-Archive."""

import os
import re
import mimetypes
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
        """Convert a regular URL to a Wayback Machine URL."""
        if url.startswith("http://web.archive.org") or url.startswith("https://web.archive.org"):
            return url
        # Extract timestamp from original wayback URL
        match = re.match(r"https?://web\.archive\.org/web/(\d+[a-z]*)/", self.config.wayback_url)
        if match:
            timestamp = match.group(1)
            return f"https://web.archive.org/web/{timestamp}/{url}"
        return url

    def _make_relative_path(self, url: str) -> str:
        """Convert absolute URL to relative path."""
        parsed = urlparse(url)
        path = parsed.path
        if parsed.query:
            path += "?" + parsed.query
        if parsed.fragment:
            path += "#" + parsed.fragment
        return path or "/"

    def _normalize_url(self, url: str, base_url: str) -> str:
        """Normalize URL and handle www/non-www conversion."""
        # Handle relative URLs
        if not url.startswith(("http://", "https://", "//")):
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

        # Remove fragment for file identification
        url_without_fragment = parsed._replace(fragment="").geturl()

        return url_without_fragment

    def _get_local_path(self, url: str) -> Path:
        """Get local file path for a URL."""
        parsed = urlparse(url)
        path = unquote(parsed.path)
        
        # Remove leading slash
        if path.startswith("/"):
            path = path[1:]

        # Default to index.html for directories
        if not path or path.endswith("/"):
            path = "index.html"

        # Add .html extension if no extension
        if "." not in os.path.basename(path):
            path = os.path.join(os.path.dirname(path), os.path.basename(path) + ".html")

        return Path(self.config.output_dir) / path

    def download_file(self, url: str) -> Optional[bytes]:
        """Download a file from the given URL."""
        try:
            wayback_url = self._convert_to_wayback_url(url)
            response = self.session.get(
                wayback_url, timeout=30, allow_redirects=self.config.keep_redirections
            )
            response.raise_for_status()
            return response.content
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
            normalized = self._normalize_url(import_url, base_url)
            if normalized not in urls:
                urls.append(normalized)
        
        # Extract url() references (images, fonts, etc.)
        url_pattern = r'url\s*\(\s*["\']?([^"\'()]+)["\']?\s*\)'
        for match in re.finditer(url_pattern, css, re.IGNORECASE):
            css_url = match.group(1).strip()
            # Skip data URIs and special protocols
            if not css_url.startswith(("data:", "javascript:", "vbscript:", "#")):
                normalized = self._normalize_url(css_url, base_url)
                if normalized not in urls:
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

        # Remove comments
        for comment in soup.findAll(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        # Remove trackers and analytics
        if self.config.remove_trackers:
            for script in soup.find_all("script", src=True):
                if self._is_tracker(script["src"]):
                    script.decompose()

            # Remove inline tracking scripts
            for script in soup.find_all("script"):
                if script.string and any(
                    pattern in script.string for pattern in self.TRACKER_PATTERNS
                ):
                    script.decompose()

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
            href = link["href"]
            normalized_url = self._normalize_url(href, base_url)

            # Handle contact links
            if self.config.remove_clickable_contacts and self._is_contact_link(href):
                if self.config.remove_external_links_remove_anchors:
                    link.decompose()
                else:
                    link["href"] = "#"
                continue

            # Handle external links
            if not self._is_internal_url(normalized_url):
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
                link["href"] = self._make_relative_path(normalized_url)
            else:
                if self.config.make_non_www or self.config.make_www:
                    link["href"] = normalized_url

            # Add to links to follow
            if normalized_url not in self.config.visited_urls:
                links_to_follow.append(normalized_url)

        # Process images
        for img in soup.find_all("img", src=True):
            src = img["src"]
            normalized_url = self._normalize_url(src, base_url)

            if self._is_internal_url(normalized_url):
                if self.config.make_internal_links_relative:
                    img["src"] = self._make_relative_path(normalized_url)
                else:
                    img["src"] = normalized_url

                if normalized_url not in self.config.visited_urls:
                    links_to_follow.append(normalized_url)

        # Process CSS links
        for link in soup.find_all("link", rel="stylesheet", href=True):
            href = link["href"]
            normalized_url = self._normalize_url(href, base_url)

            if self._is_internal_url(normalized_url):
                if self.config.make_internal_links_relative:
                    link["href"] = self._make_relative_path(normalized_url)
                else:
                    link["href"] = normalized_url

                if normalized_url not in self.config.visited_urls:
                    links_to_follow.append(normalized_url)

        # Process script tags
        for script in soup.find_all("script", src=True):
            src = script["src"]
            normalized_url = self._normalize_url(src, base_url)

            if self._is_internal_url(normalized_url):
                if self.config.make_internal_links_relative:
                    script["src"] = self._make_relative_path(normalized_url)
                else:
                    script["src"] = normalized_url

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

            # Determine file type
            parsed = urlparse(url)
            content_type, _ = mimetypes.guess_type(url)
            local_path = self._get_local_path(url)
            local_path.parent.mkdir(parents=True, exist_ok=True)

            # Process based on content type
            if content_type == "text/html" or url.endswith(".html") or not content_type:
                # Process HTML
                html = content.decode("utf-8", errors="ignore")
                processed_html, new_links = self._process_html(html, url)

                # Save HTML
                with open(local_path, "w", encoding="utf-8") as f:
                    f.write(processed_html)

                # Add new links to queue
                queue.extend(new_links)
                self.config.downloaded_files[url] = str(local_path)

            elif content_type == "text/css":
                # Process CSS
                css = content.decode("utf-8", errors="ignore")
                
                # Extract URLs from CSS (images, fonts, @import, etc.)
                css_urls = self._extract_css_urls(css, url)
                for css_url in css_urls:
                    if css_url not in self.config.visited_urls and self._is_internal_url(css_url):
                        queue.append(css_url)
                
                css = self._minify_css(css)

                with open(local_path, "w", encoding="utf-8") as f:
                    f.write(css)

                self.config.downloaded_files[url] = str(local_path)

            elif content_type in ("application/javascript", "text/javascript"):
                # Process JavaScript
                js = content.decode("utf-8", errors="ignore")
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

            else:
                # Save as-is
                with open(local_path, "wb") as f:
                    f.write(content)

                self.config.downloaded_files[url] = str(local_path)

        print(f"\nDownload complete! Files saved to: {self.config.output_dir}")
        print(f"Total files downloaded: {len(self.config.downloaded_files)}")

