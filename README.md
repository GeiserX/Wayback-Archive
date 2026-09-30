<p align="center">
  <img src="https://raw.githubusercontent.com/GeiserX/Wayback-Archive/main/docs/images/banner.svg" alt="Wayback-Archive banner" width="900"/>
</p>

<p align="center">
  <strong>Rescue whole websites from the Wayback Machine.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/wayback-archive/"><img src="https://img.shields.io/pypi/v/wayback-archive?style=flat-square&logo=pypi&logoColor=white" alt="PyPI version"></a>
  <a href="https://github.com/GeiserX/Wayback-Archive/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/GeiserX/Wayback-Archive/ci.yml?style=flat-square&logo=github&label=build" alt="Build"></a>
  <a href="https://github.com/GeiserX/Wayback-Archive/blob/main/LICENSE"><img src="https://img.shields.io/github/license/GeiserX/Wayback-Archive?style=flat-square" alt="License"></a>
  <a href="https://pypi.org/project/wayback-archive/"><img src="https://img.shields.io/pypi/dm/wayback-archive?style=flat-square" alt="PyPI downloads per month"></a>
  <a href="https://github.com/GeiserX/Wayback-Archive/stargazers"><img src="https://img.shields.io/github/stars/GeiserX/Wayback-Archive?style=flat-square" alt="GitHub stars"></a>
</p>

---

Wayback-Archive is a command-line tool that downloads an archived website from the [Wayback Machine](https://web.archive.org/) and rebuilds it as a folder you can open offline. It fetches every page and asset it can find in the snapshot, rewrites the links to local paths and removes the Wayback Machine's own toolbar, scripts and URL prefixes, so the copy looks like the site did on that day. `wget --mirror` and `httrack` do not understand Wayback Machine URLs; this does.

<p align="center">
  <img src="https://raw.githubusercontent.com/GeiserX/Wayback-Archive/main/docs/images/screenshots/restored.png" alt="The python.org homepage of 31 December 2005, rescued and opened from the local copy: original layout, stylesheet and images, no Wayback Machine toolbar" width="900"/>
</p>

## Features

- Saves HTML, CSS, JavaScript, images and fonts, following links in HTML, CSS and JavaScript until nothing is left to fetch.
- Every link in the copy points at the local file, so pages open and lead to each other without the Wayback toolbar or its URL prefixes.
- A page or file missing from the snapshot is looked up at up to three other Wayback timestamps (a day either side and a week earlier) before it is given up on.
- A capture that is an archived error or a Cloudflare challenge page is replaced with the nearest good capture.
- Google Fonts are saved locally, and a font the archive returns as an HTML error page is dropped instead of breaking the page.
- Pages still work when the archive lost jQuery: a copy is fetched from `code.jquery.com` instead.
- Social icon groups, button links and cookie banners keep working in the copy.
- Analytics and ads are stripped by default; external iframes too, with `REMOVE_EXTERNAL_IFRAMES=true`.
- Optional HTML, CSS, JavaScript and image minification for a smaller folder.

## Quick start

```bash
pipx install wayback-archive
WAYBACK_URL="https://web.archive.org/web/20051231235226/http://www.python.org/" MAX_FILES=50 wayback-archive
open output/index.html                     # Linux: xdg-open output/index.html
```

Needs Python 3.10 or newer (on 3.9, pip stops with `ResolutionImpossible`); `pip install` works too, and the other install paths are in [Getting started](https://geiserx.github.io/Wayback-Archive/getting-started/). That run takes about a minute, ends with a `Download Complete!` block counting the files downloaded, failed and skipped, and opens from disk as the page above: the homepage, its stylesheet and its images are all within the first 50 files. Drop `MAX_FILES` to fetch the whole site. On another site a short run can stop before a stylesheet that is only reached through `@import`, because the crawl fetches files in the order it finds them. There are no flags: every setting is an environment variable, listed in [Configuration](https://geiserx.github.io/Wayback-Archive/configuration/).

## Documentation

The full documentation is at https://geiserx.github.io/Wayback-Archive/.

- [Getting started](https://geiserx.github.io/Wayback-Archive/getting-started/): pipx, pip or a checkout, and the first run
- [Configuration](https://geiserx.github.io/Wayback-Archive/configuration/): every environment variable and its default
- [Usage](https://geiserx.github.io/Wayback-Archive/usage/): macOS, Linux and Windows shells, the quick test, opening the copy
- [Features](https://geiserx.github.io/Wayback-Archive/features/): the full list and the comparison with wget and httrack
- [How it works](https://geiserx.github.io/Wayback-Archive/how-it-works/): the crawl steps, the fallbacks and the project layout
- [Troubleshooting](https://geiserx.github.io/Wayback-Archive/troubleshooting/): fonts, missing icons, libraries that do not load
- [Development](https://geiserx.github.io/Wayback-Archive/development/): tests and contributing
- [Related projects](https://geiserx.github.io/Wayback-Archive/related/): the other Wayback tools

## Related projects

[Wayback-Diff](https://github.com/GeiserX/Wayback-Diff), [Way-CMS](https://github.com/GeiserX/Way-CMS), [web-mirror](https://github.com/GeiserX/web-mirror), [media-download](https://github.com/GeiserX/media-download), [n8n-nodes-way-cms](https://github.com/GeiserX/n8n-nodes-way-cms) (archived).

## License

[GPL-3.0-or-later](https://github.com/GeiserX/Wayback-Archive/blob/main/LICENSE)
