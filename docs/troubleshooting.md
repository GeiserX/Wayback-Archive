# Troubleshooting

## Port Already in Use

```bash
python3 -m http.server 8080  # Use a different port
```

## Font Loading Issues

- **Google Fonts**: Downloaded automatically to avoid CORS issues
- **Corrupted fonts**: Detected and removed from CSS automatically
- **Missing fonts**: Some fonts may not exist in the Wayback Machine archive

See [Font Loading Research Notes](https://github.com/GeiserX/Wayback-Archive/blob/main/docs/FONT_LOADING.md) for details.

## Missing Links or Icons

- Icon groups (social media, contacts) are preserved automatically
- Button links with `sppb-btn` or `btn` classes are preserved
- Set `REMOVE_CLICKABLE_CONTACTS=false` to keep `tel:` and `mailto:` links

## jQuery or Libraries Not Loading

If the Wayback Machine does not have a site's `jquery.min.js`, the tool replaces it with jQuery 3.7.1 from `code.jquery.com`. Other missing libraries are only fetched live when they are hosted on Google Fonts, `code.jquery.com` or the Squarespace CDN; anything else is reported as failed (see [How it works](how-it-works.md#where-requests-go)).
