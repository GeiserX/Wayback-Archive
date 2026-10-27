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

## Interrupting and resuming

A run can be stopped at any time with Ctrl-C. Running the same command again, with the same `WAYBACK_URL` and `OUTPUT_DIR`, carries on where it stopped:

```text
Resuming: 312 files done, 87 queued
```

Files already saved are not fetched again. The file being downloaded at the moment of the interruption is fetched again first. There is no setting for this: the tool keeps its progress in `OUTPUT_DIR/.wayback-archive-state.json`, writing it every 25 files and whenever the run stops early, and deletes it when the crawl finishes. A run of a different `WAYBACK_URL` in the same folder ignores the file and starts from the first page, and says so. A process killed outright (power loss, `kill -9`) gets no chance to save, so the next run goes back to the last save, at most 25 files earlier, and fetches those again. To start over on purpose, delete the file or the folder.

The same applies when a run stops early for other reasons:

- **Throttling.** When the Wayback Machine refuses 5 requests in a row, the run stops, and the next one retries those 5 files before the rest of the queue.
- **`MAX_FILES`.** The summary says how many queued URLs were not fetched (`Stopped at MAX_FILES; 87 queued URLs not fetched`). Running again with a higher `MAX_FILES`, or without it, continues the same crawl.

Every file is written to a temporary name first and renamed into place once complete, so a run killed mid-write never leaves a truncated file behind; a temporary file left by a run killed outright is removed when the next run starts.

The summary at the end lists the URLs that failed, up to 50, so what is missing from the copy is visible without scrolling back through the log.

## Exit status

The command exits with status 1 and a one-line `Error:` message when `WAYBACK_URL` is missing or is not a Wayback Machine URL, when `MAX_FILES` is not a positive whole number, when nothing could be saved because the start page has no usable capture, when the start page was saved raw but could not be processed (so no links were followed), or when the Wayback Machine refused 5 requests in a row (throttling with HTTP 429 or not answering), in which case the files saved so far stay in place and a later run resumes, retrying the refused files first. A 429 is first retried up to three times, waiting as long as its `Retry-After` header asks, up to 30 seconds. Ctrl-C stops the run with status 1 and keeps what was saved. Otherwise a run that saves the start page exits 0, even if some assets failed or `MAX_FILES` stopped it.
