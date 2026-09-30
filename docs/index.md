# Wayback-Archive

Wayback-Archive is a Python tool that downloads archived websites from the [Wayback Machine](https://web.archive.org/) and reconstructs them for fully functional offline viewing. It preserves all assets (HTML, CSS, JavaScript, images and fonts), rewrites URLs to relative paths, and cleans up Wayback Machine artifacts so the result looks like the original site. Unlike `wget --mirror` or `httrack`, it understands Wayback Machine URLs.

- [Getting started](getting-started.md): install from PyPI or from source, and the first run
- [Configuration](configuration.md): every environment variable
- [Usage](usage.md): macOS, Linux and Windows examples
- [Features](features.md): the full list and a comparison with wget and httrack
- [How it works](how-it-works.md): the crawl steps, project layout and dependencies
- [Troubleshooting](troubleshooting.md): common problems and their fixes
- [Development](development.md): tests and contributing
- [Related projects](related.md): the other Wayback tools
