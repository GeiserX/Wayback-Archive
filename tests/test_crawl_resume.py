"""The crawl loop: resuming an interrupted run, safe writes, and the summary."""

import contextlib
import io
import json
import os
from unittest.mock import patch

import pytest

from wayback_archive.config import Config
from wayback_archive.downloader import WaybackDownloader

WAYBACK_URL = "https://web.archive.org/web/20200101000000/http://example.com/"
SITE = "http://example.com"


@pytest.fixture(autouse=True)
def _clean_env():
    yield
    os.environ.pop("WAYBACK_URL", None)


def _make_downloader(output_dir, wayback_url=WAYBACK_URL, max_files=None):
    os.environ["WAYBACK_URL"] = wayback_url
    config = Config()
    config.output_dir = str(output_dir)
    config.max_files = max_files
    return WaybackDownloader(config)


def _page(*paths):
    links = "".join(f'<a href="{SITE}{p}">x</a>' for p in paths)
    return f"<html><body>{links}</body></html>".encode()


def _site(n_pages):
    """A home page linking to n pages, each a plain page."""
    paths = [f"/p{i}.html" for i in range(n_pages)]
    pages = {SITE + "/": _page(*paths)}
    pages.update({SITE + p: _page() for p in paths})
    return pages


def _serve(dl, pages, interrupt_at=None, refuse=()):
    """Answer download_file from a dict of pages; return the list of calls."""
    calls = []

    def fake_download_file(url):
        calls.append(url)
        if url == interrupt_at:
            raise KeyboardInterrupt
        if url in refuse:
            dl._last_failure = "throttled"
            return None
        dl._last_failure = None
        return pages.get(url)

    dl.download_file = fake_download_file
    return calls


def _run(dl, pages, refuse=()):
    """Run download() against a dict of pages; return (calls, output)."""
    calls = _serve(dl, pages, refuse=refuse)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        dl.download()
    return calls, out.getvalue()


def _run_interrupted(dl, pages, interrupt_at):
    _serve(dl, pages, interrupt_at=interrupt_at)
    out = io.StringIO()
    with pytest.raises(KeyboardInterrupt), contextlib.redirect_stdout(out):
        dl.download()
    return out.getvalue()


def _state(output_dir):
    return json.loads((output_dir / WaybackDownloader.STATE_FILE).read_text())


class TestResume:
    def test_interrupted_run_resumes_without_refetching(self, tmp_path):
        out_dir = tmp_path / "out"
        pages = _site(4)
        out = _run_interrupted(_make_downloader(out_dir), pages, interrupt_at=SITE + "/p2.html")

        assert "Download interrupted" in out
        assert "Files successfully downloaded: 3" in out
        state = _state(out_dir)
        assert state["complete"] is False
        assert state["queue"][0] == SITE + "/p2.html"  # the interrupted file goes back first
        assert not (out_dir / "p2.html").exists()

        calls, out = _run(_make_downloader(out_dir), pages)
        assert "Resuming: 3 files done, 2 queued" in out
        assert calls == [SITE + "/p2.html", SITE + "/p3.html"]
        assert "Files successfully downloaded: 5" in out
        assert "Files skipped (duplicates): 0" in out
        assert "Download Complete!" in out
        assert not (out_dir / WaybackDownloader.STATE_FILE).exists()
        assert {p.name for p in out_dir.iterdir()} == {"index.html"} | {f"p{i}.html" for i in range(4)}

    def test_same_folder_named_another_way_resumes(self, tmp_path, monkeypatch):
        pages = _site(3)
        _run_interrupted(_make_downloader(tmp_path / "out"), pages, interrupt_at=SITE + "/p1.html")
        monkeypatch.chdir(tmp_path)
        calls, _ = _run(_make_downloader("out"), pages)
        assert calls == [SITE + "/p1.html", SITE + "/p2.html"]

    def test_other_wayback_url_starts_fresh(self, tmp_path):
        out_dir = tmp_path / "out"
        _run_interrupted(_make_downloader(out_dir), _site(2), interrupt_at=SITE + "/p1.html")

        other = "https://web.archive.org/web/20210101000000/http://example.com/"
        calls, out = _run(_make_downloader(out_dir, wayback_url=other), _site(2))
        assert "starting fresh" in out
        assert "Resuming" not in out
        assert calls[0] == SITE + "/"

    def test_state_is_saved_every_25_files(self, tmp_path):
        out_dir = tmp_path / "out"
        dl = _make_downloader(out_dir)
        pages = _site(30)
        seen = {}
        real_save = dl._save_state

        def spy(*args):
            seen.setdefault("visited", len(dl.config.visited_urls))
            real_save(*args)

        dl._save_state = spy
        _run(dl, pages)
        assert seen["visited"] == 25

    def test_resume_keeps_extensionless_kinds(self, tmp_path):
        # The extension an extensionless stylesheet got must survive the
        # restart, or the resumed run saves it as a page.
        out_dir = tmp_path / "out"
        css = b"body{color:red}"
        pages = {
            SITE + "/": b'<html><head><link rel="stylesheet" href="http://example.com/theme"></head>'
            b'<body><a href="http://example.com/a.html">a</a></body></html>',
            SITE + "/a.html": _page(),
            SITE + "/theme": css,
        }
        _run_interrupted(_make_downloader(out_dir), pages, interrupt_at=SITE + "/theme")
        _run(_make_downloader(out_dir), pages)
        assert (out_dir / "theme.css").read_bytes() == css


class TestStops:
    def test_max_files_names_what_was_left_and_can_resume(self, tmp_path):
        out_dir = tmp_path / "out"
        pages = _site(4)
        _, out = _run(_make_downloader(out_dir, max_files=2), pages)
        assert "Stopped at MAX_FILES; 3 queued URLs not fetched" in out
        assert _state(out_dir)["complete"] is False

        calls, out = _run(_make_downloader(out_dir), pages)
        assert "Resuming: 2 files done, 3 queued" in out
        assert len(calls) == 3

    def test_refused_urls_are_retried_by_the_next_run(self, tmp_path):
        out_dir = tmp_path / "out"
        pages = _site(6)
        refused = {SITE + f"/p{i}.html" for i in range(1, 6)}
        with pytest.raises(RuntimeError, match="refused 5 requests in a row"):
            _run(_make_downloader(out_dir), pages, refuse=refused)

        calls, out = _run(_make_downloader(out_dir), pages)
        assert sorted(calls) == sorted(refused)
        assert "Files failed: 0" in out

    def test_jquery_rescued_by_the_cdn_ends_a_refusal_streak(self, tmp_path):
        out_dir = tmp_path / "out"
        paths = [f"/p{i}.html" for i in range(4)] + ["/jquery.min.js"] + [f"/q{i}.html" for i in range(4)]
        pages = {SITE + "/": _page(*paths)}
        refused = {SITE + p for p in paths}
        dl = _make_downloader(out_dir)
        with patch.object(dl, "_fetch_from_live_cdn", return_value=b"/*jq*/"):
            _, out = _run(dl, pages, refuse=refused)
        assert "Download Complete!" in out
        assert "Files failed: 8" in out


class TestSummary:
    def test_failed_urls_are_listed_and_capped(self, tmp_path):
        paths = [f"/missing{i:02}.png" for i in range(53)]
        pages = {SITE + "/": b"<html><body>" + "".join(f'<img src="{SITE}{p}">' for p in paths).encode() + b"</body>"}
        _, out = _run(_make_downloader(tmp_path / "out"), pages)
        out = out[out.index("Download Complete!") :]
        assert "Files failed: 53" in out
        assert "Total files processed: 54" in out
        assert f"\n  {SITE}/missing00.png\n" in out
        assert f"{SITE}/missing49.png" in out
        assert f"{SITE}/missing50.png" not in out
        assert "  ... and 3 more" in out

    def test_a_page_whose_processing_fails_counts_as_failed(self, tmp_path):
        out_dir = tmp_path / "out"
        pages = _site(1)
        dl = _make_downloader(out_dir)
        real = dl._process_html

        def flaky(html, base_url):
            if base_url.endswith("p0.html"):
                raise ValueError("broken")
            return real(html, base_url)

        dl._process_html = flaky
        _, out = _run(dl, pages)
        assert "Files successfully downloaded: 1" in out
        assert "Files failed: 1" in out
        assert (out_dir / "p0.html").read_bytes() == pages[SITE + "/p0.html"]

    def test_an_archived_file_cannot_overwrite_the_state(self, tmp_path):
        out_dir = tmp_path / "out"
        pages = {SITE + "/": _page("/.wayback-archive-state.json"), SITE + "/.wayback-archive-state.json": b"{}"}
        calls, out = _run(_make_downloader(out_dir), pages)
        assert "Files failed: 1" in out
        assert SITE + "/.wayback-archive-state.json" not in calls


class TestWriteFile:
    def test_a_failed_write_leaves_the_old_file_and_no_temp(self, tmp_path):
        dl = _make_downloader(tmp_path)
        target = tmp_path / "a.html"
        target.write_bytes(b"old")
        with patch("wayback_archive.downloader.os.replace", side_effect=KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                dl._write_file(target, "new")
        assert target.read_bytes() == b"old"
        assert [p.name for p in tmp_path.iterdir()] == ["a.html"]

    def test_text_is_encoded(self, tmp_path):
        dl = _make_downloader(tmp_path)
        dl._write_file(tmp_path / "a.css", "é", "utf-8")
        assert (tmp_path / "a.css").read_bytes() == "é".encode()
