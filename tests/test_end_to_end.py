"""The whole tool against a fake Wayback Machine on 127.0.0.1.

Nothing is mocked inside the downloader: cli.main() parses real flags, the
requests session makes real HTTP requests, and the files land on disk. Only
the host is swapped, from https://web.archive.org to the loopback server.
"""

import http.server
import re
import threading

import pytest
import requests

from wayback_archive import cli

TS = "20200101000000"
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4

PAGES = {
    "http://example.com/": (
        "text/html",
        (
            "<!DOCTYPE html><html><head><title>Home</title>"
            f'<link rel="stylesheet" href="/web/{TS}cs_/http://example.com/style.css">'
            "</head><body><h1>Home</h1>"
            '<img src="logo.png" alt="logo">'
            '<img src="missing.png" alt="gone">'
            '<a href="about.html">About</a>'
            "</body></html>"
        ).encode(),
    ),
    "http://example.com/about.html": (
        "text/html",
        b'<!DOCTYPE html><html><head><title>About</title></head><body><a href="/">Home</a></body></html>',
    ),
    "http://example.com/style.css": ("text/css", b"body { color: #333; }\n"),
    "http://example.com/logo.png": ("image/png", PNG),
}


class _FakeWayback(http.server.BaseHTTPRequestHandler):
    """Serves PAGES at /web/<timestamp>[modifier_]/<original URL>; 404 otherwise."""

    def do_GET(self):
        self.server.requests.append(self.path)
        match = re.match(r"/web/\d+(?:[a-z]+_)?/(.+)", self.path)
        found = PAGES.get(match.group(1)) if match else None
        if found is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        content_type, body = found
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def fake_wayback(monkeypatch):
    server = http.server.HTTPServer(("127.0.0.1", 0), _FakeWayback)
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}/"
    real_get = requests.Session.get

    def get(self, url, **kwargs):
        response = real_get(self, url.replace("https://web.archive.org/", base, 1), **kwargs)
        # The downloader rejects a response whose final URL left web.archive.org,
        # so the loopback answer has to report the Wayback URL it stood in for.
        response.url = response.url.replace(base, "https://web.archive.org/", 1)
        return response

    monkeypatch.setattr(requests.Session, "get", get)
    yield server
    server.shutdown()
    server.server_close()


def test_a_small_site_is_rebuilt_offline(fake_wayback, tmp_path, capsys):
    out = tmp_path / "site"
    try:
        cli.main([f"https://web.archive.org/web/{TS}/http://example.com/", "-o", str(out), "--no-optimize-html"])
        code = 0
    except SystemExit as e:
        code = e.code

    assert code == 0, capsys.readouterr().err
    index = (out / "index.html").read_text()
    assert (out / "style.css").read_text() == "body { color: #333; }\n"
    assert (out / "logo.png").read_bytes() == PNG
    assert (out / "about.html").exists()
    assert not (out / "missing.png").exists()
    assert re.search(r'<link[^>]+href="style\.css"', index)
    assert 'src="logo.png"' in index
    assert "web.archive.org" not in index
    # Every request went to the loopback server and asked for a capture.
    assert fake_wayback.requests and all(path.startswith(("/web/", "/cdx/")) for path in fake_wayback.requests)
    assert any("missing.png" in path for path in fake_wayback.requests)
