# Configuration

All options are set via environment variables. You can also put them in a `.env` file in the directory you run the command from (or one of its parents); variables already set in the environment win.

A boolean is true when set to `true`, `1`, `yes` or `on` (any case); any other value is false, and an unset or empty one takes the default.

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
| `OPTIMIZE_IMAGES` | `false` | Recompress still images in their own format; animated images are left as they are |
| `MINIFY_JS` | `false` | Minify JavaScript |
| `MINIFY_CSS` | `false` | Minify CSS |

## Content Removal

| Variable | Default | Description |
|---|---|---|
| `REMOVE_TRACKERS` | `true` | Remove analytics and trackers |
| `REMOVE_ADS` | `true` | Remove advertisements |
| `REMOVE_CLICKABLE_CONTACTS` | `true` | Point `tel:` and `mailto:` links at `#`, keeping their text. Links in floating buttons and icon groups are left alone |
| `REMOVE_EXTERNAL_IFRAMES` | `false` | Remove external iframes |

## Link Handling

| Variable | Default | Description |
|---|---|---|
| `REMOVE_EXTERNAL_LINKS_KEEP_ANCHORS` | `true` | Remove external links, keep what they wrap (text, images, markup) |
| `REMOVE_EXTERNAL_LINKS_REMOVE_ANCHORS` | `false` | Delete external links together with what they wrap. Overrides `REMOVE_EXTERNAL_LINKS_KEEP_ANCHORS`, and deletes contact links instead of pointing them at `#` |
| `MAKE_INTERNAL_LINKS_RELATIVE` | `true` | Convert internal links to relative paths. When `false` they keep pointing at the original site's URLs instead of the saved files |

With both external link options `false`, external links stay and point at the live site. Button links (`btn`, `sppb-btn` classes) and links in icon groups are always kept.

## Domain

| Variable | Default | Description |
|---|---|---|
| `MAKE_NON_WWW` | `true` | Drop `www.` from the archived site's host |
| `MAKE_WWW` | `false` | Add `www.` to the archived site's host; when `true`, `MAKE_NON_WWW` is ignored |

Both apply to the archived site's own host only; other hosts such as `www.gstatic.com` keep their name.

## Testing

| Variable | Default | Description |
|---|---|---|
| `MAX_FILES` | unlimited | Stop after trying this many files, failed ones included. Must be a positive whole number |

See [Usage](usage.md) for examples per shell.
