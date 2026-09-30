"""Packaging metadata and CI must agree with each other.

Parsed as text: tomllib needs 3.11 and PyYAML is not a dependency.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = (ROOT / "pyproject.toml").read_text()
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text()


def _version(text):
    return tuple(int(part) for part in text.split("."))


def _ci_matrix():
    match = re.search(r"python-version:\s*\[([^\]]*)\]", CI)
    return sorted(_version(v) for v in re.findall(r'"([\d.]+)"', match.group(1)))


def test_requires_python_is_the_lowest_ci_version():
    # pip on a version below the floor falls back to an old release; on a
    # version above it but untested, it installs something CI never ran.
    floor = re.search(r'^requires-python = ">=([\d.]+)"', PYPROJECT, re.MULTILINE)
    assert _version(floor.group(1)) == _ci_matrix()[0]


def test_classifiers_list_exactly_the_ci_versions():
    listed = sorted(
        _version(v)
        for v in re.findall(r'"Programming Language :: Python :: (\d+\.\d+)"', PYPROJECT)
    )
    assert listed == _ci_matrix()
