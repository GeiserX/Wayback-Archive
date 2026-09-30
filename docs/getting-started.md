# Getting started

## Prerequisites

- Python 3.10 or higher
- pip

## From PyPI

```bash
pip install wayback-archive
WAYBACK_URL="https://web.archive.org/web/20250417203037/http://example.com/" wayback-archive
```

The copy lands in `./output` (set `OUTPUT_DIR` to change it). Serve it and open `http://localhost:8000`:

```bash
cd output && python3 -m http.server 8000
```

Every setting is in [Configuration](configuration.md); per-shell examples are in [Usage](usage.md).

## From source

```bash
git clone https://github.com/GeiserX/Wayback-Archive.git
cd Wayback-Archive

# Optional: create a virtual environment
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

pip install -r config/requirements.txt
WAYBACK_URL="https://web.archive.org/web/20250417203037/http://example.com/" python3 -m wayback_archive.cli
```

To get the `wayback-archive` command from a checkout, install it in editable mode with `pip install -e .`.
