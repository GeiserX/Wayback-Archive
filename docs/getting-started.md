# Getting started

## Prerequisites

- Python 3.10 or newer (on 3.9, pip stops with `ResolutionImpossible`)
- pipx or pip

## From PyPI

```bash
pipx install wayback-archive
```

pipx gives the command its own environment. Inside a virtual environment, pip works the same way:

```bash
pip install wayback-archive
```

Homebrew Python and the system Python on Debian and Ubuntu refuse a bare `pip install` with `externally-managed-environment`, which is why pipx comes first. See [Troubleshooting](troubleshooting.md#pip-refuses-to-install-externally-managed-environment) for both fixes.

Then give it one Wayback Machine URL:

```bash
WAYBACK_URL="https://web.archive.org/web/20051231235226/http://www.python.org/" MAX_FILES=50 wayback-archive
```

The copy lands in `./output` (set `OUTPUT_DIR` to change it). `MAX_FILES=50` keeps the first try to about a minute, and on this snapshot the homepage, its stylesheet and its images are all within those 50 files, so the copy opens styled. Drop `MAX_FILES` to fetch the whole site. On another site a short run can stop before a stylesheet that is only reached through `@import`, because the crawl fetches files in the order it finds them. Every setting is in [Configuration](configuration.md); per-shell examples are in [Usage](usage.md).

## What a finished run looks like

Each file prints a numbered line while it downloads. The run ends with a block like this one:

```text
======================================================================
Download Complete!
======================================================================
Output directory: ./output
Files successfully downloaded: 50
Files failed: 0
Files skipped (duplicates): 0
Total files processed: 50
======================================================================
```

`Files failed` (none here) counts pages and files the archive does not have at that timestamp or any nearby one; their links stay broken in the copy.

Open the copy straight from disk:

```bash
open output/index.html        # macOS
xdg-open output/index.html    # Linux
start output\index.html       # Windows
```

A browser that blocks scripts on `file://` pages can use a local server instead: `cd output && python3 -m http.server 8000`, then open `http://localhost:8000`.

## From source

```bash
git clone https://github.com/GeiserX/Wayback-Archive.git
cd Wayback-Archive

# Optional: create a virtual environment
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

pip install -r config/requirements.txt
WAYBACK_URL="https://web.archive.org/web/20051231235226/http://www.python.org/" python3 -m wayback_archive.cli
```

To get the `wayback-archive` command from a checkout, install it in editable mode with `pip install -e .`.
