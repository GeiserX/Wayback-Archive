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
    # The `test` job's matrix is the only list-form python-version; the other
    # jobs pin one version. A second list would be ignored here, so refuse it.
    matches = re.findall(r"python-version:\s*\[([^\]]*)\]", CI)
    assert len(matches) == 1, matches
    return sorted(_version(v) for v in re.findall(r'"([\d.]+)"', matches[0]))


def test_requires_python_is_the_lowest_ci_version():
    # pip on a version below the floor falls back to an old release; on a
    # version above it but untested, it installs something CI never ran.
    floor = re.search(r'^requires-python = ">=([\d.]+)"', PYPROJECT, re.MULTILINE)
    assert _version(floor.group(1)) == _ci_matrix()[0]


def test_classifiers_list_exactly_the_ci_versions():
    listed = sorted(_version(v) for v in re.findall(r'"Programming Language :: Python :: (\d+\.\d+)"', PYPROJECT))
    assert listed == _ci_matrix()


def test_pytest_settings_are_loaded(pytestconfig):
    # pytest reads settings from pyproject.toml or a root-level ini file only;
    # a file under config/ is silently ignored.
    assert pytestconfig.inipath == ROOT / "pyproject.toml"
    assert pytestconfig.getini("testpaths") == ["tests"]


def test_every_action_is_pinned_to_a_commit():
    # A tag can be moved to other code after review; a commit SHA cannot.
    for workflow in (ROOT / ".github" / "workflows").glob("*.yml"):
        for ref in re.findall(r"^\s*(?:- )?uses:\s*(\S+)", workflow.read_text(), re.MULTILINE):
            assert re.search(r"@[0-9a-f]{40}$", ref), f"{workflow.name}: {ref}"


def test_coverage_has_a_floor():
    assert re.search(r"--cov-fail-under=\d+", CI)


def test_ci_gates_can_fail():
    # A step that swallows its own exit code reports green on any result.
    for fake in ("|| true", "--exit-zero", "continue-on-error"):
        assert fake not in CI


def test_codecov_gets_the_input_it_reads():
    # codecov-action v4+ reads `files`; `file` is ignored with a warning.
    assert re.search(r"^\s+files: \./coverage\.xml$", CI, re.MULTILINE)
    assert not re.search(r"^\s+file:", CI, re.MULTILINE)


def test_ci_installs_the_built_wheel_outside_the_checkout():
    assert "python -m build" in CI
    assert "pip install dist/*.whl" in CI
    assert "'site-packages' in" in CI
