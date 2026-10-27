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


URL = "https://web.archive.org/web/20250417203037/http://example.com/"


class TestStrictValues:
    @pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "On", " on "])
    def test_true_spellings(self, monkeypatch, value):
        monkeypatch.setenv("MINIFY_JS", value)
        assert Config().minify_js is True

    @pytest.mark.parametrize("value", ["false", "False", "0", "no", "OFF"])
    def test_false_spellings(self, monkeypatch, value):
        monkeypatch.setenv("OPTIMIZE_HTML", value)
        assert Config().optimize_html is False

    def test_a_typo_is_an_error_naming_the_variable(self, monkeypatch):
        monkeypatch.setenv("WAYBACK_URL", URL)
        monkeypatch.setenv("REMOVE_TRACKERS", "flase")
        is_valid, error = Config().validate()
        assert is_valid is False
        assert "REMOVE_TRACKERS" in error and "'flase'" in error

    def test_empty_boolean_means_the_default(self, monkeypatch):
        monkeypatch.setenv("OPTIMIZE_HTML", "")
        config = Config()
        assert config.optimize_html is True
        assert config.errors == []

    def test_empty_output_dir_means_the_default(self, monkeypatch):
        monkeypatch.setenv("OUTPUT_DIR", "")
        assert Config().output_dir == "./output"
        assert Config(output_dir="").output_dir == "./output"

    @pytest.mark.parametrize("value, expected", [("", 0.0), ("0", 0.0), ("1.5", 1.5)])
    def test_request_delay(self, monkeypatch, value, expected):
        monkeypatch.setenv("REQUEST_DELAY", value)
        config = Config()
        assert config.request_delay == expected
        assert config.errors == []

    @pytest.mark.parametrize("value", ["-1", "soon", "nan", "inf"])
    def test_bad_request_delay(self, monkeypatch, value):
        monkeypatch.setenv("REQUEST_DELAY", value)
        config = Config()
        assert config.request_delay == 0.0
        assert any("REQUEST_DELAY" in error for error in config.errors)

    def test_request_delay_defaults_to_zero(self):
        assert Config().request_delay == 0.0


class TestWww:
    def test_make_www_alone_turns_off_the_non_www_default(self, monkeypatch):
        monkeypatch.setenv("MAKE_WWW", "true")
        config = Config()
        assert (config.make_www, config.make_non_www) == (True, False)
        assert config.errors == []

    def test_both_set_true_is_an_error(self, monkeypatch):
        monkeypatch.setenv("MAKE_WWW", "true")
        monkeypatch.setenv("MAKE_NON_WWW", "true")
        config = Config()
        assert any("MAKE_WWW" in error and "MAKE_NON_WWW" in error for error in config.errors)

    def test_make_www_with_non_www_explicitly_off_is_fine(self):
        config = Config(make_www=True, make_non_www=False)
        assert (config.make_www, config.make_non_www) == (True, False)
        assert config.errors == []


class TestOverrides:
    def test_an_override_beats_the_environment(self, monkeypatch):
        monkeypatch.setenv("WAYBACK_URL", "https://web.archive.org/web/2020/http://env.example/")
        monkeypatch.setenv("OPTIMIZE_HTML", "false")
        monkeypatch.setenv("MAX_FILES", "9")
        config = Config(wayback_url=URL, optimize_html=True, max_files=3)
        assert (config.wayback_url, config.optimize_html, config.max_files) == (URL, True, 3)

    def test_none_means_not_given(self, monkeypatch):
        monkeypatch.setenv("MINIFY_CSS", "true")
        assert Config(minify_css=None).minify_css is True

    def test_bad_override_names_the_option(self):
        assert Config(max_files=0).errors == ["max_files must be a positive whole number, got 0"]
        assert "request_delay" in Config(request_delay=-2).errors[0]

    def test_unknown_override_is_a_type_error(self):
        with pytest.raises(TypeError, match="optimise_html"):
            Config(optimise_html=True)

    def test_env_vars_lists_every_option(self):
        assert set(Config.ENV_VARS) == {env for _, env, _ in Config.BOOL_OPTIONS + Config.VALUE_OPTIONS}
        assert {"WAYBACK_URL", "OUTPUT_DIR", "MAX_FILES", "REQUEST_DELAY", "MAKE_WWW"} <= set(Config.ENV_VARS)


class TestCleanEnvironment:
    """conftest removes every variable Config reads before each test."""

    def test_set_in_one_test(self):
        os.environ["MINIFY_JS"] = "true"

    def test_gone_in_the_next(self):
        assert "MINIFY_JS" not in os.environ
