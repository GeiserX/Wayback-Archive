"""Tests for CLI module."""

import os
from unittest.mock import MagicMock, patch

import pytest

from wayback_archive import __version__, cli
from wayback_archive.cli import main
from wayback_archive.config import Config

URL = "https://web.archive.org/web/20250417203037/http://example.com/"


def _run(argv, monkeypatch=None, download=None):
    """Run main(argv) with a fake downloader; return (exit code, the Config it got)."""
    seen = {}

    class FakeDownloader:
        def __init__(self, config):
            seen["config"] = config

        def download(self):
            if download:
                download()

    with patch.object(cli, "WaybackDownloader", FakeDownloader):
        try:
            main(argv)
            code = 0
        except SystemExit as e:
            code = e.code
    return code, seen.get("config")


class TestCLI:
    """Test CLI functionality."""

    def test_main_missing_url(self, capsys):
        """No URL anywhere is a usage error that names WAYBACK_URL."""
        with pytest.raises(SystemExit) as exc_info:
            main([])

        assert exc_info.value.code == 2
        captured = capsys.readouterr()
        assert "WAYBACK_URL" in captured.err

    def test_main_with_url(self, capsys):
        """Test CLI with valid URL."""
        os.environ["WAYBACK_URL"] = URL

        with patch("wayback_archive.cli.WaybackDownloader") as mock_downloader_class:
            mock_downloader = MagicMock()
            mock_downloader_class.return_value = mock_downloader

            main()

            mock_downloader.download.assert_called_once()

    def test_main_keyboard_interrupt(self, capsys):
        """Ctrl-C exits 130 and says so on stderr."""
        os.environ["WAYBACK_URL"] = URL

        with patch("wayback_archive.cli.WaybackDownloader") as mock_downloader_class:
            mock_downloader = MagicMock()
            mock_downloader.download.side_effect = KeyboardInterrupt()
            mock_downloader_class.return_value = mock_downloader

            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code == 130
        assert "Interrupted" in capsys.readouterr().err


class TestFlags:
    def test_help_works_without_a_url_and_lists_every_option(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0
        out = " ".join(capsys.readouterr().out.split())
        for name, env, _ in Config.BOOL_OPTIONS:
            flag = name.replace("_", "-")
            assert f"--{flag}" in out and f"--no-{flag}" in out
            assert f"env {env}," in out
        for flag, env in (
            ("--output-dir", "OUTPUT_DIR"),
            ("--max-files", "MAX_FILES"),
            ("--request-delay", "REQUEST_DELAY"),
        ):
            assert flag in out and f"env {env}," in out
        assert "env WAYBACK_URL" in out
        assert "https://geiserx.github.io/Wayback-Archive/" in out

    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0
        assert capsys.readouterr().out.strip() == f"wayback-archive {__version__}"

    def test_positional_url_and_options(self, tmp_path):
        code, config = _run(
            [
                URL,
                "-o",
                str(tmp_path),
                "--max-files",
                "5",
                "--request-delay",
                "0.5",
                "--no-optimize-html",
                "--minify-css",
            ]
        )
        assert code == 0
        assert config.wayback_url == URL
        assert config.output_dir == str(tmp_path)
        assert config.max_files == 5
        assert config.request_delay == 0.5
        assert config.optimize_html is False
        assert config.minify_css is True
        assert config.remove_ads is True  # untouched default

    def test_flag_beats_environment_which_beats_default(self):
        os.environ["WAYBACK_URL"] = "https://web.archive.org/web/2020/http://env.example/"
        os.environ["OPTIMIZE_HTML"] = "false"
        os.environ["MINIFY_JS"] = "true"
        os.environ["MAX_FILES"] = "9"
        code, config = _run([URL, "--optimize-html", "--max-files", "3"])
        assert code == 0
        assert config.wayback_url == URL
        assert config.optimize_html is True
        assert config.max_files == 3
        assert config.minify_js is True  # from the environment
        assert config.minify_css is False  # the default

    def test_environment_beats_dotenv_and_only_cwd_dotenv_is_read(self, tmp_path, monkeypatch):
        parent = tmp_path / "parent"
        child = parent / "child"
        child.mkdir(parents=True)
        (parent / ".env").write_text("MINIFY_JS=true\n")
        monkeypatch.chdir(child)
        code, config = _run([URL])
        assert code == 0
        assert config.minify_js is False  # the parent's .env is not read

        (child / ".env").write_text("MINIFY_CSS=true\nOPTIMIZE_HTML=false\n")
        monkeypatch.setenv("OPTIMIZE_HTML", "true")
        monkeypatch.delenv("MINIFY_CSS", raising=False)
        code, config = _run([URL])
        assert config.minify_css is True  # from .env
        assert config.optimize_html is True  # the environment wins over .env
        monkeypatch.delenv("MINIFY_CSS", raising=False)

    @pytest.mark.parametrize(
        "argv", [["--max-files", "0"], ["--max-files", "x"], ["--request-delay", "-1"], ["--bogus"]]
    )
    def test_bad_flag_values_exit_2(self, argv, capsys):
        code, config = _run([URL, *argv])
        assert code == 2
        assert config is None
        assert "error:" in capsys.readouterr().err

    def test_bad_environment_value_exits_2_naming_it(self, capsys):
        os.environ["REMOVE_ADS"] = "ture"
        code, config = _run([URL])
        assert code == 2
        assert config is None
        assert "REMOVE_ADS" in capsys.readouterr().err

    def test_run_error_exits_1_without_traceback(self, capsys):
        def fail():
            raise RuntimeError("Nothing was saved")

        code, _ = _run([URL], download=fail)
        err = capsys.readouterr().err
        assert code == 1
        assert err == "Error: Nothing was saved\n"

    def test_unexpected_error_exits_1_with_traceback(self, capsys):
        def fail():
            raise KeyError("boom")

        code, _ = _run([URL], download=fail)
        err = capsys.readouterr().err
        assert code == 1
        assert err.startswith("Error: 'boom'\n")
        assert "Traceback" in err

    def test_constructor_failure_exits_1_like_a_failed_run(self, capsys):
        """An error while building the downloader gets the run's exit code and message."""

        def fail(config):
            raise PermissionError("output directory is not writable")

        with patch.object(cli, "WaybackDownloader", fail), pytest.raises(SystemExit) as exc_info:
            main([URL])
        err = capsys.readouterr().err
        assert exc_info.value.code == 1
        assert err.startswith("Error: output directory is not writable\n")

    def test_constructor_interrupted_exits_130(self, capsys):
        def interrupt(config):
            raise KeyboardInterrupt

        with patch.object(cli, "WaybackDownloader", interrupt), pytest.raises(SystemExit) as exc_info:
            main([URL])
        assert exc_info.value.code == 130
        assert "Interrupted" in capsys.readouterr().err

    def test_not_a_wayback_url_exits_1_without_traceback(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["https://example.com/"])
        err = capsys.readouterr().err
        assert exc_info.value.code == 1
        assert err.startswith("Error: WAYBACK_URL must look like")
        assert "Traceback" not in err


class TestPythonAPI:
    def test_download_builds_config_from_arguments(self, tmp_path):
        import wayback_archive

        seen = {}

        class FakeDownloader:
            def __init__(self, config):
                seen["config"] = config

            def download(self):
                seen["ran"] = True

        with patch("wayback_archive.downloader.WaybackDownloader", FakeDownloader):
            wayback_archive.download(URL, str(tmp_path), optimize_html=False, max_files=7)
        config = seen["config"]
        assert seen["ran"]
        assert (config.wayback_url, config.output_dir) == (URL, str(tmp_path))
        assert config.optimize_html is False and config.max_files == 7

    def test_download_rejects_bad_options(self):
        import wayback_archive

        with pytest.raises(ValueError, match="max_files"):
            wayback_archive.download(URL, max_files=0)
        with pytest.raises(TypeError, match="no_such_option"):
            wayback_archive.download(URL, no_such_option=True)

    def test_all(self):
        import wayback_archive

        assert wayback_archive.__all__ == ["download", "__version__"]
