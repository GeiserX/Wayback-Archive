# URL Deduplication Mechanism

## How It Works

The Wayback-Archive downloader ensures each file is downloaded only once through a multi-layer deduplication system:

### 1. **Visited URLs Tracking**
- A `visited_urls` set in the `Config` class tracks all URLs that have been processed
- This set persists across the entire download session

### 2. **URL Normalization**
Before checking if a URL has been visited, all URLs are normalized through `_normalize_url()`:

- **Extracts original URLs** from Wayback Machine paths (removes `/web/TIMESTAMP/` prefixes)
- **Converts relative URLs** to absolute URLs using the current page's base URL
- **Handles protocol-relative URLs** (converts `//example.com` to `https://example.com`)
- **Normalizes www/non-www** based on configuration (`make_non_www` or `make_www`)
- **Removes fragments** (#anchors) since they point to the same file
- **Handles URL encoding** consistently

### 3. **Check Before Queueing**
Before adding any URL to the download queue, the code checks:
```python
if normalized_url not in self.config.visited_urls:
    links_to_follow.append(normalized_url)
```

This check happens for:
- Links in HTML (`<a href>`, `<link href>`, `<img src>`, `<script src>`)
- URLs in CSS (`url()` functions, `@import` statements)
- URLs in inline styles
- URLs in JavaScript (optional, if extraction is enabled)

### 4. **Check Before Downloading**
At the start of the download loop:
```python
if url in self.config.visited_urls:
    continue  # Skip this URL
```

### 5. **Mark as Visited**
Immediately after the check, before downloading:
```python
self.config.visited_urls.add(url)
```

This ensures that even if the download fails, the URL won't be retried (unless it's a new session).

## Potential Issues and Improvements

### Current Limitation: Query Parameters
The current normalization **does NOT remove query parameters**. This means:
- `style.css?v=1` and `style.css?v=2` are treated as different URLs
- `script.js?timestamp=123` and `script.js?timestamp=456` are downloaded twice

**Recommendation**: Consider removing query parameters during normalization for cache-busting patterns like `?v=`, `?ver=`, `?timestamp=`, etc., while preserving meaningful query parameters.

### Trailing Slashes
URLs with trailing slashes (`/page/` vs `/page`) might be treated differently depending on the server. The current implementation preserves the exact path from the URL.

### Same Content, Different Formats
The same file might be referenced as:
- `/image.jpg`
- `./image.jpg`
- `../images/image.jpg`
- `https://example.com/image.jpg`

The normalization handles these by converting relative paths to absolute using `urljoin()`, ensuring they map to the same normalized URL.

## Example Flow

1. HTML page contains: `<img src="/images/logo.png">`
2. URL is normalized to: `http://example.com/images/logo.png`
3. Check: Is `http://example.com/images/logo.png` in `visited_urls`? No
4. Add to queue
5. Later, another HTML page contains: `<link rel="stylesheet" href="https://example.com/images/logo.png">`
6. URL is normalized to: `http://example.com/images/logo.png` (https normalized to http, www removed if configured)
7. Check: Is `http://example.com/images/logo.png` in `visited_urls`? Yes
8. Skip - file already downloaded

## Statistics

After download completes, you can check:
- `len(self.config.visited_urls)` - Total unique URLs encountered
- `len(self.config.downloaded_files)` - Total files actually downloaded

These should be equal if all downloads succeeded.

