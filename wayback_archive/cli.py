"""Command-line interface for Wayback-Archive."""

import argparse
import os
import sys
import traceback

from dotenv import load_dotenv

from wayback_archive import __version__
from wayback_archive.config import Config
from wayback_archive.downloader import WaybackDownloader

DOCS_URL = "https://geiserx.github.io/Wayback-Archive/configuration/"

# What each on/off option does, for --help.
BOOL_HELP = {
    "optimize_html": "minify HTML",
    "optimize_images": "recompress still images in their own format",
    "minify_js": "minify JavaScript",
    "minify_css": "minify CSS",
    "remove_trackers": "remove analytics and trackers",
    "remove_ads": "remove advertisements",
    "remove_clickable_contacts": "point tel: and mailto: links at #, keeping their text",
    "remove_external_iframes": "remove external iframes",
    "remove_external_links_keep_anchors": "remove external links, keep what they wrap",
    "remove_external_links_remove_anchors": "delete external links together with what they wrap",
    "make_internal_links_relative": "convert internal links to relative paths",
    "make_non_www": "drop www. from the archived site's host",
    "make_www": "add www. to the archived site's host",
}


def _positive_int(text: str) -> int:
    if not (text.isascii() and text.isdigit() and int(text) > 0):
        raise argparse.ArgumentTypeError(f"must be a positive whole number, got {text!r}")
    return int(text)


def _seconds(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        value = -1.0
    if not (0 <= value < float("inf")):
        raise argparse.ArgumentTypeError(f"must be a number of seconds, 0 or more, got {text!r}")
    return value


def build_parser() -> argparse.ArgumentParser:
    """The argument parser. Every option defaults to None, meaning not given,
    so its environment variable or its default applies."""
    parser = argparse.ArgumentParser(
        prog="wayback-archive",
        usage="%(prog)s [URL] [options]",
        description="Download a website snapshot from the Wayback Machine and rebuild it for offline viewing.",
        epilog=(
            "Every option can also be set with its environment variable, or in a .env file in the "
            "current directory. A flag wins over the environment, which wins over .env. "
            f"Documentation: {DOCS_URL}"
        ),
    )
    parser.add_argument(
        "wayback_url",
        nargs="?",
        metavar="URL",
        help="the Wayback Machine URL to download, such as "
        "https://web.archive.org/web/20051231235226/http://www.python.org/ (env WAYBACK_URL)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        metavar="DIR",
        help="where to write the site (env OUTPUT_DIR, default: ./output)",
    )
    parser.add_argument(
        "--max-files",
        type=_positive_int,
        metavar="N",
        help="stop after trying this many files, failed ones included (env MAX_FILES, default: unlimited)",
    )
    parser.add_argument(
        "--request-delay",
        type=_seconds,
        metavar="SECONDS",
        help="wait this long between requests to the Wayback Machine (env REQUEST_DELAY, default: 0)",
    )
    for name, env, default in Config.BOOL_OPTIONS:
        parser.add_argument(
            "--" + name.replace("_", "-"),
            dest=name,
            action=argparse.BooleanOptionalAction,
            default=None,
            help=f"{BOOL_HELP[name]} (env {env}, default: {'on' if default else 'off'})",
        )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv=None):
    """Main CLI entry point.

    Exit codes: 0 complete, 1 the run failed, 2 bad usage or configuration,
    130 interrupted.
    """
    # Ensure unbuffered output for real-time logging
    sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, "reconfigure") else None

    parser = build_parser()
    args = parser.parse_args(argv)

    # Only the .env of the directory the command runs from; variables
    # already in the environment win over it.
    if os.path.isfile(".env"):
        load_dotenv(".env")
    config = Config(**{name: value for name, value in vars(args).items() if value is not None})

    # Validate configuration
    is_valid, error = config.validate()
    if not is_valid:
        parser.error(error)

    try:
        downloader = WaybackDownloader(config)
    except ValueError as e:
        # A URL that is not a Wayback address.
        print(f"Error: {e}", file=sys.stderr, flush=True)
        sys.exit(1)

    try:
        downloader.download()
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr, flush=True)
        sys.exit(130)
    except RuntimeError as e:
        # The run stopped: nothing was saved, or Wayback kept refusing.
        print(f"Error: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr, flush=True)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
