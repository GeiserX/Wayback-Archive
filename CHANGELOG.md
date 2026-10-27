# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

<!-- lanes: add under Unreleased -->

### Added

- Command-line flags for every option: `wayback-archive URL [options]` with `-o/--output-dir`, `--max-files`, `--request-delay`, `--version` and an on/off pair for each boolean (`--minify-css` / `--no-minify-css`). A flag wins over the environment, the environment over `./.env`. `--help` works without a URL (#75).
- A Python API: `wayback_archive.download(wayback_url, output_dir="./output", **options)` (#75).
- `REQUEST_DELAY` / `--request-delay`: seconds to wait, give or take 20%, before every Wayback request (default 0) (#74, #75).
- Resume: an interrupted run (Ctrl-C, the Wayback Machine throttling, a `MAX_FILES` stop) saves its progress to `OUTPUT_DIR/.wayback-archive-state.json`, and running the same command again carries on where it stopped instead of starting over (#76).
- The final summary lists the failed URLs, up to 50 (#76).
- Docker image on Docker Hub: `drumsergio/wayback-archive:<version>` and `:<major>.<minor>`, for amd64 and arm64. It runs as a non-root user and writes to `/output`. There is no `:latest` tag (#73). Its Docker Hub page follows README.md.
- Python 3.13 and 3.14 are supported and tested; the test suite also runs on Windows and macOS (#73).
- Each release attaches its wheel and sdist to the GitHub release (#73).

### Changed

- **Behaviour change: `OPTIMIZE_HTML` now defaults to off.** minify-html removed the visible space between inline elements and collapsed text styled `white-space: pre`, and no minify-html option avoids it. Set `OPTIMIZE_HTML=true` (or `--optimize-html`) to minify as before (#77).
- CSS minification (`MINIFY_CSS`) uses `rcssmin` instead of `cssmin`, which broke `calc()` and `@supports` rules (#77).
- Exit statuses: 0 done, 1 the run failed, 2 bad arguments or settings (a missing URL, a misspelled boolean such as `REMOVE_ADS=ture`), 130 on Ctrl-C. A misspelled boolean used to run silently with the wrong setting, and Ctrl-C used to exit 1. Only `./.env` is read, not one in a parent directory (#75).
- A page whose URL has a query string (`page?id=1`, `index.php?id=3`) gets its own file (`page__q<hash>.html`) instead of overwriting the first variant; a query of cache-busters only (`v`, `ver`, `_`, `t`, ...) still maps to the plain name (#72).
- File names are valid on every filesystem: `<>:"|?*` and control characters become `_`, trailing dots and spaces go, names Windows reserves (`CON`, `nul.txt`) get `_` after the stem, and an over-long name is shortened instead of failing (#72).
- `WAYBACK_URL` is matched case-insensitively and trimmed, and `https:/host` is accepted (#72).
- Wayback's own 502, 503 and 504 are retried like a 429: up to 5 times, waiting 0, 2, 4, 8 and 16 seconds plus jitter, or as long as `Retry-After` asks, up to 120 seconds. A brief outage no longer loses files (#74).
- Rewrite fidelity: a reference to another site (a CDN image, an embedded video, a CSS `url()`) points at its real address instead of a Wayback path; HTML comments are kept, IE conditional comments included, and only Wayback's own are removed; only Wayback's own inline scripts are removed; text attributes such as `alt` and `title` are left as written; CSS `url()` keeps its `#fragment`; font clean-up touches only `@font-face` blocks and leaves a legacy-only font its source (#77).
- `OPTIMIZE_IMAGES` keeps ICC profiles, EXIF and progressive JPEG encoding, and leaves lossless WebP and animated images alone (#77).
- Every file is written to a temporary name and renamed into place, so a run killed mid-write never leaves a truncated file (#76).
- Dependency floors are the oldest versions the tool works with (for example `requests>=2.32.0`, `Pillow>=10.0.0`), so installing it no longer forces upgrades of packages you already have (#73).
- PyPI metadata: Internet and Archiving topics instead of Build Tools, keywords, and links to the documentation, this changelog and the issue tracker (#73).

### Fixed

- SVG images that start with `<!DOCTYPE svg` are kept instead of being dropped as corrupted fonts, and old latin-1 pages keep characters they used to lose (#74).
- A run whose start page was saved raw but could not be processed now exits 1 instead of reporting success (#76).
- `Files skipped (duplicates)` counts duplicates; it was always 0 (#76).

### Security

- Every file the tool saves comes from web.archive.org or the live-CDN allowlist (Google Fonts, `code.jquery.com`, the Squarespace CDN): a Wayback answer that redirected to another host is refused, a host such as `evil.com\.fonts.gstatic.com` no longer passes the allowlist, and a live CDN fetch goes over HTTPS on the default port only (#74).
- No response body larger than 512 MiB is read (#74).
- Every GitHub Actions workflow runs with a read-only token by default and uses actions pinned to a commit (#73).
- A manual run of the release workflow builds and checks the package but never publishes it (#73).
- PyPI releases use Trusted Publishing with attestations: no PyPI token is stored anywhere.

## [1.5.0] - 2026-09-30

### Security

- A page could make the tool fetch an arbitrary host directly, for example `http://web.archive.org@169.254.169.254/`, and save the response (#55). Every 1.4.x version is affected; upgrade to 1.5.0.

### Changed

- The live site is no longer used to fill gaps: a file the Wayback Machine does not have is reported as failed. Only Google Fonts, `code.jquery.com` and the Squarespace CDN are ever fetched live.
- Python 3.10 or newer is required.
- The command exits 1 when nothing was saved, when `WAYBACK_URL` is malformed, and when the Wayback Machine refuses 5 requests in a row.
- `MAX_FILES` bounds attempts, and a value that is not a positive integer is an error.
- Server-side pages are stored as `<name>.php.html`.

### Removed

- `KEEP_REDIRECTIONS`, which never did anything.

### Fixed

- Relative links were requested as hostnames, so many sites archived as a mix of unrelated pages and failures (#56).
- A capture that is a Cloudflare challenge or a server error is replaced by the nearest capture with status 200 (#48, #57).
- Pages that are not UTF-8 keep their accented characters (#56).
- The font clean-up no longer deletes neighbouring CSS rules, and runs in linear time (#55).
- The site's own scripts and images are no longer removed as ads, trackers or toolbar code; `srcset`, fragment links, `data-*` JSON, `<base href>`, SVG sprites and media elements are handled, and the files they point at are downloaded (#58).
- A missing file costs at most 5 requests instead of 15, and HTTP 429 is retried with backoff (#57).
- Ctrl-C stops the run, and `.env` is read from the directory the command runs in (#57).
- `OPTIMIZE_IMAGES` keeps transparency, animation and icons (#58).

## [1.4.6] - 2026-08-20

### Fixed

- The sdist on PyPI contained no code, so `pip install --no-binary :all: wayback-archive` failed on every earlier release. Metadata moved to a root `pyproject.toml`, and the release workflow installs the sdist in a clean environment before uploading.

## [1.4.5] - 2026-08-20

### Fixed

- A stylesheet imported without `url()` (`@import "theme.css";`) was downloaded but the reference still pointed at the live site.
- A resource whose URL has no file extension was requested in the wrapped replay form; it now gets the `cs_`, `js_` or `im_` form that matches what referenced it.

## [1.4.4] - 2026-08-19

### Fixed

- Stylesheets and scripts served from a URL without a file extension were saved as HTML, wrapped in `<body>`, and their `@import` targets were never downloaded. The element that references a resource now decides its kind, its saved extension and its content type.

## [1.4.3] - 2026-08-19

### Fixed

- Directory-style pages (`/blog/`, `/about/`) all wrote to the root `index.html`, so a multi-page site could archive down to one file. Re-archive any site saved with an earlier version.
- Inline `style="...url(...)"` references kept pointing at the live site.
- Links to files whose names hold `#` or `?`, stylesheet `url()` paths, CDN root URLs and extensionless assets could point at a file that was never written.

[Unreleased]: https://github.com/GeiserX/Wayback-Archive/compare/v1.5.0...HEAD
[1.5.0]: https://github.com/GeiserX/Wayback-Archive/compare/v1.4.6...v1.5.0
[1.4.6]: https://github.com/GeiserX/Wayback-Archive/compare/v1.4.5...v1.4.6
[1.4.5]: https://github.com/GeiserX/Wayback-Archive/compare/v1.4.4...v1.4.5
[1.4.4]: https://github.com/GeiserX/Wayback-Archive/compare/v1.4.3...v1.4.4
[1.4.3]: https://github.com/GeiserX/Wayback-Archive/releases/tag/v1.4.3
