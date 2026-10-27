"""Wayback-Archive - A comprehensive tool for downloading websites from Wayback Machine."""

__version__ = "1.6.0"
__all__ = ["download", "__version__"]


def download(wayback_url: str, output_dir: str = "./output", **options) -> None:
    """Download a Wayback Machine snapshot into output_dir.

    options are keyed like the Config attributes (optimize_html=False,
    max_files=50, request_delay=1.0, ...); an option not given comes from
    its environment variable, then its default. Raises ValueError for an
    invalid option and RuntimeError when the run fails.
    """
    # Imported here so that reading __version__ needs no dependencies.
    from wayback_archive.config import Config
    from wayback_archive.downloader import WaybackDownloader

    config = Config(wayback_url=wayback_url, output_dir=output_dir, **options)
    is_valid, error = config.validate()
    if not is_valid:
        raise ValueError(error)
    WaybackDownloader(config).download()
