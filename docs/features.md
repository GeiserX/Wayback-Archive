# Features

## Core

- **Full website download** -- HTML, CSS, JS, images, fonts, and all linked assets
- **Recursive link discovery** -- Automatically follows links in HTML, CSS, and JS files
- **Smart URL rewriting** -- Converts all links to relative paths for local serving
- **Timeframe fallback** -- Tries up to three other Wayback Machine timestamps (a day either side and a week earlier) when a resource returns 404
- **Real-time progress logging** -- Displays download status and file processing as it happens

## Asset Handling

- **Google Fonts support** -- Downloads Google Fonts CSS and font files locally, fixing CORS issues
- **Font corruption detection** -- Identifies and removes corrupted font files (HTML error pages served as fonts)
- **CDN fallback** -- When the Wayback Machine lacks a file hosted on Google Fonts, `code.jquery.com` or the Squarespace CDN, fetches it from that CDN; a missing `jquery.min.js` is replaced with jQuery 3.7.1 from `code.jquery.com`. Nothing else is fetched live (see [How it works](how-it-works.md#where-requests-go))
- **Data attribute processing** -- Processes `data-*` attributes containing URLs (videos, images, etc.)

## Preservation

- **Icon group preservation** -- Preserves all links in icon groups (social media, contact icons)
- **Button link preservation** -- Maintains styling and functionality of button links
- **Cookie consent preservation** -- Keeps cookie consent popups and functionality intact

## Optimization

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
