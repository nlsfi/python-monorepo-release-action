# Copyright (c) 2026 National Land Survey of Finland
# (https://www.maanmittauslaitos.fi/en).
# This file is part of the Python Monorepo Release Action.
# Licensed under the MIT License; see the repository LICENSE file.

"""Create a git repository with a uv workspace that has releasable changes.

The workspace has components "lib" and "app" (depending on "lib"), both tagged
at 0.1.0, and an unreleased `feat` commit touching only "lib".

Usage: python fixture_workspace.py <repository> <origin>
"""

import subprocess
import sys
from pathlib import Path

ROOT_PYPROJECT = """\
[project]
name = "root"
version = "0.0.0"
requires-python = ">=3.12"

[tool.uv.workspace]
members = ["components/*"]

[tool.uv.sources]
lib = { workspace = true }
"""

COMPONENT_PYPROJECT = """\
[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [{dependencies}]

[build-system]
requires = ["uv_build>=0.13.6,<0.14.0"]
build-backend = "uv_build"

[tool.semantic_release]
tag_format = "{name}-v{{version}}"
version_toml = ["pyproject.toml:project.version"]
build_command = "uv build --out-dir dist"
allow_zero_version = true
commit_parser = "conventional-monorepo"

[tool.semantic_release.branches.main]
match = "main"

[tool.semantic_release.commit_parser_options]
patch_tags = ["fix", "perf", "build"]

[tool.semantic_release.remote]
ignore_token_for_push = true
"""

IDENTITY = ["-c", "user.name=test", "-c", "user.email=test@example.com"]


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *IDENTITY, *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def add_component(repo: Path, name: str, dependencies: str = "") -> None:
    component = repo / "components" / name
    (component / "src" / name).mkdir(parents=True)
    (component / "src" / name / "__init__.py").touch()
    (component / "pyproject.toml").write_text(
        COMPONENT_PYPROJECT.format(name=name, dependencies=dependencies)
    )


def create_workspace(repo: Path, origin: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    origin.mkdir(parents=True, exist_ok=True)
    git(origin, "init", "--bare", "--initial-branch=main")
    git(repo, "init", "--initial-branch=main")
    git(repo, "remote", "add", "origin", str(origin))

    (repo / "pyproject.toml").write_text(ROOT_PYPROJECT)
    (repo / ".gitignore").write_text("dist/\n.venv/\naction/\n")
    # "app" sorts before "lib" alphabetically, so the order must come from deps.
    add_component(repo, "lib")
    add_component(repo, "app", '"lib>=0.1"')
    subprocess.run(["uv", "lock"], cwd=repo, check=True, capture_output=True)
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "chore: initial")
    git(repo, "tag", "lib-v0.1.0")
    git(repo, "tag", "app-v0.1.0")
    git(repo, "push", "origin", "HEAD:main", "--tags")
    git(repo, "branch", "--set-upstream-to=origin/main")

    (repo / "components" / "lib" / "feature.txt").write_text("feature")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "feat: add lib feature")


if __name__ == "__main__":
    create_workspace(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
