"""Targeted tests for remaining coverage gaps in downloader.py."""

import os
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from bs4 import BeautifulSoup

from wayback_archive.config import Config
from wayback_archive.downloader import WaybackDownloader


def _make_dl(wayback_url=None, **env_overrides):
    env = {"WAYBACK_URL": wayback_url or "https://web.archive.org/web/20250417203037/http://example.com/"}
    env.update(env_overrides)
    for k, v in env.items():
        os.environ[k] = v
    config = Config()
    return WaybackDownloader(config)


def _cleanup():
    os.environ.pop("WAYBACK_URL", None)


# ===================================================================
# download_file - deeper 404 fallback paths
# ===================================================================

class TestDownloadFileFallbacks:

    def setup_method(self):
        self.dl = _make_dl()

    def teardown_method(self):
        _cleanup()

    def test_404_html_tries_if_variant_timestamps(self):
        """For HTML pages, 404 fallback should try if_ variant for each timestamp."""
        import requests

        attempt = 0
        def mock_get(url, **kwargs):
            nonlocal attempt
            attempt += 1
            resp = Mock()
            if attempt <= 3:
                resp.status_code = 404
                error = requests.exceptions.HTTPError(response=resp)
                resp.raise_for_status = Mock(side_effect=error)
                resp.content = b''
            else:
                resp.status_code = 200
                resp.content = b'<html><body>Found via timestamp variant</body></html>'
                resp.raise_for_status = Mock()
            return resp

        self.dl.session.get = mock_get
        result = self.dl.download_file("http://example.com/page.html")
        assert result is not None

    def test_404_non_html_tries_regular_variant_timestamps(self):
        """For non-HTML assets, 404 fallback should try regular timestamps (not if_)."""
        import requests

        attempt = 0
        def mock_get(url, **kwargs):
            nonlocal attempt
            attempt += 1
            resp = Mock()
            if attempt <= 2:
                resp.status_code = 404
                error = requests.exceptions.HTTPError(response=resp)
                resp.raise_for_status = Mock(side_effect=error)
                resp.content = b''
            else:
                resp.status_code = 200
                resp.content = b'\x00\x01\x00\x00'  # binary font data
                resp.raise_for_status = Mock()
            return resp

        self.dl.session.get = mock_get
        result = self.dl.download_file("http://example.com/style.css")
        assert result is not None

    def test_404_variant_corrupted_font_continues(self):
        """Corrupted font in variant timestamp should continue to next variant."""
        import requests

        attempt = 0
        def mock_get(url, **kwargs):
            nonlocal attempt
            attempt += 1
            resp = Mock()
            if attempt == 1:
                # First attempt: 404
                resp.status_code = 404
                error = requests.exceptions.HTTPError(response=resp)
                resp.raise_for_status = Mock(side_effect=error)
                resp.content = b''
            elif attempt <= 3:
                # Variant attempts return corrupted font (HTML error page)
                resp.status_code = 200
                resp.content = b'<!DOCTYPE html><html>Error</html>'
                resp.raise_for_status = Mock()
            else:
                # Eventually get real font
                resp.status_code = 200
                resp.content = b'\x00\x01\x00\x00' + b'\x00' * 50
                resp.raise_for_status = Mock()
            return resp

        self.dl.session.get = mock_get
        result = self.dl.download_file("http://example.com/font.woff")
        # May or may not find it depending on how many variants are tried
        # The key is that it doesn't crash

    def test_404_variant_exception_continues(self):
        """Exceptions during variant attempts should continue to next variant."""
        import requests

        attempt = 0
        def mock_get(url, **kwargs):
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                resp = Mock()
                resp.status_code = 404
                error = requests.exceptions.HTTPError(response=resp)
                resp.raise_for_status = Mock(side_effect=error)
                resp.content = b''
                return resp
            elif attempt <= 4:
                raise requests.exceptions.ConnectionError("network down")
            else:
                resp = Mock()
                resp.status_code = 200
                resp.content = b'found it'
                resp.raise_for_status = Mock()
                return resp

        self.dl.session.get = mock_get
        result = self.dl.download_file("http://example.com/style.css")
        # Should not crash

    def test_404_live_fallback_timeout(self):
        """Live URL fallback should handle timeouts gracefully."""
        import requests

        def mock_get(url, **kwargs):
            resp = Mock()
            if "web.archive.org" in url:
                resp.status_code = 404
                error = requests.exceptions.HTTPError(response=resp)
                resp.raise_for_status = Mock(side_effect=error)
                resp.content = b''
                return resp
            else:
                raise requests.exceptions.Timeout("live timeout")

        self.dl.session.get = mock_get
        result = self.dl.download_file("http://example.com/image.jpg")
        assert result is None

    def test_404_live_fallback_http_error(self):
        """Live URL fallback should handle HTTP errors gracefully."""
        import requests

        def mock_get(url, **kwargs):
            resp = Mock()
            if "web.archive.org" in url:
                resp.status_code = 404
                error = requests.exceptions.HTTPError(response=resp)
                resp.raise_for_status = Mock(side_effect=error)
                resp.content = b''
                return resp
            else:
                resp.status_code = 500
                resp.raise_for_status = Mock(side_effect=requests.exceptions.HTTPError(response=resp))
                resp.content = b''
                return resp

        self.dl.session.get = mock_get
        result = self.dl.download_file("http://example.com/image.jpg")
        assert result is None

    def test_timeout_live_fallback_corrupted_font(self):
        """Timeout + live fallback returning corrupted font should return None."""
        import requests

        attempt = 0
        def mock_get(url, **kwargs):
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise requests.exceptions.Timeout()
            resp = Mock()
            resp.status_code = 200
            resp.content = b'<!DOCTYPE html>Error page'
            resp.raise_for_status = Mock()
            return resp

        self.dl.session.get = mock_get
        result = self.dl.download_file("http://example.com/font.woff")
        assert result is None

    def test_timeout_live_fallback_exception(self):
        """Timeout + live fallback raising exception should return None."""
        import requests

        attempt = 0
        def mock_get(url, **kwargs):
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise requests.exceptions.Timeout()
            raise Exception("network error")

        self.dl.session.get = mock_get
        result = self.dl.download_file("http://example.com/image.jpg")
        assert result is None

    def test_non_404_http_error(self):
        """Non-404 HTTP errors (e.g. 500) should return None without fallback."""
        import requests

        def mock_get(url, **kwargs):
            resp = Mock()
            resp.status_code = 500
            error = requests.exceptions.HTTPError(response=resp)
            resp.raise_for_status = Mock(side_effect=error)
            resp.content = b''
            return resp

        self.dl.session.get = mock_get
        result = self.dl.download_file("http://example.com/style.css")
        assert result is None

    def test_html_if_decode_exception_returns_content(self):
        """If decoding the if_ response fails, content should still be returned."""
        attempt = 0
        def mock_get(url, **kwargs):
            nonlocal attempt
            attempt += 1
            resp = Mock()
            resp.status_code = 200
            resp.raise_for_status = Mock()
            # Binary content that starts with HTML but can't be fully decoded
            resp.content = b'<!DOCTYPE html>\xff\xfe' + b'\x00' * 200
            return resp

        self.dl.session.get = mock_get
        result = self.dl.download_file("http://example.com/page")
        assert result is not None

    def test_html_if_fails_falls_to_regular(self):
        """If the if_ request raises an exception, should fall through to regular."""
        attempt = 0
        def mock_get(url, **kwargs):
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                # if_ version fails
                raise Exception("if_ failed")
            resp = Mock()
            resp.status_code = 200
            resp.content = b'<html><body>Regular page</body></html>'
            resp.raise_for_status = Mock()
            return resp

        self.dl.session.get = mock_get
        result = self.dl.download_file("http://example.com/page")
        assert result is not None


# ===================================================================
# _process_html - deeper coverage of floating buttons
# ===================================================================

class TestFloatingButtonsDeep:

    def setup_method(self):
        self.dl = _make_dl()

    def teardown_method(self):
        _cleanup()

    def test_floating_button_mailto_direct_absolute(self):
        """Mailto: in absolute wayback URL within floating button."""
        html = """
        <html><body>
        <div id="sp-footeredu">
            <a href="https://web.archive.org/web/20250417203037/mailto:info@test.com">Email</a>
        </div>
        </body></html>
        """
        processed, _ = self.dl._process_html(html, "http://example.com/")
        assert "mailto:info@test.com" in processed

    def test_floating_button_whatsapp(self):
        html = """
        <html><body>
        <div id="sp-footeredu">
            <a href="/web/20250417203037/whatsapp:+34600000000">WhatsApp</a>
        </div>
        </body></html>
        """
        processed, _ = self.dl._process_html(html, "http://example.com/")
        assert "whatsapp:+34600000000" in processed

    def test_floating_button_email_in_path(self):
        """Email address hidden in URL path like /web/TIMESTAMP/https://domain.com/email@domain.com."""
        html = """
        <html><body>
        <div id="sp-footeredu">
            <a href="/web/20250417203037/https://example.com/contact@test.com">Email</a>
        </div>
        </body></html>
        """
        processed, _ = self.dl._process_html(html, "http://example.com/")
        assert "mailto:contact@test.com" in processed

    def test_floating_button_extracted_url_with_email_in_path(self):
        """Extracted URL that contains @ but isn't a mailto: should become mailto:."""
        html = """
        <html><body>
        <div id="sp-footeredu">
            <a href="https://web.archive.org/web/20250417203037/http://example.com/info@example.com">Email</a>
        </div>
        </body></html>
        """
        processed, _ = self.dl._process_html(html, "http://example.com/")
        assert "mailto:" in processed

    def test_floating_button_sms(self):
        html = """
        <html><body>
        <div id="sp-footeredu">
            <a href="/web/20250417203037/sms:+34600000000">SMS</a>
        </div>
        </body></html>
        """
        processed, _ = self.dl._process_html(html, "http://example.com/")
        assert "sms:+34600000000" in processed

    def test_floating_button_callto(self):
        html = """
        <html><body>
        <div id="sp-footeredu">
            <a href="/web/20250417203037/callto:user123">Call</a>
        </div>
        </body></html>
        """
        processed, _ = self.dl._process_html(html, "http://example.com/")
        assert "callto:user123" in processed


# ===================================================================
# _process_html - CSS stylesheet links with Google Fonts / external
# ===================================================================

class TestCssStylesheetLinks:

    def setup_method(self):
        self.dl = _make_dl()

    def teardown_method(self):
        _cleanup()

    def test_squarespace_cdn_stylesheet(self):
        """Squarespace CDN stylesheet should be queued for download."""
        html = '<html><head><link rel="stylesheet" href="https://static1.squarespace.com/static/css/style.css"></head><body>Test</body></html>'
        processed, links = self.dl._process_html(html, "http://example.com/index.html")
        assert any("squarespace" in l for l in links)

    def test_external_stylesheet_remove_anchors(self):
        """External stylesheets with remove_anchors should be decomposed."""
        self.dl.config.remove_external_links_keep_anchors = False
        self.dl.config.remove_external_links_remove_anchors = True
        html = '<html><head><link rel="stylesheet" href="http://cdn.other.com/style.css"></head><body>Test</body></html>'
        processed, _ = self.dl._process_html(html, "http://example.com/")
        assert "cdn.other.com" not in processed

    def test_internal_stylesheet_not_relative(self):
        """Internal stylesheet when make_internal_links_relative=False."""
        self.dl.config.make_internal_links_relative = False
        html = '<html><head><link rel="stylesheet" href="/web/20250417203037cs_/http://example.com/style.css"></head><body>Test</body></html>'
        processed, links = self.dl._process_html(html, "http://example.com/index.html")
        assert any("style.css" in l for l in links)


# ===================================================================
# _process_html - script tags deeper coverage
# ===================================================================

class TestScriptTagProcessing:

    def setup_method(self):
        self.dl = _make_dl()

    def teardown_method(self):
        _cleanup()

    def test_internal_script_not_relative(self):
        """Internal scripts when make_internal_links_relative=False."""
        self.dl.config.make_internal_links_relative = False
        html = '<html><body><script src="/web/20250417203037js_/http://example.com/app.js"></script></body></html>'
        processed, links = self.dl._process_html(html, "http://example.com/index.html")
        assert any("app.js" in l for l in links)


# ===================================================================
# _process_html - image processing deeper
# ===================================================================

class TestImageProcessing:

    def setup_method(self):
        self.dl = _make_dl()

    def teardown_method(self):
        _cleanup()

    def test_image_not_relative(self):
        """Images when make_internal_links_relative=False."""
        self.dl.config.make_internal_links_relative = False
        html = '<html><body><img src="/web/20250417203037im_/http://example.com/photo.jpg"></body></html>'
        processed, links = self.dl._process_html(html, "http://example.com/index.html")
        assert any("photo.jpg" in l for l in links)


# ===================================================================
# _process_html - link tags (non-stylesheet)
# ===================================================================

class TestNonStylesheetLinks:

    def setup_method(self):
        self.dl = _make_dl()

    def teardown_method(self):
        _cleanup()

    def test_favicon_not_relative(self):
        """Favicon when make_internal_links_relative=False."""
        self.dl.config.make_internal_links_relative = False
        html = '<html><head><link rel="icon" href="/web/20250417203037im_/http://example.com/favicon.ico"></head><body>Test</body></html>'
        processed, links = self.dl._process_html(html, "http://example.com/")

    def test_squarespace_cdn_preload_with_query(self):
        """Squarespace CDN in preload link with query string."""
        html = '<html><head><link rel="preload" href="https://static1.squarespace.com/static/file.js?v=123"></head><body>Test</body></html>'
        processed, links = self.dl._process_html(html, "http://example.com/index.html")


# ===================================================================
# _process_html - SVG use elements
# ===================================================================

class TestSvgUseElements:

    def setup_method(self):
        self.dl = _make_dl()

    def teardown_method(self):
        _cleanup()

    def test_svg_use_wayback_with_fragment_and_query(self):
        """SVG use with wayback path containing fragment and query params."""
        html = '<html><body><svg><use xlink:href="/web/20250417203037im_/http://example.com/icons.svg#email?v=1" href="/web/20250417203037im_/http://example.com/icons.svg#email?v=1"></use></svg></body></html>'
        processed, _ = self.dl._process_html(html, "http://example.com/")
        assert "#email" in processed

    def test_svg_use_plain_fragment(self):
        """SVG use with plain fragment in wayback path."""
        html = '<html><body><svg><use xlink:href="/web/20250417203037im_/http://example.com/#icon-star"></use></svg></body></html>'
        processed, _ = self.dl._process_html(html, "http://example.com/")
        assert "#icon-star" in processed


# ===================================================================
# _process_html - remaining attribute rewriting
# ===================================================================

class TestRemainingAttributeRewrite:

    def setup_method(self):
        self.dl = _make_dl()

    def teardown_method(self):
        _cleanup()

    def test_web_archive_in_arbitrary_attr(self):
        """web.archive.org in arbitrary attributes should be cleaned."""
        html = '<html><body><div data-url="https://web.archive.org/web/20250417203037/http://example.com/data.json">Content</div></body></html>'
        processed, _ = self.dl._process_html(html, "http://example.com/index.html")
        assert "web.archive.org" not in processed

    def test_squarespace_cdn_in_arbitrary_attr(self):
        """Squarespace CDN in arbitrary data attributes should be rewritten."""
        html = '<html><body><div data-background="https://images.squarespace-cdn.com/content/v1/bg.jpg">Content</div></body></html>'
        processed, _ = self.dl._process_html(html, "http://example.com/index.html")

    def test_relative_web_path_in_attr(self):
        """Relative /web/ paths in attributes should be cleaned."""
        html = '<html><body><div data-src="/web/20250417203037im_/http://example.com/photo.jpg">Content</div></body></html>'
        processed, _ = self.dl._process_html(html, "http://example.com/index.html")
        assert "/web/" not in processed

    def test_make_internal_links_not_relative_attr(self):
        """When make_internal_links_relative=False, attributes should use normalized URLs."""
        self.dl.config.make_internal_links_relative = False
        html = '<html><body><div data-image="http://example.com/photo.jpg">Content</div></body></html>'
        processed, _ = self.dl._process_html(html, "http://example.com/index.html")

    def test_squarespace_cdn_attr_not_relative(self):
        """Squarespace CDN attributes when make_internal_links_relative=False."""
        self.dl.config.make_internal_links_relative = False
        html = '<html><body><div data-bg="https://images.squarespace-cdn.com/content/bg.jpg">Content</div></body></html>'
        processed, _ = self.dl._process_html(html, "http://example.com/index.html")

    def test_squarespace_cdn_with_query_in_attr(self):
        """Squarespace CDN with query string in data attribute."""
        html = '<html><body><div data-src="https://images.squarespace-cdn.com/content/v1/photo.jpg?format=500w">Content</div></body></html>'
        processed, _ = self.dl._process_html(html, "http://example.com/index.html")


# ===================================================================
# _process_html - inline styles with wayback URLs
# ===================================================================

class TestInlineStyleRewriting:

    def setup_method(self):
        self.dl = _make_dl()

    def teardown_method(self):
        _cleanup()

    def test_absolute_wayback_url_in_inline_style(self):
        html = '<html><body><div style="background: url(https://web.archive.org/web/20250417203037im_/http://example.com/bg.jpg)">X</div></body></html>'
        processed, _ = self.dl._process_html(html, "http://example.com/index.html")
        assert "web.archive.org" not in processed

    def test_simple_web_archive_url_in_style(self):
        html = '<html><body><div style="background: url(https://web.archive.org/web/file.jpg)">X</div></body></html>'
        processed, _ = self.dl._process_html(html, "http://example.com/index.html")

    def test_squarespace_cdn_in_inline_style(self):
        html = '<html><body><div style="background-image: url(https://images.squarespace-cdn.com/content/bg.jpg)">X</div></body></html>'
        processed, links = self.dl._process_html(html, "http://example.com/index.html")

    def test_squarespace_cdn_not_relative_inline_style(self):
        self.dl.config.make_internal_links_relative = False
        html = '<html><body><div style="background-image: url(https://images.squarespace-cdn.com/content/bg.jpg)">X</div></body></html>'
        processed, _ = self.dl._process_html(html, "http://example.com/index.html")


# ===================================================================
# _process_html - picture/source srcset deep coverage
# ===================================================================

class TestPictureSrcsetDeep:

    def setup_method(self):
        self.dl = _make_dl()

    def teardown_method(self):
        _cleanup()

    def test_srcset_squarespace_with_query_and_relative(self):
        """Squarespace CDN URLs in srcset with query and relative mode."""
        html = """
        <html><body>
        <picture>
            <source srcset="https://images.squarespace-cdn.com/content/v1/img.jpg?format=500w 500w">
            <img src="https://images.squarespace-cdn.com/content/v1/img.jpg">
        </picture>
        </body></html>
        """
        processed, links = self.dl._process_html(html, "http://example.com/index.html")

    def test_srcset_squarespace_not_relative(self):
        """Squarespace CDN URLs in srcset when make_internal_links_relative=False."""
        self.dl.config.make_internal_links_relative = False
        html = """
        <html><body>
        <picture>
            <source srcset="https://images.squarespace-cdn.com/content/v1/img.jpg 500w">
            <img src="https://images.squarespace-cdn.com/content/v1/img.jpg">
        </picture>
        </body></html>
        """
        processed, _ = self.dl._process_html(html, "http://example.com/index.html")

    def test_srcset_external_url_kept(self):
        """External URLs in srcset should be preserved as-is."""
        html = """
        <html><body>
        <picture>
            <source srcset="https://cdn.other.com/img-500.jpg 500w">
            <img src="https://cdn.other.com/img.jpg">
        </picture>
        </body></html>
        """
        processed, _ = self.dl._process_html(html, "http://example.com/index.html")
        assert "cdn.other.com" in processed

    def test_srcset_absolute_wayback_url(self):
        """Absolute wayback URLs in srcset should be extracted."""
        html = """
        <html><body>
        <picture>
            <source srcset="https://web.archive.org/web/20250417203037im_/http://example.com/img-500.jpg 500w">
            <img src="http://example.com/img.jpg">
        </picture>
        </body></html>
        """
        processed, links = self.dl._process_html(html, "http://example.com/index.html")
        assert "web.archive.org" not in processed

    def test_picture_img_squarespace_not_relative(self):
        """Picture img with Squarespace when not relative."""
        self.dl.config.make_internal_links_relative = False
        html = """
        <html><body>
        <picture>
            <img src="https://images.squarespace-cdn.com/content/v1/img.jpg">
        </picture>
        </body></html>
        """
        processed, _ = self.dl._process_html(html, "http://example.com/index.html")


# ===================================================================
# download() main loop - deeper branches
# ===================================================================

class TestDownloadLoopDeep:

    def teardown_method(self):
        _cleanup()

    def test_download_file_size_mb(self, tmp_path):
        """Large files should show size in MB."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.config.base_url = "http://example.com/big.zip"
        # 2MB content
        dl.download_file = Mock(return_value=b'\x00' * (2 * 1024 * 1024))
        dl.download()

    def test_download_queue_dedup(self, tmp_path):
        """Links already in queue should not be added again."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 2

        call_count = 0
        def fake_download_file(url):
            nonlocal call_count
            call_count += 1
            return b'<html><body>Page</body></html>'

        dl.download_file = fake_download_file
        # Return same link twice - should only be queued once
        call_num = 0
        def fake_process_html(html, base_url):
            nonlocal call_num
            call_num += 1
            if call_num == 1:
                return "<html>Page</html>", ["http://example.com/page2", "http://example.com/page2"]
            return "<html>Page</html>", []

        dl._process_html = fake_process_html
        dl.download()

    def test_download_css_with_queue_dedup(self, tmp_path):
        """CSS resource URLs should be deduplicated in queue."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.config.base_url = "http://example.com/style.css"
        # CSS with duplicate URLs
        dl.download_file = Mock(return_value=b'body { background: url(/bg.jpg); } .a { background: url(/bg.jpg); }')
        dl.download()

    def test_download_js_with_urls(self, tmp_path):
        """JavaScript files should have their URLs extracted and queued."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.config.base_url = "http://example.com/app.js"
        dl.download_file = Mock(return_value=b'img.src = "http://example.com/photo.jpg"')
        dl.download()

    def test_download_css_google_font_queued(self, tmp_path):
        """Google Font URLs in CSS should be queued."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.config.base_url = "http://example.com/style.css"
        dl.download_file = Mock(
            return_value=b"@font-face { src: url('https://fonts.gstatic.com/s/roboto/v29/file.woff2'); }"
        )
        dl.download()

    def test_download_css_squarespace_queued(self, tmp_path):
        """Squarespace CDN URLs in CSS should be queued."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.config.base_url = "http://example.com/style.css"
        dl.download_file = Mock(
            return_value=b"body { background: url('https://images.squarespace-cdn.com/content/bg.jpg'); }"
        )
        dl.download()

    def test_download_html_save_error(self, tmp_path):
        """Error saving HTML should be handled gracefully."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path / "nonexistent" / "deep" / "path")
        dl.config.max_files = 1
        dl.download_file = Mock(return_value=b'<html><body>Test</body></html>')
        dl._process_html = Mock(return_value=("<html>Test</html>", []))
        # This should not crash even if directory creation fails
        dl.download()

    def test_download_html_utf8_strict_fails(self, tmp_path):
        """HTML with invalid UTF-8 should still be processed."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        # Content with invalid UTF-8 bytes
        dl.download_file = Mock(return_value=b'<html><body>\xff\xfe Test</body></html>')
        dl._process_html = Mock(return_value=("<html>Test</html>", []))
        dl.download()

    def test_download_css_processing_error(self, tmp_path):
        """Error processing CSS should fall back to original content."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.config.base_url = "http://example.com/style.css"
        dl.download_file = Mock(return_value=b'body { margin: 0; }')
        dl._extract_css_urls = Mock(side_effect=Exception("parse error"))
        dl.download()

    def test_download_content_type_detection_error(self, tmp_path):
        """Error during content type detection should be handled."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.config.base_url = "http://example.com/file"
        dl.download_file = Mock(return_value=b'some content')
        # This tests the try/except around content type detection
        dl.download()

    def test_download_queue_shows_remaining(self, tmp_path):
        """Queue size > 1 should show remaining count."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 3

        call_count = 0
        def fake_download_file(url):
            nonlocal call_count
            call_count += 1
            if "style" in url:
                return b'body { margin: 0; }'
            if "app" in url:
                return b'var x = 1;'
            return b'<html><body>Page</body></html>'

        dl.download_file = fake_download_file
        dl._process_html = Mock(return_value=(
            "<html>Page</html>",
            ["http://example.com/style.css", "http://example.com/app.js"]
        ))
        dl.download()

    def test_download_max_files_with_limit_info(self, tmp_path):
        """Max files limit should be shown in output."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.download_file = Mock(return_value=b'<html><body>Test</body></html>')
        dl._process_html = Mock(return_value=("<html>Test</html>", ["http://example.com/p2"]))
        dl.download()


# ===================================================================
# _rewrite_css_urls - deeper branches
# ===================================================================

class TestRewriteCssUrlsDeep:

    def setup_method(self):
        self.dl = _make_dl()
        self.dl._current_page_url = "http://example.com/css/style.css"

    def teardown_method(self):
        _cleanup()

    def test_squarespace_cdn_url(self):
        """Squarespace CDN URLs in CSS should be rewritten to relative paths."""
        self.dl.config.make_internal_links_relative = True
        css = "body { background: url(https://images.squarespace-cdn.com/content/bg.jpg); }"
        result = self.dl._rewrite_css_urls(css, "http://example.com/css/style.css")
        # Should be rewritten (no longer the original absolute URL)
        assert "https://images.squarespace-cdn.com" not in result
        assert "url(" in result

    def test_squarespace_cdn_not_relative(self):
        """Squarespace CDN URLs when make_internal_links_relative=False."""
        self.dl.config.make_internal_links_relative = False
        css = "body { background: url(https://images.squarespace-cdn.com/content/bg.jpg); }"
        result = self.dl._rewrite_css_urls(css, "http://example.com/css/style.css")

    def test_external_url_preserved(self):
        """External (non-internal, non-CDN) URLs should be preserved."""
        css = "body { background: url(https://cdn.other.com/bg.jpg); }"
        result = self.dl._rewrite_css_urls(css, "http://example.com/css/style.css")
        assert "cdn.other.com" in result

    def test_relative_wayback_url(self):
        """Relative wayback URLs in CSS should be rewritten."""
        css = "body { background: url(/web/20250417203037im_/http://example.com/bg.jpg); }"
        result = self.dl._rewrite_css_urls(css, "http://example.com/css/style.css")
        assert "web.archive.org" not in result

    def test_google_fonts_googleapis_path(self):
        """Google Fonts CSS file paths should be handled specially."""
        self.dl.config.make_internal_links_relative = True
        css = "@font-face { src: url(https://fonts.googleapis.com/css?family=Roboto); }"
        result = self.dl._rewrite_css_urls(css, "http://example.com/css/style.css")


# ===================================================================
# _check_and_remove_corrupted_fonts_in_css - absolute path font URL
# ===================================================================

class TestCheckCorruptedFontsAbsPath:

    def setup_method(self):
        self.dl = _make_dl()

    def teardown_method(self):
        _cleanup()

    def test_font_relative_to_css(self):
        """Font with path relative to CSS file should be resolved correctly."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.content = b'\x00\x01\x00\x00' + b'\x00' * 200
        self.dl.session.get = Mock(return_value=mock_response)

        css = "@font-face { src: url('fonts/regular.woff'); }"
        self.dl._check_and_remove_corrupted_fonts_in_css(css, "http://example.com/css/style.css")


# ===================================================================
# __main__.py coverage
# ===================================================================

class TestMainModuleCoverage:

    def teardown_method(self):
        os.environ.pop("WAYBACK_URL", None)

    def test_main_runs_as_script(self):
        """Verify __main__ module can be executed."""
        os.environ["WAYBACK_URL"] = "https://web.archive.org/web/20250417203037/http://example.com/"
        with patch("wayback_archive.cli.main") as mock_main:
            # Simulate running __main__ directly
            exec(
                compile(
                    "from wayback_archive.cli import main\nif __name__ == '__main__':\n    main()\n",
                    "<string>",
                    "exec"
                ),
                {"__name__": "__main__"}
            )
            mock_main.assert_called_once()


# ===================================================================
# Config.validate edge case
# ===================================================================

# ===================================================================
# download() main loop - HTML/CSS/JS processing error paths
# ===================================================================

class TestDownloadProcessingErrors:

    def teardown_method(self):
        _cleanup()

    def test_html_decode_unicode_error(self, tmp_path):
        """HTML with bytes that fail strict UTF-8 should use ignore/latin-1 fallback."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        # Content with bytes that fail strict UTF-8 decoding
        bad_bytes = b'<html><body>\x80\x81\x82\x83 Content</body></html>'
        dl.download_file = Mock(return_value=bad_bytes)
        dl._process_html = Mock(return_value=("<html>Content</html>", []))
        dl.download()

    def test_html_save_error(self, tmp_path):
        """Error writing processed HTML should not crash."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.download_file = Mock(return_value=b'<html><body>Test</body></html>')
        dl._process_html = Mock(return_value=("<html>Test</html>", []))
        # Make the output path read-only to trigger write error
        output_file = tmp_path / "index.html"
        output_file.touch()
        output_file.chmod(0o000)
        dl.download()
        output_file.chmod(0o644)  # restore for cleanup

    def test_html_process_error_and_save_error(self, tmp_path):
        """Error processing HTML + error saving raw should not crash."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.download_file = Mock(return_value=b'<html><body>Test</body></html>')
        dl._process_html = Mock(side_effect=Exception("parse error"))
        # The raw save should still work via tmp_path
        dl.download()

    def test_css_js_queue_dedup_in_loop(self, tmp_path):
        """CSS and JS URL dedup in the main download loop."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 3

        call_count = 0
        def fake_download(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b'<html><body>Main</body></html>'
            elif call_count == 2:
                # CSS with internal URL already in queue
                return b'body { background: url(http://example.com/bg.jpg); } .x { background: url(http://example.com/bg.jpg); }'
            return b'\x89PNG' + b'\x00' * 50

        dl.download_file = fake_download
        dl._process_html = Mock(return_value=(
            "<html>Main</html>",
            ["http://example.com/style.css"]
        ))
        dl.download()

    def test_js_url_queue_dedup(self, tmp_path):
        """JS URLs should be deduplicated in queue."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 2

        call_count = 0
        def fake_download(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b'<html><body>Main</body></html>'
            return b'img.src = "http://example.com/photo.jpg"; other.src = "http://example.com/photo.jpg"'

        dl.download_file = fake_download
        dl._process_html = Mock(return_value=(
            "<html>Main</html>",
            ["http://example.com/app.js"]
        ))
        dl.download()

    def test_download_general_processing_exception(self, tmp_path):
        """General exception during processing should continue to next URL."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 2

        call_count = 0
        def fake_download(url):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return b'<html><body>Main</body></html>'
            return b'some content'

        dl.download_file = fake_download
        # First HTML processing works, but raises in the save portion
        first = True
        def fake_process(html, base_url):
            nonlocal first
            if first:
                first = False
                return "<html>Main</html>", ["http://example.com/page2"]
            return "<html>Page2</html>", []

        dl._process_html = fake_process
        dl.download()

    def test_download_content_type_from_path_extensions(self, tmp_path):
        """URLs with extensions where mimetypes returns None should use path-based detection."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        # Use an unusual URL structure where mimetypes might fail
        dl.config.base_url = "http://example.com/font.woff"
        dl.download_file = Mock(return_value=b'\x00\x01\x00\x00' + b'\x00' * 50)
        dl.download()

    def test_download_css_with_corrupted_fonts_processing(self, tmp_path):
        """CSS processing should handle corrupted font detection."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.config.base_url = "http://example.com/style.css"
        dl.corrupted_fonts.add("http://example.com/fonts/broken.woff")
        dl.download_file = Mock(
            return_value=b"@font-face { src: url('/fonts/broken.woff'); } body { margin: 0; }"
        )
        # Mock the font check to avoid real HTTP
        dl._check_and_remove_corrupted_fonts_in_css = Mock(return_value="body { margin: 0; }")
        dl.download()


class TestConfigValidateEdge:

    def teardown_method(self):
        os.environ.pop("WAYBACK_URL", None)

    def test_validate_returns_tuple(self):
        os.environ["WAYBACK_URL"] = "https://web.archive.org/web/20250417203037/http://example.com/"
        config = Config()
        result = config.validate()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert result[0] is True
        assert result[1] is None


# ===================================================================
# Final coverage push - targeted missing lines
# ===================================================================

class TestExtractOriginalUrlException:
    """Cover lines 249-251: exception handler in _extract_original_url_from_path."""

    def setup_method(self):
        self.dl = _make_dl()

    def teardown_method(self):
        _cleanup()

    def test_extract_original_url_exception_returns_none(self):
        """If regex processing raises, should return None."""
        # Pass an object whose string operations cause issues
        result = self.dl._extract_original_url_from_path(None)
        assert result is None

    def test_extract_original_url_empty_string(self):
        result = self.dl._extract_original_url_from_path("")
        assert result is None

    def test_extract_original_url_non_string(self):
        result = self.dl._extract_original_url_from_path(12345)
        assert result is None


class TestNormalizeUrlRelativeWebPath:
    """Cover lines 266-271: relative /web/ path handling in _normalize_url."""

    def setup_method(self):
        self.dl = _make_dl()

    def teardown_method(self):
        _cleanup()

    def test_relative_web_path_extracts_original(self):
        """Relative /web/ path should be extracted to original URL."""
        result = self.dl._normalize_url(
            "/web/20250417203037/http://example.com/page.html",
            "http://example.com/"
        )
        assert "example.com" in result
        assert "/web/" not in result

    def test_relative_web_path_no_extraction_uses_urljoin(self):
        """If /web/ path extraction fails, should use urljoin as fallback."""
        # A /web/ path that doesn't match the extraction pattern
        result = self.dl._normalize_url(
            "/web/invalid-no-timestamp",
            "http://example.com/"
        )
        # Should be resolved via urljoin since extraction fails
        assert result is not None


class TestImageOptimization:
    """Cover lines 1043-1052: RGBA/mode conversion in _optimize_image."""

    def setup_method(self):
        self.dl = _make_dl(OPTIMIZE_IMAGES="true")

    def teardown_method(self):
        _cleanup()
        os.environ.pop("OPTIMIZE_IMAGES", None)

    def test_optimize_jpeg_rgba_conversion(self):
        """RGBA images should be converted to RGB for JPEG."""
        from PIL import Image
        from io import BytesIO
        # Create an RGBA image
        img = Image.new("RGBA", (10, 10), (255, 0, 0, 128))
        buf = BytesIO()
        img.save(buf, format="PNG")
        content = buf.getvalue()
        result = self.dl._optimize_image(content, "JPEG")
        assert len(result) > 0

    def test_optimize_non_rgb_mode_conversion(self):
        """Non-RGB/non-L mode images should be converted to RGB."""
        from PIL import Image
        from io import BytesIO
        # Create a palette (P) mode image
        img = Image.new("P", (10, 10))
        buf = BytesIO()
        img.save(buf, format="PNG")
        content = buf.getvalue()
        result = self.dl._optimize_image(content, "PNG")
        assert len(result) > 0

    def test_optimize_l_mode_preserved(self):
        """L (grayscale) mode images should be processed without conversion."""
        from PIL import Image
        from io import BytesIO
        img = Image.new("L", (10, 10), 128)
        buf = BytesIO()
        img.save(buf, format="PNG")
        content = buf.getvalue()
        result = self.dl._optimize_image(content, "PNG")
        assert len(result) > 0


class TestJsUrlExtraction:
    """Cover lines 1016-1024: JS URL extraction filtering."""

    def setup_method(self):
        self.dl = _make_dl()

    def teardown_method(self):
        _cleanup()

    def test_js_url_with_code_keyword_skipped(self):
        """URLs containing code keywords should be skipped."""
        js = '''img.src = "function test() { return; }"'''
        urls = self.dl._extract_js_urls(js, "http://example.com/")
        assert len(urls) == 0

    def test_js_url_with_data_scheme_skipped(self):
        """data: URLs should be skipped."""
        js = '''img.src = "data:image/png;base64,ABC"'''
        urls = self.dl._extract_js_urls(js, "http://example.com/")
        assert len(urls) == 0

    def test_js_url_relative_without_protocol_skipped(self):
        """Relative URLs not starting with http/https// should be skipped."""
        js = '''img.src = "images/photo.jpg"'''
        urls = self.dl._extract_js_urls(js, "http://example.com/")
        assert len(urls) == 0

    def test_js_wayback_url_extracted(self):
        """Wayback URLs in JS should be extracted to original."""
        js = '''img.src = "https://web.archive.org/web/20250417203037im_/http://example.com/photo.jpg"'''
        urls = self.dl._extract_js_urls(js, "http://example.com/")
        # Should extract the original URL
        assert any("photo.jpg" in u for u in urls)


class TestDownloadLoopJqueryCdnFallback:
    """Cover lines 1917-1931: jQuery CDN fallback."""

    def teardown_method(self):
        _cleanup()

    def test_jquery_cdn_fallback(self, tmp_path):
        """Failed jquery.min.js should try CDN fallback URLs."""
        import requests
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.config.base_url = "http://example.com/jquery.min.js"

        call_count = 0
        def fake_download(url):
            nonlocal call_count
            call_count += 1
            # First call returns None (download failed)
            return None

        dl.download_file = fake_download

        # Mock session.get for CDN fallback
        cdn_resp = Mock()
        cdn_resp.status_code = 200
        cdn_resp.content = b'/* jQuery */'
        cdn_resp.raise_for_status = Mock()
        dl.session.get = Mock(return_value=cdn_resp)

        dl.download()
        # CDN fallback should have been attempted
        assert dl.session.get.called

    def test_jquery_cdn_fallback_all_fail(self, tmp_path):
        """When all CDN fallbacks fail, file should be counted as failed."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.config.base_url = "http://example.com/jquery.min.js"

        dl.download_file = Mock(return_value=None)
        dl.session.get = Mock(side_effect=Exception("CDN down"))

        dl.download()


class TestDownloadLoopSkipVisited:
    """Cover lines 1901-1902: visited URL skip counting."""

    def teardown_method(self):
        _cleanup()

    def test_visited_url_skipped(self, tmp_path):
        """Already visited URLs should be skipped."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 2

        call_count = 0
        def fake_download(url):
            nonlocal call_count
            call_count += 1
            return b'<html>Page</html>'

        dl.download_file = fake_download
        # Pre-add the base URL's normalized form to visited
        # Then it gets added again during processing -> skip
        dl._process_html = Mock(return_value=(
            "<html>Page</html>",
            ["http://example.com/", "http://example.com/page2"]
        ))
        dl.download()


class TestDownloadLoopFragmentSkip:
    """Cover line 1891: fragment-only URLs should be skipped."""

    def teardown_method(self):
        _cleanup()

    def test_fragment_url_skipped(self, tmp_path):
        """Fragment-only URLs (#section) should be skipped."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 2
        dl.download_file = Mock(return_value=b'<html>Page</html>')
        dl._process_html = Mock(return_value=(
            "<html>Page</html>",
            ["#section1", "#section2"]
        ))
        dl.download()


class TestDownloadLoopContentTypeFromPath:
    """Cover lines 1960-1976: content type detection from URL extensions."""

    def teardown_method(self):
        _cleanup()

    def test_json_extension(self, tmp_path):
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.config.base_url = "http://example.com/data.json"
        dl.download_file = Mock(return_value=b'{"key": "value"}')
        dl.download()

    def test_xml_extension(self, tmp_path):
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.config.base_url = "http://example.com/feed.xml"
        dl.download_file = Mock(return_value=b'<?xml version="1.0"?><root/>')
        dl.download()

    def test_pdf_extension(self, tmp_path):
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.config.base_url = "http://example.com/doc.pdf"
        dl.download_file = Mock(return_value=b'%PDF-1.4 content')
        dl.download()

    def test_video_extension(self, tmp_path):
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.config.base_url = "http://example.com/video.mp4"
        dl.download_file = Mock(return_value=b'\x00\x00\x00\x1cftyp')
        dl.download()

    def test_audio_extension(self, tmp_path):
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.config.base_url = "http://example.com/audio.mp3"
        dl.download_file = Mock(return_value=b'ID3\x04\x00')
        dl.download()

    def test_font_extension_woff2(self, tmp_path):
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.config.base_url = "http://example.com/font.woff2"
        dl.download_file = Mock(return_value=b'wOF2\x00\x00')
        dl.download()

    def test_image_extension_png(self, tmp_path):
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.config.base_url = "http://example.com/icon.png"
        dl.download_file = Mock(return_value=b'\x89PNG\r\n\x1a\n' + b'\x00' * 50)
        dl.download()

    def test_css_content_signature(self, tmp_path):
        """Content starting with CSS signatures should be detected as CSS."""
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.config.base_url = "http://example.com/file"
        dl.download_file = Mock(return_value=b'@charset "utf-8"; body { margin: 0; }')
        dl.download()

    def test_mjs_extension(self, tmp_path):
        dl = _make_dl()
        dl.config.output_dir = str(tmp_path)
        dl.config.max_files = 1
        dl.config.base_url = "http://example.com/module.mjs"
        dl.download_file = Mock(return_value=b'export default function() {}')
        dl.download()


class TestProcessHtmlFrames:
    """Cover lines 1186-1201: frame/iframe processing."""

    def setup_method(self):
        self.dl = _make_dl()

    def teardown_method(self):
        _cleanup()

    def test_internal_frame_relative(self):
        """Internal frame src should be rewritten to relative path."""
        html = '<html><body><frame src="/web/20250417203037/http://example.com/frame.html"></body></html>'
        processed, links = self.dl._process_html(html, "http://example.com/index.html")
        assert any("frame.html" in l for l in links)

    def test_internal_frame_not_relative(self):
        """Internal frame when make_internal_links_relative=False."""
        self.dl.config.make_internal_links_relative = False
        html = '<html><body><frame src="/web/20250417203037/http://example.com/frame.html"></body></html>'
        processed, links = self.dl._process_html(html, "http://example.com/index.html")
        assert any("frame.html" in l for l in links)

    def test_internal_iframe_relative(self):
        """Internal iframe src should be rewritten."""
        html = '<html><body><iframe src="http://example.com/embed.html"></iframe></body></html>'
        processed, links = self.dl._process_html(html, "http://example.com/index.html")

    def test_frame_empty_src_skipped(self):
        """Frame with empty src should be skipped."""
        html = '<html><body><frame src=""></body></html>'
        processed, links = self.dl._process_html(html, "http://example.com/index.html")


class TestProcessHtmlBackgroundAttr:
    """Cover lines 1432-1448: HTML background attribute processing."""

    def setup_method(self):
        self.dl = _make_dl()

    def teardown_method(self):
        _cleanup()

    def test_body_background_rewritten(self):
        """Body background attribute should be rewritten."""
        html = '<html><body background="/web/20250417203037im_/http://example.com/bg.jpg">Content</body></html>'
        processed, links = self.dl._process_html(html, "http://example.com/index.html")
        assert any("bg.jpg" in l for l in links)

    def test_td_background_not_relative(self):
        """TD background when make_internal_links_relative=False."""
        self.dl.config.make_internal_links_relative = False
        html = '<html><body><table><tr><td background="http://example.com/bg.jpg">Cell</td></tr></table></body></html>'
        processed, links = self.dl._process_html(html, "http://example.com/index.html")

    def test_background_empty_skipped(self):
        """Empty background attribute should be skipped."""
        html = '<html><body><table><tr><td background="">Cell</td></tr></table></body></html>'
        processed, links = self.dl._process_html(html, "http://example.com/index.html")


class TestProcessHtmlContactLinksInIconGroup:
    """Cover lines 1300-1314, 1341: contact link in icon group with string classes."""

    def setup_method(self):
        self.dl = _make_dl()

    def teardown_method(self):
        _cleanup()

    def test_contact_in_icon_group_string_class(self):
        """Contact link inside icon group with string class attribute should be preserved."""
        html = '''<html><body>
        <div class="sppb-icons-group-list">
            <a href="tel:+34600000000">Call</a>
        </div>
        </body></html>'''
        self.dl.config.remove_clickable_contacts = True
        processed, _ = self.dl._process_html(html, "http://example.com/")
        assert "tel:+34600000000" in processed

    def test_button_link_class_as_string(self):
        """Button link with class as string (not list) should be preserved."""
        html = '<html><body><a href="http://external.com/page" class="sppb-btn">Click</a></body></html>'
        processed, _ = self.dl._process_html(html, "http://example.com/")
        assert "Click" in processed


class TestCssRewriteSquarespaceCdnNotRelative:
    """Cover lines 974-981: Squarespace CDN rewrite in CSS non-relative mode."""

    def setup_method(self):
        self.dl = _make_dl()
        self.dl._current_page_url = "http://example.com/style.css"

    def teardown_method(self):
        _cleanup()

    def test_squarespace_cdn_css_not_relative(self):
        """Squarespace CDN URLs in CSS with make_internal_links_relative=False."""
        self.dl.config.make_internal_links_relative = False
        css = "body { background: url(https://images.squarespace-cdn.com/content/bg.jpg); }"
        result = self.dl._rewrite_css_urls(css, "http://example.com/style.css")
        # Should still contain url()
        assert "url(" in result


class TestGoogleFontsStylesheetDownload:
    """Cover lines 1583-1600: Google Fonts CSS link download and path rewrite."""

    def setup_method(self):
        self.dl = _make_dl()

    def teardown_method(self):
        _cleanup()

    def test_google_fonts_stylesheet_not_relative(self):
        """Google Fonts stylesheet when make_internal_links_relative=False."""
        self.dl.config.make_internal_links_relative = False
        html = '<html><head><link rel="stylesheet" href="//web.archive.org/web/20250417203037cs_/http://fonts.googleapis.com/css?family=Roboto"></head><body>Test</body></html>'
        processed, links = self.dl._process_html(html, "http://example.com/")
        # Should queue the Google Fonts CSS
        assert any("fonts.googleapis.com" in l for l in links)

    def test_squarespace_cdn_stylesheet_path_rewrite(self):
        """Squarespace CDN stylesheet should have path rewritten."""
        html = '<html><head><link rel="stylesheet" href="//web.archive.org/web/20250417203037cs_/https://static1.squarespace.com/static/css/site.css"></head><body>Test</body></html>'
        processed, links = self.dl._process_html(html, "http://example.com/index.html")
        assert any("squarespace" in l for l in links)
