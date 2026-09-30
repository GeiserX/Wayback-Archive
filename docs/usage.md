# Usage

## macOS / Linux

```bash
export WAYBACK_URL="https://web.archive.org/web/20051231235226/http://www.python.org/"
export OUTPUT_DIR="./my_website"
export REMOVE_CLICKABLE_CONTACTS="false"  # Keep email/phone links

python3 -m wayback_archive.cli
```

## Windows (PowerShell)

```powershell
$env:WAYBACK_URL = "https://web.archive.org/web/20051231235226/http://www.python.org/"
$env:OUTPUT_DIR = ".\my_website"
$env:REMOVE_CLICKABLE_CONTACTS = "false"

python -m wayback_archive.cli
```

## Windows (CMD)

```cmd
set WAYBACK_URL=https://web.archive.org/web/20051231235226/http://www.python.org/
set OUTPUT_DIR=.\my_website
set REMOVE_CLICKABLE_CONTACTS=false

python -m wayback_archive.cli
```

## Quick Test

Download the first 50 files to check that everything works. On this snapshot the homepage, its stylesheet and its images are all within the first 50, so the copy opens styled:

```bash
export WAYBACK_URL="https://web.archive.org/web/20051231235226/http://www.python.org/"
export MAX_FILES=50
python3 -m wayback_archive.cli
```

## Preview the result

The copy opens straight from disk: `open output/index.html` on macOS, `xdg-open output/index.html` on Linux, `start output\index.html` on Windows. A browser that blocks scripts on `file://` pages can use a local server instead:

```bash
cd output && python3 -m http.server 8000
# Open http://localhost:8000
```

## Exit status

The command exits with status 1 and a one-line `Error:` message when `WAYBACK_URL` is missing or is not a Wayback Machine URL, when `MAX_FILES` is not a positive whole number, when nothing could be saved because the start page has no usable capture, or when the Wayback Machine refused 5 requests in a row (throttling with HTTP 429 or not answering), in which case the files saved so far stay in place and a later run can be tried. A 429 is first retried up to three times, waiting as long as its `Retry-After` header asks, up to 30 seconds. Ctrl-C stops the run with status 1 and keeps what was saved. Otherwise a run that saves the start page exits 0, even if some assets failed.
