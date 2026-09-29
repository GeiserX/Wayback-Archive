# How it works

1. **Initial download** -- Fetches the main page from the Wayback Machine
2. **Link extraction** -- Parses HTML to find all referenced assets (links, images, CSS, JS)
3. **CSS processing** -- Extracts font URLs, background images, and `@import` statements; downloads Google Fonts locally; detects corrupted font files
4. **JS processing** -- Extracts dynamically loaded resources from JavaScript
5. **Data attributes** -- Scans `data-*` attributes for additional asset URLs
6. **Iterative crawling** -- Continues discovering and downloading resources until the queue is empty
7. **Timeframe fallback** -- For 404 responses, searches nearby Wayback Machine timestamps
8. **URL rewriting** -- Converts all URLs to relative paths for offline serving
9. **Preservation** -- Maintains icon groups, button links, and cookie consent functionality

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
    pytest.ini              # Test configuration
  tests/                    # Test suite
  docs/                     # Documentation
  pyproject.toml            # Package metadata and build configuration
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
