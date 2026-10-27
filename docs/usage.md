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

- **0**: the start page was saved, even if some assets failed or `MAX_FILES` stopped the crawl. The summary lists what failed.
- **1**: the run failed, with a one-line `Error:` message. That happens when `WAYBACK_URL` is not a Wayback Machine URL, when nothing could be saved because the start page has no usable capture, when the start page was saved raw but could not be processed (so no links were followed), or when the Wayback Machine refused 5 requests in a row (see below). Files saved so far stay in place.
- **2**: bad arguments or settings, caught before anything is downloaded: no Wayback URL, a `MAX_FILES` that is not a positive whole number, a `REQUEST_DELAY` that is not 0 or more seconds, an on/off option that is not one of the accepted values. The command prints its usage line and an `error:` message naming the setting.
- **130**: stopped with Ctrl-C. The summary is printed, what was saved stays, and the next run resumes.

### When the Wayback Machine refuses

A request the Wayback Machine throttles (HTTP 429) or answers with its own 502, 503 or 504 is retried up to 5 times in total. The waits grow 0, 2, 4, 8 and 16 seconds, each after the first with up to a second of random jitter added. When the answer carries a `Retry-After` header, the tool waits that long instead, but never more than 120 seconds. An answer slower than the timeout is retried twice; a connection that cannot be opened at all is not retried. A 429 or 5xx that is an archived capture (it carries a `memento-datetime` header) is the page as it was captured and is never retried. With `REQUEST_DELAY` set, the tool also waits that many seconds, give or take 20%, before every Wayback request.

A file still refused after its retries is refused for one of three reasons: `throttled` (a 429), `unavailable` (a 5xx, or a read timeout that outlived its retries) or `connection` (no answer). When 5 files in a row are refused, the run stops rather than keep asking. Those 5 are not counted as failed: they go back to the front of the queue, the progress is saved, and the next run fetches them first. The summary is titled `Download stopped early`, and the command then exits 1 with a line such as:

```text
Error: Stopped: the Wayback Machine refused 5 requests in a row (last: throttled); try again later
```
