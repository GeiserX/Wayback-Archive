"""Command-line interface for Wayback-Archive."""

import sys
from wayback_archive.config import Config
from wayback_archive.downloader import WaybackDownloader


def main():
    """Main CLI entry point."""
    config = Config()
    
    # Validate configuration
    is_valid, error = config.validate()
    if not is_valid:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    # Create downloader and start
    downloader = WaybackDownloader(config)
    
    try:
        downloader.download()
    except KeyboardInterrupt:
        print("\nDownload interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

