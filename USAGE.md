# Usage Examples

## Basic Usage

```bash
# Set the Wayback URL
export WAYBACK_URL="https://web.archive.org/web/20250417203037/http://clvreformas.com/"

# Run the downloader
python -m wayback_archive
```

## Advanced Configuration

```bash
# Full configuration example
export WAYBACK_URL="https://web.archive.org/web/20250417203037/http://clvreformas.com/"
export OUTPUT_DIR="./my_output"
export OPTIMIZE_HTML="true"
export OPTIMIZE_IMAGES="false"
export MINIFY_JS="true"
export MINIFY_CSS="true"
export REMOVE_TRACKERS="true"
export REMOVE_ADS="true"
export REMOVE_EXTERNAL_LINKS_KEEP_ANCHORS="true"
export REMOVE_EXTERNAL_LINKS_REMOVE_ANCHORS="false"
export REMOVE_CLICKABLE_CONTACTS="true"
export REMOVE_EXTERNAL_IFRAMES="false"
export MAKE_INTERNAL_LINKS_RELATIVE="true"
export MAKE_NON_WWW="true"
export MAKE_WWW="false"
export KEEP_REDIRECTIONS="false"

python -m wayback_archive
```

## Using .env File

Create a `.env` file in the project root:

```env
WAYBACK_URL=https://web.archive.org/web/20250417203037/http://clvreformas.com/
OPTIMIZE_HTML=true
REMOVE_TRACKERS=true
REMOVE_ADS=true
```

Then run:
```bash
python -m wayback_archive
```

## Command Line (Installed Package)

If installed via pip:
```bash
wayback-archive
```

