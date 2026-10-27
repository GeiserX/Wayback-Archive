# Configuration

Every option can be given three ways: as a command-line flag, as an environment variable, or in a `.env` file in the directory you run the command from. When one option is set in more than one place, the flag wins over the environment variable, the environment variable wins over `.env`, and `.env` wins over the default. Only the `.env` of the current directory is read, never one in a parent directory.

```bash
wayback-archive "https://web.archive.org/web/20051231235226/http://www.python.org/" -o ./python --no-remove-clickable-contacts
```

`wayback-archive --help` lists every flag with its environment variable and default.

Each on/off option has a pair of flags: `--minify-css` turns it on and `--no-minify-css` turns it off. As an environment variable it takes `true`, `false`, `1`, `0`, `yes`, `no`, `on` or `off` (any case); an empty one takes the default. Any other value, such as a typo like `ture`, stops the command with exit status 2 and a message naming the variable, before anything is downloaded.

## Required

| Flag | Environment variable | Default | What it does |
|---|---|---|---|
| `URL` (first argument) | `WAYBACK_URL` | none | The Wayback Machine URL to download |

## Output

| Flag | Environment variable | Default | What it does |
|---|---|---|---|
| `-o`, `--output-dir` | `OUTPUT_DIR` | `./output` | Output directory for downloaded files. An empty value means the default |

## Optimization

| Flag | Environment variable | Default | What it does |
|---|---|---|---|
| `--optimize-html` | `OPTIMIZE_HTML` | `false` | Minify HTML with `minify-html`. Off by default because it changes how pages render: it drops the space between inline elements such as `<span>a</span> <span>b</span>` and collapses text styled `white-space: pre`. It also removes HTML comments |
| `--optimize-images` | `OPTIMIZE_IMAGES` | `false` | Recompress still images in their own format; animated images are left as they are |
| `--minify-js` | `MINIFY_JS` | `false` | Minify JavaScript |
| `--minify-css` | `MINIFY_CSS` | `false` | Minify CSS with `rcssmin`, which keeps `calc()` and `@supports` valid |

## Content Removal

| Flag | Environment variable | Default | What it does |
|---|---|---|---|
| `--remove-trackers` | `REMOVE_TRACKERS` | `true` | Remove analytics and trackers |
| `--remove-ads` | `REMOVE_ADS` | `true` | Remove advertisements |
| `--remove-clickable-contacts` | `REMOVE_CLICKABLE_CONTACTS` | `true` | Point `tel:` and `mailto:` links at `#`, keeping their text. Links in floating buttons and icon groups are left alone |
| `--remove-external-iframes` | `REMOVE_EXTERNAL_IFRAMES` | `false` | Remove external iframes |

## Link Handling

| Flag | Environment variable | Default | What it does |
|---|---|---|---|
| `--remove-external-links-keep-anchors` | `REMOVE_EXTERNAL_LINKS_KEEP_ANCHORS` | `true` | Remove external links, keep what they wrap (text, images, markup) |
| `--remove-external-links-remove-anchors` | `REMOVE_EXTERNAL_LINKS_REMOVE_ANCHORS` | `false` | Delete external links together with what they wrap. Overrides `REMOVE_EXTERNAL_LINKS_KEEP_ANCHORS`, and deletes contact links instead of pointing them at `#` |
| `--make-internal-links-relative` | `MAKE_INTERNAL_LINKS_RELATIVE` | `true` | Convert internal links to relative paths. When `false` they keep pointing at the original site's URLs instead of the saved files |

With both external link options `false`, external links stay and point at the live site. Button links (`btn`, `sppb-btn` classes) and links in icon groups are always kept.

## Domain

| Flag | Environment variable | Default | What it does |
|---|---|---|---|
| `--make-non-www` | `MAKE_NON_WWW` | `true` | Drop `www.` from the archived site's host |
| `--make-www` | `MAKE_WWW` | `false` | Add `www.` to the archived site's host; when `true`, the `MAKE_NON_WWW` default is ignored |

Both apply to the archived site's own host only; other hosts such as `www.gstatic.com` keep their name. Setting both to `true` explicitly is an error.

## Pace and testing

| Flag | Environment variable | Default | What it does |
|---|---|---|---|
| `--request-delay` | `REQUEST_DELAY` | `0` | Seconds to wait between requests to the Wayback Machine. Any number 0 or more, fractions included |
| `--max-files` | `MAX_FILES` | unlimited | Stop after trying this many files, failed ones included. Must be a positive whole number |

## From Python

The same options are keyword arguments of `wayback_archive.download()`, named like the flags with underscores; see [Usage](usage.md#from-python).

See [Usage](usage.md) for examples per shell.
