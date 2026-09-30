import ipaddress
import socket

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


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Fail any test that opens a real connection instead of mocking it.

    Without this a test that forgets a mock still passes, just slowly, while
    asserting nothing about the code it meant to cover. Loopback stays open
    for the tests that run a local HTTP server.
    """

    def guard(real):
        def connect(self, address, *args, **kwargs):
            if not _is_local(address):
                raise RuntimeError(f"test tried a real network connection to {address!r}")
            return real(self, address, *args, **kwargs)
        return connect

    monkeypatch.setattr(socket.socket, "connect", guard(_real_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guard(_real_connect_ex))
