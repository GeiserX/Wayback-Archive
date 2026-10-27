"""The release workflow publishes only from a published release, only what it checked.

The PyPI token must only be visible to the step that uploads: a job-level env
exports it to every step, including pip installs and the build backend, which
run third-party code. Parsed as text because PyYAML is not a dependency.
"""

import re
from pathlib import Path

RELEASE = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "release.yml"
TEXT = RELEASE.read_text()


def _job(name):
    """The text of one job, from its key to the next job's key."""
    jobs = TEXT.split("\njobs:\n", 1)[1]
    blocks = re.split(r"\n(?=  [a-z][\w-]*:\n)", "\n" + jobs)
    return next(block for block in blocks if block.lstrip("\n").startswith(f"  {name}:\n"))


def _steps(job_text):
    """Split a job's steps list into one text block per step."""
    steps_body = job_text.split("\n    steps:\n", 1)[1]
    return re.split(r"\n(?=    - )", steps_body)


def _header(job_text):
    return job_text.split("\n    steps:\n", 1)[0]


def test_runs_when_a_release_is_published():
    # `created` never fires for a draft, so publishing a saved draft would
    # release nothing; `published` covers both flows.
    assert re.search(r"^    types: \[published\]$", TEXT, re.MULTILINE)


def test_workflow_token_is_read_only_by_default():
    assert re.search(r"^permissions:\n  contents: read$", TEXT, re.MULTILINE)


def test_build_job_never_sees_a_secret():
    assert "secrets." not in _job("build")


def test_tag_check_runs_on_every_event_before_building():
    steps = _steps(_job("build"))
    check = next(
        i for i, step in enumerate(steps) if "wayback_archive.__version__" in step and "GITHUB_REF_NAME" in step
    )
    assert "if:" not in steps[check]
    build = next(i for i, step in enumerate(steps) if "name: Build package" in step)
    assert check < build


def test_build_tools_are_pinned():
    assert re.search(r"pip install build==[\d.]+ twine==[\d.]+", _job("build"))


def test_publishing_jobs_run_only_for_a_release():
    # workflow_dispatch is a dry run: it builds and checks, never publishes.
    for name in ("publish", "docker-publish"):
        header = _header(_job(name))
        assert "if: github.event_name == 'release'" in header
        assert "needs: build" in header


def test_publish_uses_the_built_artifact_in_the_pypi_environment():
    job = _job("publish")
    assert "environment: pypi" in _header(job)
    assert "actions/download-artifact@" in job
    assert "python -m build" not in job


def test_token_is_only_in_the_upload_step():
    assert TEXT.count("secrets.PYPI_API_TOKEN") == 1
    holders = [step for step in _steps(_job("publish")) if "secrets.PYPI_API_TOKEN" in step]
    assert len(holders) == 1
    assert "twine upload" in holders[0]


def test_jobs_have_no_env_block():
    for name in ("build", "publish", "docker-publish"):
        assert not re.search(r"^    env:", _header(_job(name)), re.MULTILINE)


def test_missing_token_fails_the_release():
    upload = next(step for step in _steps(_job("publish")) if "twine upload" in step)
    assert "exit 1" in upload
    assert "exit 0" not in upload
    assert "::warning::" not in upload


def test_distributions_are_attached_to_the_release():
    job = _job("publish")
    assert "contents: write" in _header(job)
    assert 'gh release upload "$GITHUB_REF_NAME" dist/*' in job


def test_docker_image_is_never_tagged_latest():
    job = _job("docker-publish")
    assert "geiserx/wayback-archive:$VERSION" in job
    assert ":latest" not in job
    secrets_check = _steps(job)[0]
    assert "DOCKERHUB_TOKEN" in secrets_check and "exit 1" in secrets_check
