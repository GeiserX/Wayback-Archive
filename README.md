# Wayback-Archive

A comprehensive Python tool for downloading and archiving websites from the Wayback Machine. Preserves complete functionality including fonts, CSS, JavaScript, images, and interactive elements for offline viewing.

## Features

### Core Functionality
- **Full website download**: HTML, CSS, JS, images, fonts, and all assets
- **Recursive link discovery**: Automatically follows links in HTML, CSS, and JS files
- **Timeframe fallback**: Searches nearby timestamps if a file returns 404
- **Smart URL rewriting**: Converts all links to relative paths for local serving
- **Real-time progress logging**: See download status and file processing in real-time

### Advanced Features
- **Google Fonts support**: Downloads and serves Google Fonts locally (fixes CORS issues)
- **Font corruption detection**: Automatically detects and removes corrupted font files (HTML error pages)
- **Icon group preservation**: Preserves all links in icon groups (social media, contact icons)
- **Button link preservation**: Maintains styling and functionality of button links
- **Cookie consent preservation**: Keeps cookie consent popups and functionality
- **CDN fallback**: Automatic fallback to CDN for critical files (e.g., jQuery) if Wayback Machine fails
- **Data attribute processing**: Processes `data-*` attributes containing URLs (videos, images, etc.)

### Optimization Options
- **HTML optimization**: Minification using `minify-html` (Python 3.14+ compatible)
- **Image optimization**: Optional image compression
- **JS/CSS minification**: Optional JavaScript and CSS minification
- **Content removal**: Remove trackers, ads, and external iframes
- **Link handling**: Configurable external link removal/keeping
- **Contact link handling**: Option to preserve or remove clickable contacts
- **www/non-www conversion**: Normalize domain variations

## Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Setup

```bash
# Clone the repository
git clone https://github.com/GeiserX/Wayback-Archive.git
cd Wayback-Archive

# Create virtual environment (recommended)
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r config/requirements.txt
```

## Configuration

All options are configured via environment variables. You can set them directly or use a `.env` file.

### Required Variables

- `WAYBACK_URL`: The Wayback Machine URL to download (required)
  ```bash
  export WAYBACK_URL="https://web.archive.org/web/20250417203037/http://clvreformas.com/"
  ```

### Output Configuration

- `OUTPUT_DIR`: Output directory for downloaded files (default: `./output`)
  ```bash
  export OUTPUT_DIR="./my_website"
  ```

### Optimization Options

- `OPTIMIZE_HTML`: Optimize HTML code (default: `true`)
- `OPTIMIZE_IMAGES`: Optimize images (default: `false`)
- `MINIFY_JS`: Minify JavaScript (default: `false`)
- `MINIFY_CSS`: Minify CSS (default: `false`)

### Content Removal Options

- `REMOVE_TRACKERS`: Remove trackers and analytics (default: `true`)
- `REMOVE_ADS`: Remove ads (default: `true`)
- `REMOVE_CLICKABLE_CONTACTS`: Remove clickable contacts (default: `true`)
- `REMOVE_EXTERNAL_IFRAMES`: Remove external iframes (default: `false`)

### Link Handling Options

- `REMOVE_EXTERNAL_LINKS_KEEP_ANCHORS`: Remove external links, saving anchors (default: `true`)
- `REMOVE_EXTERNAL_LINKS_REMOVE_ANCHORS`: Remove external links together with anchors (default: `false`)
- `MAKE_INTERNAL_LINKS_RELATIVE`: Make internal links relative (default: `true`)

### Domain Options

- `MAKE_NON_WWW`: Convert www to non-www (default: `true`)
- `MAKE_WWW`: Convert non-www to www (default: `false`)
- `KEEP_REDIRECTIONS`: Keep redirections (default: `false`)

### Testing Options

- `MAX_FILES`: Limit number of files to download (for testing, default: unlimited)
  ```bash
  export MAX_FILES=10  # Download only 10 files for quick testing
  ```

## Usage

### macOS / Linux

```bash
# Set environment variables
export WAYBACK_URL="https://web.archive.org/web/20250417203037/http://clvreformas.com/"
export OUTPUT_DIR="./my_website"
export REMOVE_CLICKABLE_CONTACTS="false"  # Keep email/phone links

# Run the tool
python3 -m wayback_archive.cli

# Test with Python's built-in server
cd my_website
python3 -m http.server 8000
# Open http://localhost:8000 in your browser
```

### Windows (PowerShell)

```powershell
# Set environment variables
$env:WAYBACK_URL = "https://web.archive.org/web/20250417203037/http://clvreformas.com/"
$env:OUTPUT_DIR = ".\my_website"
$env:REMOVE_CLICKABLE_CONTACTS = "false"

# Run the tool
python -m wayback_archive.cli

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
python -m wayback_archive.cli

REM Test with Python's built-in server
cd my_website
python -m http.server 8000
REM Open http://localhost:8000 in your browser
```

### Quick Testing

For quick testing with a limited number of files:

```bash
export MAX_FILES=5  # Download only 5 files
export WAYBACK_URL="https://web.archive.org/web/20250417203037/http://clvreformas.com/"
python3 -m wayback_archive.cli
```

## How It Works

1. **Initial Download**: Downloads the main page from the Wayback Machine
2. **Link Extraction**: Parses HTML to find all links, images, CSS, and JavaScript
3. **CSS Processing**: Extracts font URLs, background images, and `@import` statements
   - Downloads Google Fonts CSS files and font files locally
   - Detects and removes corrupted font files (HTML error pages)
4. **JS Processing**: Extracts dynamically loaded resources
5. **Data Attribute Processing**: Processes `data-*` attributes containing URLs (videos, images, etc.)
6. **Iterative Crawling**: Continues downloading new resources until all are fetched
7. **Timeframe Fallback**: If a resource returns 404, searches nearby timestamps
8. **URL Rewriting**: Converts all links to relative paths for local serving
9. **Link Preservation**: Preserves icon groups, button links, and cookie consent functionality

## Project Structure

```
Wayback-Archive/
├── wayback_archive/      # Main package
│   ├── __init__.py
│   ├── cli.py            # Command-line interface
│   ├── config.py         # Configuration management
│   └── downloader.py     # Core downloader logic
├── config/               # Configuration files
│   ├── requirements.txt  # Python dependencies
│   ├── requirements-dev.txt  # Development dependencies
│   ├── setup.py         # Package setup
│   └── pytest.ini       # Test configuration
├── docs/                 # Documentation
│   └── FONT_LOADING.md   # Font loading troubleshooting
├── tests/                # Test suite
├── LICENSE               # GPL v3 license
└── README.md             # This file
```

## Testing

Run the test suite:

```bash
# Install development dependencies
pip install -r config/requirements-dev.txt

# Run tests
pytest
```

## Troubleshooting

### Port Already in Use

If the Python HTTP server fails to start because port 8000 is in use, use a different port:

```bash
python3 -m http.server 8080
```

### Font Loading Issues

If fonts don't load correctly in the local copy:

- **Google Fonts**: The tool automatically downloads Google Fonts CSS and font files locally to avoid CORS issues
- **Corrupted Fonts**: The tool automatically detects and removes corrupted font files (HTML error pages) from CSS
- **Missing Fonts**: Some font files may not be available in the Wayback Machine archive

For more details, see the [Font Loading Research Notes](docs/FONT_LOADING.md) document.

### Missing Links or Icons

- **Icon Groups**: Links in icon groups (social media, contact icons) are automatically preserved
- **Button Links**: Button links with `sppb-btn` or `btn` classes are preserved
- **Contact Links**: Set `REMOVE_CLICKABLE_CONTACTS=false` to preserve `tel:` and `mailto:` links

### jQuery or Other Libraries Not Loading

The tool includes automatic CDN fallback for critical files like jQuery. If a file fails to download from Wayback Machine, it will attempt to download from a CDN.

## Recursive Link Discovery

The downloader uses an iterative crawling approach:

1. **Initial Download**: Downloads the main page from the Wayback Machine
2. **Link Extraction**: Parses HTML to find all links, images, CSS, and JavaScript
3. **CSS Processing**: Extracts font URLs, background images, and `@import` statements from CSS files
   - Processes Google Fonts CSS files and downloads font files
4. **JS Processing**: Extracts dynamically loaded resources from JavaScript files
5. **Data Attributes**: Processes `data-*` attributes containing URLs
6. **Queue Management**: New links are added to a queue and processed until empty
7. **Deduplication**: URLs are normalized (removes query strings, fragments) to prevent downloading the same file twice
8. **Timeframe Fallback**: If a resource returns 404, searches nearby timestamps

The process continues until all internal links are downloaded. External resources like Google Fonts are downloaded and served locally to avoid CORS issues.

## Development

### Running Tests

```bash
# Install development dependencies
pip install -r config/requirements-dev.txt

# Run tests
pytest

# Run tests with coverage
pytest --cov=wayback_archive
```

### Code Structure

- `wayback_archive/cli.py`: Command-line interface entry point
- `wayback_archive/config.py`: Configuration management with environment variable support
- `wayback_archive/downloader.py`: Core downloader with recursive crawling, URL rewriting, and optimization

## License

This project is licensed under the GNU General Public License v3.0 (GPL-3.0).
See the [LICENSE](LICENSE) file for details.

**Note**: This software is NOT for commercial use.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

- Built for preserving websites from the Wayback Machine
- Compatible with Python 3.8+
- Uses `minify-html` for Python 3.14+ compatibility
