"""Command-line interface for Wayback-Archive."""

import sys
from dotenv import find_dotenv, load_dotenv
from wayback_archive.config import Config
from wayback_archive.downloader import WaybackDownloader


def main():
    """Main CLI entry point."""
    # Ensure unbuffered output for real-time logging
    sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

    # A .env in the directory the command runs from (or a parent). The
    # default search starts at this module, inside site-packages once
    # installed, and never reached the user's project.
    load_dotenv(find_dotenv(usecwd=True))
    config = Config()
    
    # Validate configuration
    is_valid, error = config.validate()
    if not is_valid:
        print(f"Error: {error}", file=sys.stderr, flush=True)
        sys.exit(1)

    try:
        downloader = WaybackDownloader(config)
        downloader.download()
    except KeyboardInterrupt:
        print("\nDownload interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()


