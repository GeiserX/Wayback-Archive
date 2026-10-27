# Development

## Set up

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r config/requirements-dev.txt
pip install -e .
```

## Lint and test

CI runs these on every pull request, and each one must pass:

```bash
ruff check wayback_archive tests
ruff format --check wayback_archive tests
mypy wayback_archive
pytest tests/ -q --cov=wayback_archive --cov-fail-under=85
```

`ruff format wayback_archive tests` rewrites files in place. The ruff and mypy settings live in `pyproject.toml`.

The tests never reach the network. An autouse guard in `tests/conftest.py` refuses every connection that is not to localhost, so a test that needs a response mocks it or serves it from a local server.

CI runs the suite on Python 3.10 to 3.14 on Linux, and on Python 3.13 on Windows and macOS. The Python versions in the CI matrix and the classifiers in `pyproject.toml` must match; `tests/test_packaging.py` fails when they do not.

## Docs

The site is MkDocs in strict mode: a broken link or a page missing from the navigation fails the build.

```bash
pip install -r docs/requirements-docs.txt
mkdocs serve
```

## Docker image

```bash
docker build -t wayback-archive .
docker run --rm -e WAYBACK_URL=... -v "$PWD/output:/output" wayback-archive
```

CI builds the image on every pull request and checks that it runs the CLI.

## Releases

Set `__version__` in `wayback_archive/__init__.py`, move the `[Unreleased]` entries of `CHANGELOG.md` under the new version, merge, tag `vX.Y.Z` and publish a GitHub release for the tag. The release workflow then:

1. checks that the tag matches `__version__`, builds the wheel and sdist, and installs the sdist in a clean environment;
2. publishes them to PyPI and attaches them to the GitHub release;
3. pushes `drumsergio/wayback-archive:X.Y.Z` and `:X.Y` to Docker Hub, for amd64 and arm64.

Running the workflow by hand on a tag (`gh workflow run release.yml --ref vX.Y.Z`) does step 1 only.

## Contributing

Pull requests are welcome; see `CONTRIBUTING.md` in the repository.
