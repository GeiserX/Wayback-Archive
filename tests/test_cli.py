"""Tests for CLI module."""

import os
import pytest
import sys
from unittest.mock import patch, MagicMock
from wayback_archive.cli import main


class TestCLI:
    """Test CLI functionality."""

    def test_main_missing_url(self, capsys):
        """Test CLI with missing URL."""
        os.environ.pop("WAYBACK_URL", None)
        
        with pytest.raises(SystemExit) as exc_info:
            main()
        
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "WAYBACK_URL" in captured.err

    def test_main_with_url(self, capsys):
        """Test CLI with valid URL."""
        os.environ["WAYBACK_URL"] = "https://web.archive.org/web/20250417203037/http://example.com/"
        
        with patch("wayback_archive.cli.WaybackDownloader") as mock_downloader_class:
            mock_downloader = MagicMock()
            mock_downloader_class.return_value = mock_downloader
            
            try:
                main()
            except SystemExit:
                pass  # May exit normally
            
            mock_downloader.download.assert_called_once()

        # Cleanup
        os.environ.pop("WAYBACK_URL", None)

    def test_main_keyboard_interrupt(self):
        """Test CLI handling keyboard interrupt."""
        os.environ["WAYBACK_URL"] = "https://web.archive.org/web/20250417203037/http://example.com/"
        
        with patch("wayback_archive.cli.WaybackDownloader") as mock_downloader_class:
            mock_downloader = MagicMock()
            mock_downloader.download.side_effect = KeyboardInterrupt()
            mock_downloader_class.return_value = mock_downloader
            
            with pytest.raises(SystemExit) as exc_info:
                main()
            
            assert exc_info.value.code == 1

        # Cleanup
        os.environ.pop("WAYBACK_URL", None)

