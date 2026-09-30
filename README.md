<p align="center">
  <img src="https://raw.githubusercontent.com/GeiserX/Wayback-Archive/main/docs/images/banner.svg" alt="Wayback-Archive banner" width="900"/>
</p>

<p align="center">
  <strong>Download complete websites from the Wayback Machine for offline viewing.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/wayback-archive/"><img src="https://img.shields.io/pypi/v/wayback-archive?style=flat-square" alt="PyPI"></a>
  <a href="https://github.com/GeiserX/Wayback-Archive/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/GeiserX/Wayback-Archive/ci.yml?style=flat-square&logo=github&label=build" alt="Build"></a>
  <a href="https://github.com/GeiserX/Wayback-Archive/blob/main/LICENSE"><img src="https://img.shields.io/github/license/GeiserX/Wayback-Archive?style=flat-square" alt="License"></a>
  <a href="https://github.com/GeiserX/Wayback-Archive/stargazers"><img src="https://img.shields.io/github/stars/GeiserX/Wayback-Archive?style=flat-square" alt="GitHub Stars"></a>
  <a href="https://codecov.io/gh/GeiserX/Wayback-Archive"><img src="https://codecov.io/gh/GeiserX/Wayback-Archive/graph/badge.svg" alt="codecov"></a>
</p>

---

Wayback-Archive is a Python tool that downloads archived websites from the [Wayback Machine](https://web.archive.org/) and reconstructs them for fully functional offline viewing. It preserves all assets -- HTML, CSS, JavaScript, images, and fonts -- rewrites URLs to relative paths, and cleans up Wayback Machine artifacts so the result looks like the original site. Unlike `wget --mirror` or `httrack`, it understands Wayback Machine URLs.

## Features

- Downloads HTML, CSS, JS, images, fonts and every linked asset, following links in HTML, CSS and JS.
- Rewrites every link to a relative path so the copy works from a local server.
- Tries up to three other Wayback Machine timestamps (a day either side and a week earlier) when a resource returns 404.
- Replaces a capture that is an archived error or a Cloudflare challenge page with the nearest good capture.
- Saves Google Fonts locally, and removes corrupted fonts (HTML error pages served as fonts).
- Falls back to a CDN for critical libraries such as jQuery.
- Keeps icon groups, button links and cookie consent popups working.
- Optional HTML, JS, CSS and image minification, and removal of trackers, ads and external iframes.
- Configured with environment variables or a `.env` file.

## Quick start

```bash
pip install wayback-archive
WAYBACK_URL="https://web.archive.org/web/20250417203037/http://example.com/" wayback-archive
cd output && python3 -m http.server 8000   # then open http://localhost:8000
```

Needs Python 3.10 or newer. The source install and every setting are in [Getting started](https://github.com/GeiserX/Wayback-Archive/blob/main/docs/getting-started.md).

## Documentation

The documentation is published as a site at [geiserx.github.io/Wayback-Archive](https://geiserx.github.io/Wayback-Archive/). The same pages on GitHub:

- [Getting started](https://github.com/GeiserX/Wayback-Archive/blob/main/docs/getting-started.md): install from PyPI or from source, and the first run
- [Configuration](https://github.com/GeiserX/Wayback-Archive/blob/main/docs/configuration.md): every environment variable
- [Usage](https://github.com/GeiserX/Wayback-Archive/blob/main/docs/usage.md): macOS, Linux and Windows examples
- [Features](https://github.com/GeiserX/Wayback-Archive/blob/main/docs/features.md): the full list and a comparison with wget and httrack
- [How it works](https://github.com/GeiserX/Wayback-Archive/blob/main/docs/how-it-works.md): the crawl steps, project layout and dependencies
- [Troubleshooting](https://github.com/GeiserX/Wayback-Archive/blob/main/docs/troubleshooting.md), including the [font loading notes](https://github.com/GeiserX/Wayback-Archive/blob/main/docs/FONT_LOADING.md)
- [Development](https://github.com/GeiserX/Wayback-Archive/blob/main/docs/development.md): tests and contributing
- [Related projects](https://github.com/GeiserX/Wayback-Archive/blob/main/docs/related.md): the other Wayback tools
- [Releases](https://github.com/GeiserX/Wayback-Archive/releases)

## Related projects

[Wayback-Diff](https://github.com/GeiserX/Wayback-Diff), [Way-CMS](https://github.com/GeiserX/Way-CMS), [web-mirror](https://github.com/GeiserX/web-mirror), [media-download](https://github.com/GeiserX/media-download), [n8n-nodes-way-cms](https://github.com/GeiserX/n8n-nodes-way-cms) (archived). Descriptions are in [Related projects](https://github.com/GeiserX/Wayback-Archive/blob/main/docs/related.md).

## License

[GPL-3.0-or-later](https://github.com/GeiserX/Wayback-Archive/blob/main/LICENSE)
