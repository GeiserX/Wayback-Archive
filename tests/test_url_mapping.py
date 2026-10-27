"""Each URL maps to one file whose name works on every filesystem.

Pages that differ only by query string (?id=1, ?id=2) used to share one
file, so all but the first were skipped. Names over 255 bytes failed with
ENAMETOOLONG, and names Windows refuses (CON, a:b) were written as is.
"""

import os

import pytest

from tests.test_crawl_and_storage import _make_downloader, _run
from wayback_archive.downloader import WaybackDownloader

SITE = "https://example.com"


@pytest.fixture
def dl(tmp_path):
    downloader = _make_downloader(output_dir=tmp_path / "out")
    yield downloader
    os.environ.pop("WAYBACK_URL", None)


def _name(dl, url, kind=None):
    return dl._get_local_path(url, kind).relative_to(dl.config.output_dir).as_posix()


class TestQueryStrings:
    def test_different_queries_get_different_files(self, dl):
        one = _name(dl, f"{SITE}/page?id=1")
        two = _name(dl, f"{SITE}/page?id=2")
        assert one != two
        assert one.startswith("page__q") and one.endswith(".html")
        assert len(one) == len("page__q") + 10 + len(".html")

    def test_key_order_does_not_matter(self, dl):
        assert _name(dl, f"{SITE}/p?a=1&b=2") == _name(dl, f"{SITE}/p?b=2&a=1")

    def test_server_page_keeps_its_extension_after_the_suffix(self, dl):
        name = _name(dl, f"{SITE}/index.php?id=3")
        assert name.startswith("index__q") and name.endswith(".php.html")

    def test_directory_query_lands_inside_the_directory(self, dl):
        assert _name(dl, f"{SITE}/?p=12").startswith("index__q")
        assert _name(dl, f"{SITE}/blog/?p=12").startswith("blog/index__q")

    def test_asset_query_keeps_the_real_extension(self, dl):
        name = _name(dl, f"{SITE}/thumb.png?w=200")
        assert name.startswith("thumb__q") and name.endswith(".png")

    @pytest.mark.parametrize(
        "query", ["v=3", "ver=5.2", "_=1612345", "t=1&cb=2", "VER=1", "nocache", "", "h=a&build=7"]
    )
    def test_cache_busters_fold_into_the_plain_file(self, dl, query):
        assert _name(dl, f"{SITE}/style.css?{query}") == "style.css"

    def test_cache_busters_do_not_change_a_real_query(self, dl):
        assert _name(dl, f"{SITE}/page?id=1&_=111") == _name(dl, f"{SITE}/page?id=1&_=222")

    def test_link_names_the_stored_file(self, dl):
        dl._current_page_url = f"{SITE}/"
        stored = _name(dl, f"{SITE}/page?id=1")
        assert dl._get_relative_link_path(f"{SITE}/page?id=1", "page") == f"{stored}?id=1"

    def test_crawl_stores_both_pages_and_links_each(self, tmp_path):
        index = f'<html><body><a href="{SITE}/page?id=1">one</a><a href="{SITE}/page?id=2">two</a></body></html>'
        pages = {
            f"{SITE}/": index.encode(),
            f"{SITE}/page?id=1": b"<html><body>first</body></html>",
            f"{SITE}/page?id=2": b"<html><body>second</body></html>",
        }
        _, files, out, output_dir = _run(tmp_path, pages)
        stored = sorted(f for f in files if f.startswith("page__q"))
        assert len(stored) == 2, files
        bodies = {(output_dir / f).read_text() for f in stored}
        assert any("first" in b for b in bodies) and any("second" in b for b in bodies)
        html = (output_dir / "index.html").read_text()
        for f in stored:
            assert f'href="{f}?id=' in html
        assert "Files failed: 0" in out


class TestLongNames:
    def test_300_char_segment_is_capped_and_kept_unique(self, dl):
        a = _name(dl, f"{SITE}/{'a' * 300}/x.png")
        b = _name(dl, f"{SITE}/{'a' * 299}b/x.png")
        assert a != b
        first = a.split("/")[0]
        assert len(first.encode()) <= WaybackDownloader.MAX_NAME_BYTES
        assert first.startswith("a" * 100) and "~" in first

    def test_capped_file_keeps_its_extension(self, dl):
        name = _name(dl, f"{SITE}/{'b' * 300}.png")
        assert name.endswith(".png") and len(name.encode()) <= WaybackDownloader.MAX_NAME_BYTES

    def test_multibyte_name_is_cut_on_a_character(self, dl):
        name = _name(dl, f"{SITE}/{'é' * 200}.jpg")
        assert len(name.encode()) <= WaybackDownloader.MAX_NAME_BYTES
        assert name.endswith(".jpg") and "�" not in name

    @pytest.mark.parametrize(
        "path, tail",
        [
            (f"/{'z' * 300}.php?id=1", ".php.html"),
            (f"/{'z' * 300}?id=1", ".html"),
            (f"/{'z' * 195}.php?id=1", ".php.html"),
        ],
    )
    def test_long_query_page_keeps_extension_and_query_suffix(self, dl, path, tail):
        name = _name(dl, SITE + path)
        assert len(name.encode()) <= WaybackDownloader.MAX_NAME_BYTES
        assert "~" in name and "__q" in name and name.endswith(tail)

    def test_over_long_path_writes_instead_of_failing(self, tmp_path):
        png = b"\x89PNG\r\n\x1a\nxx"
        long_path = "/" + "a" * 300 + "/x.png"
        pages = {
            f"{SITE}/": f'<html><body><img src="{SITE}{long_path}"></body></html>'.encode(),
            SITE + long_path: png,
        }
        _, _, out, _ = _run(tmp_path, pages)
        assert "Files failed: 0" in out

    def test_crawl_writes_the_long_file(self, tmp_path):
        long = "a" * 300
        png = b"\x89PNG\r\n\x1a\nxx"
        pages = {
            f"{SITE}/": f'<html><body><img src="{SITE}/{long}/x.png"></body></html>'.encode(),
            f"{SITE}/{long}/x.png": png,
        }
        _, files, out, output_dir = _run(tmp_path, pages)
        assert "Files failed: 0" in out
        stored = [f for f in files if f.endswith("/x.png")]
        assert len(stored) == 1
        assert (output_dir / stored[0]).read_bytes() == png
        assert f'src="{stored[0]}"' in (output_dir / "index.html").read_text()


class TestPortableNames:
    @pytest.mark.parametrize(
        "path, expected",
        [
            ("/CON", "CON_.html"),
            ("/nul.txt", "nul_.txt"),
            ("/com1.png", "com1_.png"),
            ("/LPT9/a.png", "LPT9_/a.png"),
            ("/console.png", "console.png"),
            ("/a%3Ab%7Cc%2A.png", "a_b_c_.png"),
            ("/q%22%3C%3E.png", "q___.png"),
            ("/dir.%20/a.png", "dir/a.png"),
        ],
    )
    def test_windows_rules_apply_on_every_os(self, dl, path, expected):
        assert _name(dl, SITE + path) == expected

    def test_question_mark_in_a_name_is_stored_and_linked_as_underscore(self, dl):
        dl._current_page_url = f"{SITE}/"
        assert _name(dl, f"{SITE}/a%3Fb.png") == "a_b.png"
        assert dl._get_relative_link_path(f"{SITE}/a%3Fb.png", "asset") == "a_b.png"

    def test_sanitising_twice_changes_nothing(self, dl):
        for path in ("/CON", "/a%3Ab.png", f"/{'z' * 300}", f"/{'z' * 300}?id=1"):
            name = _name(dl, SITE + path)
            assert dl._sanitize_output_relpath(name) == name


class TestWaybackUrlParsing:
    @pytest.mark.parametrize(
        "wayback_url, base_url",
        [
            ("HTTPS://WEB.ARCHIVE.ORG/web/2020/https://example.com/", "https://example.com/"),
            ("  https://web.archive.org/web/2020/https://example.com/\n", "https://example.com/"),
            ("https://web.archive.org/web/2020/HTTPS://Example.COM/Path", "https://example.com/Path"),
            ("https://web.archive.org/web/2020/https:/example.com/x", "https://example.com/x"),
            ("https://web.archive.org/web/2020/example.com/x", "http://example.com/x"),
        ],
    )
    def test_base_url_and_domain(self, wayback_url, base_url):
        dl = _make_downloader(wayback_url=wayback_url)
        assert dl.config.base_url == base_url
        assert dl.config.domain == "example.com"


class TestWaybackReferences:
    @pytest.mark.parametrize(
        "ref", ["https://evil.com/web/2020/https://x.com/a", "https://notarchive.org/web/2020/https://x.com/a"]
    )
    def test_other_hosts_are_not_wayback_references(self, dl, ref):
        assert dl._extract_original_url_from_path(ref) is None

    def test_uppercase_archive_host_mailto_extracts(self, dl):
        assert dl._extract_original_url_from_path("HTTPS://WEB.ARCHIVE.ORG/web/2020/mailto:a@b.c") == "mailto:a@b.c"

    def test_site_path_with_web_segment_is_not_a_wayback_reference(self, dl):
        assert dl._extract_original_url_from_path(f"{SITE}/blog/web/2020/http://x.com/a") is None
        assert dl._extract_original_url_from_path("/blog/web/20200101/https://x.com/a") is None

    @pytest.mark.parametrize(
        "ref",
        [
            "/web/2020/https://x.com/a",
            "https://web.archive.org/web/2020im_/https://x.com/a",
            "http://archive.org/web/2020/https://x.com/a",
            "//web.archive.org/web/2020/https://x.com/a",
            "url('/web/2020/https://x.com/a')",
            "http://wayback.archive.org/web/2020/https://x.com/a",
            "https://web-beta.archive.org/web/2020/https://x.com/a",
            "HTTPS://WEB.ARCHIVE.ORG/web/2020/https://x.com/a",
        ],
    )
    def test_wayback_references_still_extract(self, dl, ref):
        assert dl._extract_original_url_from_path(ref) == "https://x.com/a"

    @pytest.mark.parametrize(
        "url",
        [
            "https://archive.org/web/2020/https://example.com/",
            "http://web.archive.org/web/2020/https://example.com/",
        ],
    )
    def test_archive_urls_are_not_wrapped_again(self, dl, url):
        assert dl._convert_to_wayback_url(url) == url

    def test_other_archive_org_pages_are_wrapped(self, dl):
        assert dl._convert_to_wayback_url("https://archive.org/details/x").startswith("https://web.archive.org/web/")
