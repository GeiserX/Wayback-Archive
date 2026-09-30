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
