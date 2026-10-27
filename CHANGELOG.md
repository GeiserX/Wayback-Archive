# Changelog

All notable changes to this project are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

<!-- lanes: add under Unreleased -->

### Added

- Docker image on Docker Hub: `geiserx/wayback-archive:<version>` and `:<major>.<minor>`, for amd64 and arm64. It runs as a non-root user and writes to `/output`. There is no `:latest` tag.
- Python 3.13 and 3.14 are supported and tested; the test suite also runs on macOS.
- Each release attaches its wheel and sdist to the GitHub release.

### Changed

- Dependency floors are the oldest versions the tool works with (for example `requests>=2.32.0`, `Pillow>=10.0.0`), so installing it no longer forces upgrades of packages you already have. `rcssmin` joins the requirements.
- PyPI metadata: Internet and Archiving topics instead of Build Tools, keywords, and links to the documentation, this changelog and the issue tracker.

### Security

- Every GitHub Actions workflow runs with a read-only token by default and uses actions pinned to a commit.
- A manual run of the release workflow builds and checks the package but never publishes it, and a release fails instead of passing when the PyPI token is missing.

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
