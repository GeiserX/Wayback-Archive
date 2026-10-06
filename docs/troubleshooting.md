# Troubleshooting

## pip refuses to install (externally-managed-environment)

Homebrew Python and the system Python on Debian and Ubuntu refuse a bare `pip install` with `error: externally-managed-environment`. Install the command with pipx, which gives it its own environment:

```bash
pipx install wayback-archive
```

Or create a virtual environment and install into it:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install wayback-archive
```

## pip cannot install it (Python 3.9)

Wayback-Archive needs Python 3.10 or newer. On Python 3.9, pip skips 1.5.0 and finds no older release it can use: it stops with `ERROR: ResolutionImpossible` while it can still try 1.4.2 to 1.4.6 (their `requests` does not install on 3.9), and with `ERROR: No matching distribution found for wayback-archive` once those are yanked. The `python3` that ships with macOS is 3.9. Install Python 3.10 or newer (for example `brew install python`) and install again with pipx or in a new virtual environment.

## Port already in use

```bash
python3 -m http.server 8080  # Use a different port
```

## Font loading issues

- **Google Fonts**: Downloaded automatically to avoid CORS issues
- **Corrupted fonts**: Detected and removed from CSS automatically
- **Missing fonts**: Some fonts may not exist in the Wayback Machine archive

See [Font Loading Research Notes](https://github.com/GeiserX/Wayback-Archive/blob/main/docs/FONT_LOADING.md) for details.

## Missing links or icons

- Icon groups (social media, contacts) are preserved automatically
- Button links with `sppb-btn` or `btn` classes are preserved
- Set `REMOVE_CLICKABLE_CONTACTS=false` to keep `tel:` and `mailto:` links

## jQuery or libraries not loading

If the Wayback Machine does not have a site's `jquery.min.js`, the tool replaces it from `code.jquery.com` with the version the URL names (for example `jquery-1.7.2/jquery.min.js` or `jquery.min.js?ver=3.6.0`), or with jQuery 3.7.1 when the URL names no version or `code.jquery.com` does not have that version. Other missing libraries are only fetched live when they are hosted on Google Fonts, `code.jquery.com` or the Squarespace CDN; anything else is reported as failed (see [How it works](how-it-works.md#where-requests-go)).
