import re
from pathlib import Path

from setuptools import find_packages, setup


CONFIG_DIR = Path(__file__).resolve().parent
REPO_ROOT = CONFIG_DIR.parent


def read_version() -> str:
    """Read the package version from the source package."""
    init_py = REPO_ROOT / "wayback_archive" / "__init__.py"
    match = re.search(
        r'^__version__ = ["\']([^"\']+)["\']',
        init_py.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not match:
        raise RuntimeError("Unable to find package version in wayback_archive/__init__.py")
    return match.group(1)


with (REPO_ROOT / "README.md").open("r", encoding="utf-8") as fh:
    long_description = fh.read()

with (CONFIG_DIR / "requirements.txt").open("r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="wayback-archive",
    version=read_version(),
    author="GeiserX",
    description="A comprehensive tool for downloading and archiving websites from the Wayback Machine",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/GeiserX/Wayback-Archive",
    packages=find_packages(where=str(REPO_ROOT), exclude=["tests", "tests.*"]),
    package_dir={"": str(REPO_ROOT)},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.9",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "wayback-archive=wayback_archive.cli:main",
        ],
    },
)
