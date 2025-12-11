# Wayback-Archive

A comprehensive Python tool for downloading and archiving websites from the Wayback Machine with extensive customization options.

## Features

- Full website download (HTML, CSS, JS, images, and all assets)
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

```bash
# Set environment variables
export WAYBACK_URL="https://web.archive.org/web/20250417203037/http://clvreformas.com/"
export OPTIMIZE_HTML="true"
export REMOVE_TRACKERS="true"

# Run the tool
python -m wayback_archive
```

## Development

Run tests:
```bash
pytest
```

## License

MIT


