# Usage

Pass the Wayback Machine URL as the first argument and options as flags. The same command works in every shell:

```bash
wayback-archive "https://web.archive.org/web/20051231235226/http://www.python.org/" -o ./my_website --no-remove-clickable-contacts
```

`--no-remove-clickable-contacts` keeps email and phone links. Every flag, its environment variable and its default are in [Configuration](configuration.md).

Environment variables set the same options, which suits scripts and containers; a flag given on the command line wins over them.

## macOS / Linux

```bash
export WAYBACK_URL="https://web.archive.org/web/20051231235226/http://www.python.org/"
export OUTPUT_DIR="./my_website"
export REMOVE_CLICKABLE_CONTACTS="false"  # Keep email/phone links

wayback-archive
```

## Windows (PowerShell)

```powershell
$env:WAYBACK_URL = "https://web.archive.org/web/20051231235226/http://www.python.org/"
$env:OUTPUT_DIR = ".\my_website"
$env:REMOVE_CLICKABLE_CONTACTS = "false"

wayback-archive
```

## Windows (CMD)

```cmd
set WAYBACK_URL=https://web.archive.org/web/20051231235226/http://www.python.org/
set OUTPUT_DIR=.\my_website
set REMOVE_CLICKABLE_CONTACTS=false

wayback-archive
```

## From Python

`wayback_archive.download()` runs the same download from a script:

```python
import wayback_archive

wayback_archive.download(
    "https://web.archive.org/web/20051231235226/http://www.python.org/",
    output_dir="./my_website",
    remove_clickable_contacts=False,
    max_files=50,
)
```

The keyword arguments are the flags' names with underscores (`optimize_html`, `minify_css`, `request_delay`, ...). An option left out comes from its environment variable, then its default. An invalid value raises `ValueError`, an unknown option `TypeError`, and a run that saves nothing or is stopped by the Wayback Machine raises `RuntimeError`.

## Quick Test

Download the first 50 files to check that everything works. On this snapshot the homepage, its stylesheet and its images are all within the first 50, so the copy opens styled:

```bash
export WAYBACK_URL="https://web.archive.org/web/20051231235226/http://www.python.org/"
export MAX_FILES=50
wayback-archive
```

## Preview the result

The copy lands in the `OUTPUT_DIR` folder, `./my_website` in the examples above (`./output` when `OUTPUT_DIR` is unset). It opens straight from disk: `open my_website/index.html` on macOS, `xdg-open my_website/index.html` on Linux, `start my_website\index.html` on Windows. A browser that blocks scripts on `file://` pages can use a local server instead:

```bash
cd my_website && python3 -m http.server 8000
# Open http://localhost:8000
```

## Exit status

The command exits with status 1 and a one-line `Error:` message when `WAYBACK_URL` is missing or is not a Wayback Machine URL, when `MAX_FILES` is not a positive whole number, when nothing could be saved because the start page has no usable capture, or when the Wayback Machine refused 5 requests in a row (throttling with HTTP 429 or not answering), in which case the files saved so far stay in place and a later run can be tried. A 429 is first retried up to three times, waiting as long as its `Retry-After` header asks, up to 30 seconds. Ctrl-C stops the run with status 1 and keeps what was saved. Otherwise a run that saves the start page exits 0, even if some assets failed.
