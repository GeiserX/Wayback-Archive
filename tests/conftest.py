import ipaddress
import socket
import sys

import pytest

_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def _is_local(address):
    """A loopback or Unix socket address: a test server, not the internet."""
    if not isinstance(address, tuple):
        return True
    try:
        return ipaddress.ip_address(address[0]).is_loopback
    except ValueError:
        return address[0] == "localhost"


_PROXY_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")


@pytest.fixture(autouse=True)
def _clean_config_env(monkeypatch):
    """Start every test with none of the variables Config reads, so settings
    exported in the developer's shell cannot change a result, and with no
    command-line arguments, so cli.main() does not parse pytest's own."""
    monkeypatch.setattr(sys, "argv", ["wayback-archive"])
    try:
        from wayback_archive.config import Config
    except ImportError:  # test_no_network runs this file outside the project
        return
    for name in Config.ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Fail any test that opens a real connection instead of mocking it.

    The downloader catches every fetch error, so raising alone is not enough:
    a test that forgets a mock would get None back and pass. Each blocked
    address is recorded and the test fails at teardown. A test that expects
    the block clears the returned list. Proxy variables are removed, or
    requests would connect to a loopback proxy that goes online for it.
    Loopback stays open for the tests that run a local HTTP server.
    """
    blocked = []

    def guard(real):
        def connect(self, address, *args, **kwargs):
            if not _is_local(address):
                blocked.append(address)
                raise RuntimeError(f"test tried a real network connection to {address!r}")
            return real(self, address, *args, **kwargs)

        return connect

    for name in _PROXY_VARS:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    monkeypatch.setattr(socket.socket, "connect", guard(_real_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guard(_real_connect_ex))
    yield blocked
    if blocked:
        pytest.fail(f"test tried a real network connection to {blocked!r}; mock it")
