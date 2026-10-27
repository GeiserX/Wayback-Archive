# Features

## Core

- **Full website download** -- HTML, CSS, JS, images, fonts, and all linked assets
- **Recursive link discovery** -- Automatically follows links in HTML, CSS, and JS files
- **Smart URL rewriting** -- Converts all links to relative paths for local serving. A reference to another site that the archive does not download (an image on a CDN, an embedded video, a script) gets its original address back instead of the Wayback one, in HTML attributes, `srcset`, CSS `url()` and `@import`. A `#fragment` in a CSS `url()` (SVG sprites, filters, masks) is kept
- **Wayback artifact cleanup** -- Removes the Wayback toolbar, its scripts and its comments. The site's own comments stay, including IE conditional comments and Knockout `<!-- ko -->` bindings, and so does a site script that only mentions `web.archive.org`
- **Timeframe fallback** -- Tries up to three other Wayback Machine timestamps (a day either side and a week earlier) when a resource returns 404
- **Bad capture fallback** -- When a capture is an archived error (403, 5xx) or a Cloudflare challenge page, uses the nearest capture with status 200 instead, found with one query to the Wayback CDX index
- **Real-time progress logging** -- Displays download status and file processing as it happens

## Asset Handling

- **Google Fonts support** -- Downloads Google Fonts CSS and font files locally, fixing CORS issues
- **Font corruption detection** -- Identifies corrupted font files (HTML error pages served as fonts) and removes their entries from `@font-face` rules. A font is matched by its whole path, so `fonts/a.woff` and `other/a.woff` are different fonts
- **Legacy font formats** -- Drops `.eot` and `.svg` entries from an `@font-face` rule when it also lists a modern format (`.woff2`, `.woff`, `.ttf`); a rule with only legacy formats keeps them. Nothing outside `@font-face` changes
- **CDN fallback** -- When the Wayback Machine lacks a file hosted on Google Fonts, `code.jquery.com` or the Squarespace CDN, fetches it from that CDN; a missing `jquery.min.js` is replaced from `code.jquery.com` with the version its URL names (`jquery-1.7.2/`, `?ver=3.6.0`; `1.9` is also tried as `1.9.0`), or 3.7.1 when it names none or `code.jquery.com` does not have that version (a WordPress `?ver=` is often WordPress's own version). Nothing else is fetched live (see [How it works](how-it-works.md#where-requests-go))
- **Data attribute processing** -- Processes `data-*` attributes containing URLs (videos, images, etc.)
- **Text stays text** -- Only attributes that load or link to something are rewritten (`href`, `src`, `poster`, `action`, `formaction`, `data-*` and the like, and `<meta content>` for `og:image`, `twitter:image` and `msapplication-TileImage`). A URL written in `alt`, `title`, an input's `value` or a meta description is left as the site wrote it

## Preservation

- **Icon group preservation** -- Preserves all links in icon groups (social media, contact icons)
- **Button link preservation** -- Maintains styling and functionality of button links
- **Cookie consent preservation** -- Keeps cookie consent popups and functionality intact

## Optimization

- **HTML minification** -- Optional, with `minify-html`. Off by default: it removes spaces that show between inline elements
- **JS/CSS minification** -- Optional JavaScript and CSS minification via `rjsmin` and `rcssmin`
- **Image compression** -- Optional image optimization with Pillow. Colour profiles, EXIF and progressive JPEG encoding are kept; lossless WebP and animated images are left as they are
- **Tracker/ad removal** -- Strips analytics and ads by default, and external iframes when asked
- **Link cleanup** -- Configurable external link removal with anchor preservation options
- **www/non-www normalization** -- Drops `www.` from the archived site's host by default, or adds it with `MAKE_WWW`

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
