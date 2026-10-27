# Contributing

Bug reports and pull requests are welcome. For a security problem, follow
[SECURITY.md](SECURITY.md) instead of opening an issue.

## Set up

```bash
git clone https://github.com/GeiserX/Wayback-Archive.git
cd Wayback-Archive
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r config/requirements-dev.txt
pip install -e .
```

Python 3.10 or newer.

## Before you push

CI runs exactly these, and a pull request merges only when they pass:

```bash
ruff check wayback_archive tests
ruff format wayback_archive tests
pytest tests/ -q
```

The tests never touch the network: a guard in `tests/conftest.py` refuses any
connection that is not to localhost, so a test that needs a response mocks it.
CI also fails when coverage drops below 85%.

To build the image the release publishes: `docker build -t wayback-archive .`

## Docs

The site under `docs/` is MkDocs in strict mode, so a broken link or a page
missing from the navigation fails the build:

```bash
pip install -r docs/requirements-docs.txt
mkdocs serve
```

## Cutting a release

1. Set `__version__` in `wayback_archive/__init__.py` to the new version.
2. Move the `[Unreleased]` entries in `CHANGELOG.md` under the new version and date.
3. Merge that to `main`, then tag it: `git tag vX.Y.Z && git push origin vX.Y.Z`.
4. Optional dry run: `gh workflow run release.yml --ref vX.Y.Z` builds and checks the package without publishing it.
5. Publish a GitHub release for the tag. The release workflow checks that the tag matches `__version__`, publishes to PyPI, attaches the wheel and sdist to the release, and pushes the Docker image.

Publishing needs the repository secrets `PYPI_API_TOKEN`, `DOCKERHUB_USERNAME`
and `DOCKERHUB_TOKEN`; without them the release fails rather than skipping a step.
