"""The conftest guard must stop a real connection, or it guards nothing."""

import socket

import pytest


def test_a_real_connection_is_refused():
    # 192.0.2.0/24 is TEST-NET-1: never routed, so without the guard this
    # times out instead of raising the guard's error.
    with pytest.raises(RuntimeError, match="real network connection"):
        socket.create_connection(("192.0.2.1", 80), timeout=1)
