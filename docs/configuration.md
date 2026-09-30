# Configuration

All options are set via environment variables. You can also put them in a `.env` file in the directory you run the command from (or one of its parents); variables already set in the environment win.

## Required

| Variable | Description |
|---|---|
| `WAYBACK_URL` | The Wayback Machine URL to download |

## Output

| Variable | Default | Description |
|---|---|---|
| `OUTPUT_DIR` | `./output` | Output directory for downloaded files |

## Optimization

| Variable | Default | Description |
|---|---|---|
| `OPTIMIZE_HTML` | `true` | Minify HTML |
| `OPTIMIZE_IMAGES` | `false` | Compress images |
| `MINIFY_JS` | `false` | Minify JavaScript |
| `MINIFY_CSS` | `false` | Minify CSS |

## Content Removal

| Variable | Default | Description |
|---|---|---|
| `REMOVE_TRACKERS` | `true` | Remove analytics and trackers |
| `REMOVE_ADS` | `true` | Remove advertisements |
| `REMOVE_CLICKABLE_CONTACTS` | `true` | Remove `tel:` and `mailto:` links |
| `REMOVE_EXTERNAL_IFRAMES` | `false` | Remove external iframes |

## Link Handling

| Variable | Default | Description |
|---|---|---|
| `REMOVE_EXTERNAL_LINKS_KEEP_ANCHORS` | `true` | Remove external links, keep what they wrap (text, images, markup) |
| `REMOVE_EXTERNAL_LINKS_REMOVE_ANCHORS` | `false` | Remove external links and anchor elements |
| `MAKE_INTERNAL_LINKS_RELATIVE` | `true` | Convert internal links to relative paths |

## Domain

| Variable | Default | Description |
|---|---|---|
| `MAKE_NON_WWW` | `true` | Convert www to non-www |
| `MAKE_WWW` | `false` | Convert non-www to www; when `true`, `MAKE_NON_WWW` is ignored |

## Testing

| Variable | Default | Description |
|---|---|---|
| `MAX_FILES` | unlimited | Stop after trying this many files, failed ones included. Must be a positive whole number |

See [Usage](usage.md) for examples per shell.
