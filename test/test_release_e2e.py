# Copyright (c) 2026 National Land Survey of Finland
# (https://www.maanmittauslaitos.fi/en).
# This file is part of the Python Monorepo Release Action.
# Licensed under the MIT License; see the repository LICENSE file.

"""End-to-end release of a fixture workspace with real git, uv and semantic-release."""

import json
import shutil
import sys
import tomllib
from pathlib import Path

import pytest
from fixture_workspace import create_workspace, git

from monorepo_release import release

pytestmark = pytest.mark.skipif(
    shutil.which("uv") is None or shutil.which("git") is None,
    reason="uv and git are required",
)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    git_config = tmp_path / "gitconfig"
    git_config.write_text("[user]\n\tname = test\n\temail = test@example.com\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(git_config))
    monkeypatch.setenv("GH_TOKEN", "unused")

    repo = tmp_path / "repo"
    create_workspace(repo, tmp_path / "origin.git")
    monkeypatch.chdir(repo)
    return repo


def remote_head(repo: Path) -> str:
    return git(repo, "ls-remote", "origin", "refs/heads/main").split()[0]


def run_release(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *extra: str
) -> dict[str, str]:
    output_file = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
    monkeypatch.setattr(release, "publish", lambda *_, **__: None)
    monkeypatch.setattr(sys, "argv", ["release", "auto", *extra])
    release.main()
    return dict(line.split("=", 1) for line in output_file.read_text().splitlines())


def test_main_auto_releases_components_in_dependency_order_and_pushes(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = run_release(monkeypatch, tmp_path)

    assert outputs["released"] == "true"
    assert json.loads(outputs["releases"]) == {"lib": "0.2.0", "app": "0.1.1"}
    app_pyproject = tomllib.loads((repo / "components/app/pyproject.toml").read_text())
    assert app_pyproject["project"]["dependencies"] == ["lib>=0.2.0,<0.3"]
    assert 'name = "lib"\nversion = "0.2.0"' in (repo / "uv.lock").read_text()
    assert git(repo, "status", "--porcelain") == ""
    assert git(repo, "rev-parse", "HEAD") == remote_head(repo)
    assert {"lib-v0.2.0", "app-v0.1.1"} <= set(git(repo, "tag").split())


def test_main_dry_run_leaves_repository_untouched(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    head = git(repo, "rev-parse", "HEAD")

    outputs = run_release(monkeypatch, tmp_path, "--dry-run")

    assert json.loads(outputs["releases"]) == {"lib": "0.2.0"}
    assert git(repo, "rev-parse", "HEAD") == head
    assert git(repo, "status", "--porcelain") == ""
    assert remote_head(repo) != head
    assert "lib-v0.2.0" not in git(repo, "tag").split()
