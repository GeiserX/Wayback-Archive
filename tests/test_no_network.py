"""The conftest guard must stop a real connection, or it guards nothing."""

import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

CONFTEST = Path(__file__).with_name("conftest.py")


def test_a_real_connection_is_refused(_no_network):
    # 192.0.2.0/24 is TEST-NET-1: never routed, so without the guard this
    # times out instead of raising the guard's error.
    with pytest.raises(RuntimeError, match="real network connection"):
        socket.create_connection(("192.0.2.1", 80), timeout=1)
    _no_network.clear()  # expected here; any other test would fail at teardown


def _run_with_guard(tmp_path, test_body, **env):
    """Run one test file under the real conftest in a fresh pytest process."""
    (tmp_path / "conftest.py").write_text(CONFTEST.read_text())
    (tmp_path / "test_inner.py").write_text(test_body)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", str(tmp_path)],
        cwd=tmp_path, env={**os.environ, **env}, capture_output=True, text=True, timeout=60,
    )


def test_a_loopback_proxy_does_not_bypass_the_guard(tmp_path):
    # A developer shell exporting HTTPS_PROXY=http://127.0.0.1:<port> made
    # requests connect to loopback (allowed) while the proxy went online.
    proxy = "http://127.0.0.1:9"
    result = _run_with_guard(
        tmp_path,
        "import requests\n\n"
        "def test_inner():\n"
        "    requests.get('http://192.0.2.1/', timeout=2)\n",
        HTTP_PROXY=proxy, HTTPS_PROXY=proxy, http_proxy=proxy, https_proxy=proxy,
        NO_PROXY="", no_proxy="",
    )
    assert "real network connection to ('192.0.2.1', 80)" in result.stdout, result.stdout


def test_a_swallowed_guard_error_still_fails_the_test(tmp_path):
    # The downloader catches every fetch error, so a test that forgets a mock
    # would otherwise see None and pass.
    result = _run_with_guard(
        tmp_path,
        "import socket\n\n"
        "def test_inner():\n"
        "    try:\n"
        "        socket.create_connection(('192.0.2.1', 80), timeout=1)\n"
        "    except Exception:\n"
        "        pass\n",
    )
    assert result.returncode == 1, result.stdout
    assert "real network connection to [('192.0.2.1', 80)]" in result.stdout, result.stdout
