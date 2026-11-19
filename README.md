# python-monorepo-release-action

GitHub action for releasing the packages of a python `uv` workspace monorepo.

The action releases the components in dependency order. For each component it:

1. Runs [python-semantic-release](https://python-semantic-release.readthedocs.io/)
   to determine the release version, update the version metadata and changelog,
   and build the distributions. The release commit and tag are pushed.
2. Publishes the distributions of the component to PyPI with `uv publish`.
3. Raises the version requirements of the workspace packages depending on the
   released component, runs `uv lock`, and commits and pushes the changes
   (`build(deps): require <component> >=<version> in dependents`).

Components without releasable changes are skipped. Container image builds and
other repository-specific steps should remain in the calling repository.

## Requirements

- Python Semantic Release is configured for each component in its
  `pyproject.toml`. Its `build_command` must place the distributions in the
  `dist` directory of the component, e.g. `uv build --out-dir dist`.
- The raised requirements are committed as `build(deps)`. For the dependents to
  be released by them, configure the commit parser to treat `build` as a patch
  tag, e.g. `patch_tags = ["fix", "perf", "build"]` in
  `[tool.semantic_release.commit_parser_options]`. Use a monorepo-aware parser
  such as `conventional-monorepo` to release a component only for changes in
  its own directory.
- A `uv.lock` exists at the repository root.
- Each component directory has a `pyproject.toml` with a `[project].name`.
- The workflow checks out the full Git history and has `contents: write` and
  `id-token: write` permissions. The latter is required for PyPI trusted
  publishing; configure the GitHub repository as a PyPI publisher.
- Release runs must not be concurrent, e.g. use a `concurrency` group.

## Usage

```yaml
name: Release

on:
  workflow_dispatch:

concurrency:
  group: release
  cancel-in-progress: false

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      id-token: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0
      - uses: nlsfi/python-monorepo-release-action@v1
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
```

By default (`components: auto`) all components are released ordered so that
the dependencies of a component are released before it. The dependencies are
read from `[project].dependencies`, `[project.optional-dependencies]` and
`[dependency-groups]` of the components. A dependency cycle is an error.

To release only some components, or in a custom order, list them one per line:

```yaml
      - uses: nlsfi/python-monorepo-release-action@v1
        with:
          components: |
            lib
            db
          github_token: ${{ secrets.GITHUB_TOKEN }}
```

### Inputs

| Name             | Required | Default      | Description                                                                         |
| ---------------- | -------- | ------------ | ----------------------------------------------------------------------------------- |
| `components`     | no       | `auto`       | Component directory names, one per line, or `auto` to order all by dependencies     |
| `components_dir` | no       | `components` | Directory containing the component directories                                      |
| `github_token`   | yes      |              | Token used to push release commits and tags                                         |
| `dry_run`        | no       | `false`      | Build and validate without committing, tagging, pushing, or publishing              |

### Outputs

| Name       | Description                                                      |
| ---------- | ---------------------------------------------------------------- |
| `released` | `"true"` if any component was or would be released               |
| `releases` | JSON object mapping released component names to their versions   |

## Dry run

With `dry_run: true` nothing is committed, tagged, pushed or published. The
version metadata is still updated in the temporary runner workspace and the
configured build command is run, followed by `uv publish --dry-run`. Dependent
requirements are updated and `uv lock` is run, but the changes are not
committed. The workspace is reset after each component, so a dry run should
only be run on a disposable checkout such as a CI runner.

## Version requirements

When a component is released, requirements matching its normalized package name
in `[project].dependencies` and `[project.optional-dependencies]` are updated.
Extras and environment markers are preserved. The new lower bound is the
released version; the upper bound is the next major version, or the next minor
version for `0.x` releases. All changed dependents and `uv.lock` are committed
together, so the dependents' own release configuration can detect the change.

## Scripts

The scripts in `src/monorepo_release` can also be used directly:

```shell
python -m monorepo_release.release <auto|components> [--components-dir <dir>] [--dry-run]
python -m monorepo_release.bump_dependents <component> <version> [--components-dir <dir>]
```

`bump_dependents` updates the dependents and prints their directory names, one
per line.

## Development

```shell
uv sync
uv run prek install
uv run pytest
```

The tests include an end-to-end test (`test/test_release_e2e.py`) that releases
a fixture workspace with real git, uv and python-semantic-release against a
local bare repository, with only the PyPI upload mocked. It needs network access
to build the fixture packages. The CI `action-dry-run` job runs the action itself
with `dry_run: true` on the same fixture (`test/fixture_workspace.py`).
