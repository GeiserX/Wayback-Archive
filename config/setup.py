from setuptools import setup, find_packages
import os

# Get the parent directory (repository root)
repo_root = os.path.dirname(os.path.dirname(__file__))

# Read README from parent directory
readme_path = os.path.join(repo_root, "README.md")
with open(readme_path, "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Read requirements from current directory (config/)
with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="wayback-archive",
    version="1.0.0",
    author="GeiserX",
    description="A comprehensive tool for downloading and archiving websites from the Wayback Machine",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/GeiserX/Wayback-Archive",
    packages=find_packages(where=repo_root, exclude=["tests", "tests.*"]),
    package_dir={"": repo_root},
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
