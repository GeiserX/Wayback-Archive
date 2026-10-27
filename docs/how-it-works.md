# How it works

1. **Initial download** -- Fetches the main page from the Wayback Machine. If that capture redirects to another host (a site that moved domains), the tool warns and archives the host that was actually captured
2. **Link extraction** -- Parses HTML to find all referenced assets (links, images, CSS, JS)
3. **CSS processing** -- Extracts font URLs, background images, and `@import` statements; downloads Google Fonts locally; detects corrupted font files
4. **JS processing** -- Extracts dynamically loaded resources from JavaScript
5. **Data attributes** -- Scans `data-*` attributes for additional asset URLs
6. **Iterative crawling** -- Continues discovering and downloading resources until the queue is empty
7. **Timeframe fallback** -- For 404 responses, tries up to three other timestamps: a day either side and a week earlier. Wayback already answers any timestamp with the nearest capture, so closer probes would land on the same answer. A capture that is an archived error (403, 5xx) or a Cloudflare challenge page is replaced by the nearest capture with status 200, found with one query to the Wayback CDX index; when the start page is replaced, the rest of the site is fetched around that capture's timestamp
8. **URL rewriting** -- Converts all URLs to relative paths for offline serving
9. **Preservation** -- Maintains icon groups, button links, and cookie consent functionality

## Where requests go

Every file is requested from the Wayback Machine (`web.archive.org`). The tool never fetches the archived site's own domain, or any other host, from the live Internet: the domain may belong to someone else today, and what it serves now is not the archive.

The one exception is a short list of well-known CDN hosts. When the Wayback Machine does not have a file on one of these, the tool fetches it live, without following redirects:

- Google Fonts: `fonts.googleapis.com`, `fonts.gstatic.com`
- jQuery: `code.jquery.com` (also the source of the replacement when a site's own `jquery.min.js` is missing: the version its URL names, or 3.7.1)
- Squarespace: `static1.squarespace.com`, `static.squarespace.com`, `images.squarespace-cdn.com`, `sqspcdn.com` and its subdomains

A host matches only exactly or as a subdomain (`assets.sqspcdn.com`), never by containing the name (`sqspcdn.com.example.net`, `sqspcdn.com@10.0.0.1`). Anything else the Wayback Machine does not have is reported as failed.

## Where files go

Each URL is stored at its path under the output directory, and every link in the copy points at that same file, relative to the page that holds it, so the copy opens straight from disk.

- A path ending in `/` is stored as `index.html` inside that directory. A path with no extension gets `.html` (`.css` or `.js` when it was referenced as a stylesheet or script), and a server-side page keeps its extension with `.html` added: `/about` becomes `about.html`, `/index.php` becomes `index.php.html`.
- The fragment (`#section`) never changes the file. The query string does, unless every key in it is a cache-buster (`v`, `ver`, `version`, `rev`, `r`, `t`, `ts`, `_`, `cb`, `cache`, `nocache`, `hash`, `h`, `build`, `timestamp`, `cachebuster`): `style.css?ver=5` is `style.css`, while `/page?id=1` and `/page?id=2` are two pages, stored as `page__q<hash>.html` with a different 10-character hash each. The hash covers the query's other keys and values, sorted, so `?a=1&b=2` and `?b=2&a=1` are one file. The suffix goes before the extension: `/index.php?id=3` becomes `index__q<hash>.php.html`, `/thumb.png?w=200` becomes `thumb__q<hash>.png`.
- A Google Fonts stylesheet is stored as `fonts.googleapis.com/css-<hash>.css`, one file per family set. Files from Google Fonts and the Squarespace CDN are stored under a folder named after their host.
- Names are made valid on Windows, macOS and Linux alike, on every OS, so a copy made on one can be moved to another: the characters `<>:"|?*` and control characters become `_`, trailing dots and spaces are removed, and a name Windows reserves (`CON`, `PRN`, `AUX`, `NUL`, `COM1` to `COM9`, `LPT1` to `LPT9`, with or without an extension) gets `_` after it (`nul.txt` becomes `nul_.txt`).
- A name longer than 200 bytes keeps its first part and its extension, with `~` and 8 characters of a hash of the full name in between, so two long names that share a beginning stay apart.
- `.` and `..` segments are resolved the way a web server does, so no URL can write outside the output directory.
- Names keep their case. Two URLs that differ only in case (`/Photo.jpg`, `/photo.jpg`) are one file on a case-insensitive filesystem (the macOS and Windows defaults), and the one saved last wins.

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
