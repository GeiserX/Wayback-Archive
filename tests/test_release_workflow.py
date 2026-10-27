"""The release workflow publishes only from a published release, only what it checked.

PyPI uploads go through Trusted Publishing: the publish job alone may mint an
OIDC token, and no PyPI token exists as a secret. Parsed as text because PyYAML
is not a dependency.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
RELEASE = WORKFLOWS / "release.yml"
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


def test_only_the_publish_job_can_mint_an_oidc_token():
    # id-token: write lets a job prove it is this workflow to PyPI; any other
    # job holding it could publish too.
    holders = [name for name in ("build", "publish", "docker-publish") if "id-token: write" in _job(name)]
    assert holders == ["publish"]
    assert "id-token: write" in _header(_job("publish"))
    assert TEXT.count("id-token:") == 1


def test_no_workflow_mentions_a_pypi_token():
    for workflow in WORKFLOWS.glob("*.yml"):
        assert "PYPI_API_TOKEN" not in workflow.read_text(), workflow.name


def test_publish_step_is_the_pinned_pypa_action():
    job = _job("publish")
    assert "environment: pypi" in _header(job)
    uploads = [step for step in _steps(job) if "pypa/gh-action-pypi-publish@" in step]
    assert len(uploads) == 1
    assert re.search(r"uses: pypa/gh-action-pypi-publish@[0-9a-f]{40} # v\d+\.\d+\.\d+$", uploads[0], re.MULTILINE)
    # Attestations are on by default; turning them off would drop provenance.
    assert "attestations: false" not in job
    assert "twine" not in job


def test_jobs_have_no_env_block():
    for name in ("build", "publish", "docker-publish"):
        assert not re.search(r"^    env:", _header(_job(name)), re.MULTILINE)


def test_distributions_are_attached_to_the_release():
    job = _job("publish")
    assert "contents: write" in _header(job)
    # Not dist/*: the publish step leaves .publish.attestation files there.
    assert 'gh release upload "$GITHUB_REF_NAME" dist/*.whl dist/*.tar.gz ' in job


def test_docker_image_is_never_tagged_latest():
    job = _job("docker-publish")
    assert "drumsergio/wayback-archive:$VERSION" in job
    assert ":latest" not in job
    secrets_check = _steps(job)[0]
    assert "DOCKERHUB_TOKEN" in secrets_check and "exit 1" in secrets_check


def _image_tags(version, tmp_path):
    """Run the docker-publish tag step's script for one version."""
    step = next(s for s in _steps(_job("docker-publish")) if "id: tags" in s)
    script = "\n".join(line[8:] for line in step.split("run: |\n", 1)[1].splitlines())
    out = tmp_path / f"output-{version}"
    env = {"VERSION": version, "GITHUB_OUTPUT": str(out), "PATH": "/usr/bin:/bin"}
    subprocess.run(["bash", "-c", script], check=True, env=env)
    return out.read_text().strip().split("=", 1)[1].split(",")


@pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="runs the job's bash script; Windows launches System32's WSL bash before any PATH entry",
)
def test_minor_tag_moves_only_for_a_final_release(tmp_path):
    # A prerelease such as 1.6.0rc1 must not move :1.6 off the last final release.
    assert _image_tags("1.6.0", tmp_path) == [
        "drumsergio/wayback-archive:1.6.0",
        "drumsergio/wayback-archive:1.6",
    ]
    assert _image_tags("1.6.0rc1", tmp_path) == ["drumsergio/wayback-archive:1.6.0rc1"]
