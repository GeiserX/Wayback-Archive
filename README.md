<p align="center">
  <img src="https://raw.githubusercontent.com/GeiserX/Wayback-Archive/main/docs/images/banner.svg" alt="Wayback-Archive banner" width="900"/>
</p>

<p align="center">
  <strong>Download complete websites from the Wayback Machine for offline viewing.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/wayback-archive/"><img src="https://img.shields.io/pypi/v/wayback-archive?style=flat-square" alt="PyPI"></a>
  <a href="https://github.com/GeiserX/Wayback-Archive/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/GeiserX/Wayback-Archive/ci.yml?style=flat-square&logo=github&label=build" alt="Build"></a>
  <a href="https://github.com/GeiserX/Wayback-Archive/releases"><img src="https://img.shields.io/github/v/release/GeiserX/Wayback-Archive?style=flat-square" alt="Release"></a>
  <a href="https://github.com/GeiserX/Wayback-Archive/blob/main/LICENSE"><img src="https://img.shields.io/github/license/GeiserX/Wayback-Archive?style=flat-square" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.8%2B-blue?style=flat-square&logo=python&logoColor=white" alt="Python 3.8+">
  <a href="https://github.com/GeiserX/Wayback-Archive/stargazers"><img src="https://img.shields.io/github/stars/GeiserX/Wayback-Archive?style=flat-square" alt="GitHub Stars"></a>
</p>

---

Wayback-Archive is a Python tool that downloads archived websites from the [Wayback Machine](https://web.archive.org/) and reconstructs them for fully functional offline viewing. It preserves all assets -- HTML, CSS, JavaScript, images, and fonts -- rewrites URLs to relative paths, and cleans up Wayback Machine artifacts so the result looks like the original site.

## Quick Start

```bash
# Install
git clone https://github.com/GeiserX/Wayback-Archive.git
cd Wayback-Archive
pip install -r config/requirements.txt

# Run
export WAYBACK_URL="https://web.archive.org/web/20250417203037/http://example.com/"
python3 -m wayback_archive.cli

# Preview
cd output && python3 -m http.server 8000
# Open http://localhost:8000
```

## Features

### Core

- **Full website download** -- HTML, CSS, JS, images, fonts, and all linked assets
- **Recursive link discovery** -- Automatically follows links in HTML, CSS, and JS files
- **Smart URL rewriting** -- Converts all links to relative paths for local serving
- **Timeframe fallback** -- Searches nearby Wayback Machine timestamps when a resource returns 404
- **Real-time progress logging** -- Displays download status and file processing as it happens

### Asset Handling

- **Google Fonts support** -- Downloads Google Fonts CSS and font files locally, fixing CORS issues
- **Font corruption detection** -- Identifies and removes corrupted font files (HTML error pages served as fonts)
- **CDN fallback** -- Automatic fallback to CDN for critical libraries (e.g., jQuery) when Wayback Machine fails
- **Data attribute processing** -- Processes `data-*` attributes containing URLs (videos, images, etc.)

### Preservation

- **Icon group preservation** -- Preserves all links in icon groups (social media, contact icons)
- **Button link preservation** -- Maintains styling and functionality of button links
- **Cookie consent preservation** -- Keeps cookie consent popups and functionality intact

### Optimization

- **HTML minification** -- Uses `minify-html` (Python 3.14+ compatible)
- **JS/CSS minification** -- Optional JavaScript and CSS minification via `rjsmin` and `cssmin`
- **Image compression** -- Optional image optimization with Pillow
- **Tracker/ad removal** -- Strips analytics, ads, and external iframes
- **Link cleanup** -- Configurable external link removal with anchor preservation options
- **www/non-www normalization** -- Normalize domain variations automatically

## Why Wayback-Archive?

| Capability | Wayback-Archive | wget | httrack |
|---|:---:|:---:|:---:|
| Wayback Machine URL rewriting | Yes | No | No |
| Wayback artifact cleanup | Yes | No | No |
| Timeframe fallback for 404s | Yes | No | No |
| Google Fonts localization | Yes | No | No |
| Font corruption detection | Yes | No | No |
| CDN fallback | Yes | No | No |
| HTML/CSS/JS minification | Yes | No | No |
| Tracker and ad removal | Yes | No | No |
| `data-*` attribute processing | Yes | No | No |

General-purpose tools like `wget --mirror` or `httrack` can download live websites, but they do not understand Wayback Machine URL structures, cannot clean up archive artifacts, and lack the specialized asset recovery that Wayback-Archive provides.

## Installation

### Prerequisites

- Python 3.8 or higher
- pip

### From Source

```bash
git clone https://github.com/GeiserX/Wayback-Archive.git
cd Wayback-Archive

# Optional: create a virtual environment
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

pip install -r config/requirements.txt
```

### As a Package

```bash
cd Wayback-Archive
pip install -e .
wayback-archive  # Available as a CLI command after installation
```

## Configuration

All options are set via environment variables. You can also use a `.env` file.

### Required

| Variable | Description |
|---|---|
| `WAYBACK_URL` | The Wayback Machine URL to download |

### Output

| Variable | Default | Description |
|---|---|---|
| `OUTPUT_DIR` | `./output` | Output directory for downloaded files |

### Optimization

| Variable | Default | Description |
|---|---|---|
| `OPTIMIZE_HTML` | `true` | Minify HTML |
| `OPTIMIZE_IMAGES` | `false` | Compress images |
| `MINIFY_JS` | `false` | Minify JavaScript |
| `MINIFY_CSS` | `false` | Minify CSS |

### Content Removal

| Variable | Default | Description |
|---|---|---|
| `REMOVE_TRACKERS` | `true` | Remove analytics and trackers |
| `REMOVE_ADS` | `true` | Remove advertisements |
| `REMOVE_CLICKABLE_CONTACTS` | `true` | Remove `tel:` and `mailto:` links |
| `REMOVE_EXTERNAL_IFRAMES` | `false` | Remove external iframes |

### Link Handling

| Variable | Default | Description |
|---|---|---|
| `REMOVE_EXTERNAL_LINKS_KEEP_ANCHORS` | `true` | Remove external links, keep anchor text |
| `REMOVE_EXTERNAL_LINKS_REMOVE_ANCHORS` | `false` | Remove external links and anchor elements |
| `MAKE_INTERNAL_LINKS_RELATIVE` | `true` | Convert internal links to relative paths |

### Domain

| Variable | Default | Description |
|---|---|---|
| `MAKE_NON_WWW` | `true` | Convert www to non-www |
| `MAKE_WWW` | `false` | Convert non-www to www |
| `KEEP_REDIRECTIONS` | `false` | Keep redirect pages |

### Testing

| Variable | Default | Description |
|---|---|---|
| `MAX_FILES` | unlimited | Limit number of files to download |

## Usage

### macOS / Linux

```bash
export WAYBACK_URL="https://web.archive.org/web/20250417203037/http://example.com/"
export OUTPUT_DIR="./my_website"
export REMOVE_CLICKABLE_CONTACTS="false"  # Keep email/phone links

python3 -m wayback_archive.cli
```

### Windows (PowerShell)

```powershell
$env:WAYBACK_URL = "https://web.archive.org/web/20250417203037/http://example.com/"
$env:OUTPUT_DIR = ".\my_website"
$env:REMOVE_CLICKABLE_CONTACTS = "false"

python -m wayback_archive.cli
```

### Windows (CMD)

```cmd
set WAYBACK_URL=https://web.archive.org/web/20250417203037/http://example.com/
set OUTPUT_DIR=.\my_website
set REMOVE_CLICKABLE_CONTACTS=false

python -m wayback_archive.cli
```

### Quick Test

Download a limited number of files to verify everything works:

```bash
export WAYBACK_URL="https://web.archive.org/web/20250417203037/http://example.com/"
export MAX_FILES=5
python3 -m wayback_archive.cli
```

## How It Works

1. **Initial download** -- Fetches the main page from the Wayback Machine
2. **Link extraction** -- Parses HTML to find all referenced assets (links, images, CSS, JS)
3. **CSS processing** -- Extracts font URLs, background images, and `@import` statements; downloads Google Fonts locally; detects corrupted font files
4. **JS processing** -- Extracts dynamically loaded resources from JavaScript
5. **Data attributes** -- Scans `data-*` attributes for additional asset URLs
6. **Iterative crawling** -- Continues discovering and downloading resources until the queue is empty
7. **Timeframe fallback** -- For 404 responses, searches nearby Wayback Machine timestamps
8. **URL rewriting** -- Converts all URLs to relative paths for offline serving
9. **Preservation** -- Maintains icon groups, button links, and cookie consent functionality

## Project Structure

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
    setup.py                # Package setup
    pytest.ini              # Test configuration
  tests/                    # Test suite
  docs/                     # Documentation
  LICENSE                   # GPL-3.0
  README.md
```

## Testing

```bash
pip install -r config/requirements-dev.txt

# Run tests
pytest

# Run tests with coverage
pytest --cov=wayback_archive
```

## Troubleshooting

### Port Already in Use

```bash
python3 -m http.server 8080  # Use a different port
```

### Font Loading Issues

- **Google Fonts**: Downloaded automatically to avoid CORS issues
- **Corrupted fonts**: Detected and removed from CSS automatically
- **Missing fonts**: Some fonts may not exist in the Wayback Machine archive

See [Font Loading Research Notes](docs/FONT_LOADING.md) for details.

### Missing Links or Icons

- Icon groups (social media, contacts) are preserved automatically
- Button links with `sppb-btn` or `btn` classes are preserved
- Set `REMOVE_CLICKABLE_CONTACTS=false` to keep `tel:` and `mailto:` links

### jQuery or Libraries Not Loading

The tool includes automatic CDN fallback for critical libraries. If a file fails to download from the Wayback Machine, it will attempt to fetch it from a CDN.

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

## Contributing

Contributions are welcome. Please feel free to submit a Pull Request.

## Related Web Archiving Tools

- [Way-CMS](https://github.com/GeiserX/Way-CMS) — Simple web CMS for editing archived HTML/CSS files
- [Website-Diff](https://github.com/GeiserX/Website-Diff) — Web page comparison with Wayback Machine support
- [web-mirror](https://github.com/GeiserX/web-mirror) — Mirror any webpage for offline access
- [media-download](https://github.com/GeiserX/media-download) — Download all media files from any web page

## License

This project is licensed under the [GNU General Public License v3.0](LICENSE) (GPL-3.0).
