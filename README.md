# Wayback-Archive

A comprehensive Python tool for downloading and archiving websites from the Wayback Machine with extensive customization options.

## Features

- Full website download (HTML, CSS, JS, images, fonts, and all assets)
- Iterative link discovery (follows links in HTML, CSS, and JS files)
- Timeframe fallback (searches nearby timestamps if file not found)
- HTML optimization (minification)
- Image optimization (optional)
- JS/CSS minification (optional)
- Remove trackers and analytics
- Remove ads
- Handle external links with configurable options
- Remove clickable contacts
- Remove external iframes
- Convert links to relative/absolute paths
- Handle www/non-www conversion
- Option to keep or remove redirections

## Installation

```bash
# Create virtual environment (recommended)
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

All options are configured via environment variables:

- `WAYBACK_URL`: The Wayback Machine URL to download (required)
  Example: `https://web.archive.org/web/20250417203037/http://clvreformas.com/`

- `OPTIMIZE_HTML`: Optimize HTML code (default: `true`)
- `OPTIMIZE_IMAGES`: Optimize images (default: `false`)
- `MINIFY_JS`: Minify JavaScript (default: `false`)
- `MINIFY_CSS`: Minify CSS (default: `false`)
- `REMOVE_TRACKERS`: Remove trackers and analytics (default: `true`)
- `REMOVE_ADS`: Remove ads (default: `true`)
- `REMOVE_EXTERNAL_LINKS_KEEP_ANCHORS`: Remove external links, saving anchors (default: `true`)
- `REMOVE_EXTERNAL_LINKS_REMOVE_ANCHORS`: Remove external links together with anchors (default: `false`)
- `REMOVE_CLICKABLE_CONTACTS`: Remove clickable contacts (default: `true`)
- `REMOVE_EXTERNAL_IFRAMES`: Remove external iframes (default: `false`)
- `MAKE_INTERNAL_LINKS_RELATIVE`: Make internal links relative (default: `true`)
- `MAKE_NON_WWW`: Make a non-www website (default: `true`)
- `MAKE_WWW`: Make a website with www (default: `false`)
- `KEEP_REDIRECTIONS`: Keep redirections (default: `false`)
- `OUTPUT_DIR`: Output directory for downloaded files (default: `./output`)

## Usage

### macOS / Linux

```bash
# Set environment variables
export WAYBACK_URL="https://web.archive.org/web/20250417203037/http://clvreformas.com/"
export OUTPUT_DIR="./my_website"
export REMOVE_CLICKABLE_CONTACTS="false"  # Keep email/phone links

# Run the tool
python -m wayback_archive

# Test with Python's built-in server
cd my_website
python -m http.server 8000
# Open http://localhost:8000 in your browser
```

### Windows (PowerShell)

```powershell
# Set environment variables
$env:WAYBACK_URL = "https://web.archive.org/web/20250417203037/http://clvreformas.com/"
$env:OUTPUT_DIR = ".\my_website"
$env:REMOVE_CLICKABLE_CONTACTS = "false"

# Run the tool
python -m wayback_archive

# Test with Python's built-in server
cd my_website
python -m http.server 8000
# Open http://localhost:8000 in your browser
```

### Windows (CMD)

```cmd
REM Set environment variables
set WAYBACK_URL=https://web.archive.org/web/20250417203037/http://clvreformas.com/
set OUTPUT_DIR=.\my_website
set REMOVE_CLICKABLE_CONTACTS=false

REM Run the tool
python -m wayback_archive

REM Test with Python's built-in server
cd my_website
python -m http.server 8000
REM Open http://localhost:8000 in your browser
```

## How It Works

1. **Initial Download**: Downloads the main page from the Wayback Machine
2. **Link Extraction**: Parses HTML to find all links, images, CSS, and JavaScript
3. **CSS Processing**: Extracts font URLs, background images, and @import statements
4. **JS Processing**: Extracts dynamically loaded resources
5. **Iterative Crawling**: Continues downloading new resources until all are fetched
6. **Timeframe Fallback**: If a resource returns 404, searches nearby timestamps
7. **URL Rewriting**: Converts all links to relative paths for local serving

## Development

Run tests:
```bash
pytest
```

## License

This project is licensed under the GNU General Public License v3.0 (GPL-3.0).
See the [LICENSE](LICENSE) file for details.

**Note**: This software is NOT for commercial use.
