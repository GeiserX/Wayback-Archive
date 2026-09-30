"""The PyPI token must only be visible to the step that uploads.

A job-level env exports it to every step, including pip installs and the
build backend, which run third-party code. Parsed as text because PyYAML is
not a dependency.
"""

import re
from pathlib import Path

RELEASE = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "release.yml"


def _steps(text):
    """Split the steps list into one text block per step."""
    steps_body = text.split("\n    steps:\n", 1)[1]
    return re.split(r"\n(?=    - )", steps_body)


def test_token_is_only_in_the_upload_step():
    text = RELEASE.read_text()
    assert text.count("secrets.PYPI_API_TOKEN") == 1
    holders = [step for step in _steps(text) if "secrets.PYPI_API_TOKEN" in step]
    assert len(holders) == 1
    assert "twine upload" in holders[0]


def test_job_has_no_env_block():
    job = RELEASE.read_text().split("\n    steps:\n", 1)[0]
    assert not re.search(r"^    env:", job, re.MULTILINE)


def test_runs_when_a_release_is_published():
    # `created` never fires for a draft, so publishing a saved draft would
    # release nothing; `published` covers both flows.
    text = RELEASE.read_text()
    assert re.search(r"^    types: \[published\]$", text, re.MULTILINE)


def test_tag_must_match_the_package_version_before_building():
    steps = _steps(RELEASE.read_text())
    check = next(i for i, step in enumerate(steps)
                 if "wayback_archive.__version__" in step and "GITHUB_REF_NAME" in step)
    build = next(i for i, step in enumerate(steps) if "name: Build package" in step)
    assert check < build
