# How it works

1. **Initial download** -- Fetches the main page from the Wayback Machine. If that capture redirects to another host (a site that moved domains), the tool warns and archives the host that was actually captured
2. **Link extraction** -- Parses HTML to find all referenced assets (links, images, CSS, JS)
3. **CSS processing** -- Extracts font URLs, background images, and `@import` statements; downloads Google Fonts locally; detects corrupted font files
4. **JS processing** -- Extracts dynamically loaded resources from JavaScript
5. **Data attributes** -- Scans `data-*` attributes for additional asset URLs
6. **Iterative crawling** -- Continues discovering and downloading resources until the queue is empty
7. **Timeframe fallback** -- For 404 responses, tries up to three other timestamps: a day either side and a week earlier, skipping any that is an archived error or a challenge page and stopping at a 429. Wayback already answers any timestamp with the nearest capture, so closer probes would land on the same answer. A capture that is an archived error (403, 5xx) or a Cloudflare challenge page is replaced by the nearest capture with status 200, found with one query to the Wayback CDX index; when the start page is replaced, the rest of the site is fetched around that capture's timestamp
8. **URL rewriting** -- Converts all URLs to relative paths for offline serving
9. **Preservation** -- Maintains icon groups, button links, and cookie consent functionality

## Where requests go

Every file is requested from the Wayback Machine (`web.archive.org`). The tool never fetches the archived site's own domain, or any other host, from the live Internet: the domain may belong to someone else today, and what it serves now is not the archive. An answer that a redirect brought from any host other than `web.archive.org` or `archive.org` is discarded and counts as a failed file.

When the Wayback Machine throttles (HTTP 429) or is briefly down (its own 502, 503 or 504), the request is retried up to five times, waiting 0, 2, 4, 8 and 16 seconds plus up to a second of jitter, or as long as a `Retry-After` header asks, up to 120 seconds. An answer slower than the timeout is retried twice. An archived error capture (one that carries a `memento-datetime` header) is never retried: it is the page as it was captured. A file still refused after the retries counts toward the stop after 5 refusals in a row. With `REQUEST_DELAY` set (see [Configuration](configuration.md)), the tool also waits that many seconds, give or take 20%, before every Wayback request.

No file is read past 512 MiB: a larger one, or one whose `Content-Length` says it will be, is skipped and reported as failed.

The one exception is a short list of well-known CDN hosts. When the Wayback Machine does not have a file on one of these, the tool fetches it live, always over HTTPS on the default port (an `http://` reference is upgraded, any other port is refused), without following redirects:

- Google Fonts: `fonts.googleapis.com`, `fonts.gstatic.com`
- jQuery: `code.jquery.com` (also the source of the replacement when a site's own `jquery.min.js` is missing: the version its URL names, or 3.7.1)
- Squarespace: `static1.squarespace.com`, `static.squarespace.com`, `images.squarespace-cdn.com`, `sqspcdn.com` and its subdomains

A host matches only exactly or as a subdomain (`assets.sqspcdn.com`), never by containing the name (`sqspcdn.com.example.net`, `sqspcdn.com@10.0.0.1`), and a host with a backslash, `%`, whitespace, a control or a non-ASCII character never matches, since `requests` would connect somewhere else than the name suggests (`evil.com\.sqspcdn.com` goes to `evil.com`). Anything else the Wayback Machine does not have is reported as failed.

## Project structure

```
Wayback-Archive/
  wayback_archive/          # Main package
    __init__.py
    __main__.py
    cli.py                  # CLI entry point
    config.py               # Environment variable configuration
    downloader.py           # Core download and processing engine
  config/
    requirements.txt        # Runtime dependencies
    requirements-dev.txt    # Development dependencies
  tests/                    # Test suite
  docs/                     # Documentation
  pyproject.toml            # Package metadata, build and pytest configuration
  LICENSE                   # GPL-3.0
  README.md
```

## Dependencies

| Package | Purpose |
|---|---|
| [requests](https://pypi.org/project/requests/) | HTTP client |
| [beautifulsoup4](https://pypi.org/project/beautifulsoup4/) | HTML parsing |
| [lxml](https://pypi.org/project/lxml/) | Fast HTML/XML parser |
| [minify-html](https://pypi.org/project/minify-html/) | HTML minification |
| [cssmin](https://pypi.org/project/cssmin/) | CSS minification |
| [rjsmin](https://pypi.org/project/rjsmin/) | JS minification |
| [Pillow](https://pypi.org/project/Pillow/) | Image optimization |
| [python-dotenv](https://pypi.org/project/python-dotenv/) | `.env` file support |
