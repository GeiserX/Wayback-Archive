# Usage

## macOS / Linux

```bash
export WAYBACK_URL="https://web.archive.org/web/20250417203037/http://example.com/"
export OUTPUT_DIR="./my_website"
export REMOVE_CLICKABLE_CONTACTS="false"  # Keep email/phone links

python3 -m wayback_archive.cli
```

## Windows (PowerShell)

```powershell
$env:WAYBACK_URL = "https://web.archive.org/web/20250417203037/http://example.com/"
$env:OUTPUT_DIR = ".\my_website"
$env:REMOVE_CLICKABLE_CONTACTS = "false"

python -m wayback_archive.cli
```

## Windows (CMD)

```cmd
set WAYBACK_URL=https://web.archive.org/web/20250417203037/http://example.com/
set OUTPUT_DIR=.\my_website
set REMOVE_CLICKABLE_CONTACTS=false

python -m wayback_archive.cli
```

## Quick Test

Download a limited number of files to verify everything works:

```bash
export WAYBACK_URL="https://web.archive.org/web/20250417203037/http://example.com/"
export MAX_FILES=5
python3 -m wayback_archive.cli
```

## Preview the result

```bash
cd output && python3 -m http.server 8000
# Open http://localhost:8000
```

## Exit status

The command exits with status 1 and a one-line `Error:` message when `WAYBACK_URL` is not a Wayback Machine URL, when nothing could be saved because the start page has no usable capture, or when the Wayback Machine refused 5 requests in a row (throttling with HTTP 429 or not answering), in which case the files saved so far stay in place and a later run can be tried. A 429 is first retried up to three times, waiting as long as its `Retry-After` header asks, up to 30 seconds. Otherwise a run that saves the start page exits 0, even if some assets failed.
