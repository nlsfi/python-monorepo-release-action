# Copyright (c) 2026 National Land Survey of Finland
# (https://www.maanmittauslaitos.fi/en).
# This file is part of the Python Monorepo Release Action.
# Licensed under the MIT License; see the repository LICENSE file.

from pathlib import Path

from pytest_mock import MockerFixture

from monorepo_release import release


def make_workspace(tmp_path: Path) -> Path:
    for directory, name, dependencies in [("lib", "lib", ""), ("app", "app", "lib")]:
        (tmp_path / directory).mkdir()
        (tmp_path / directory / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\ndependencies = ["{dependencies}>=0.1"]\n'
            if dependencies
            else f'[project]\nname = "{name}"\n'
        )
    return tmp_path


def test_release_component_released_publishes_and_commits_dependents(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    components_dir = make_workspace(tmp_path)
    (components_dir / "lib" / "dist").mkdir()
    (components_dir / "lib" / "dist" / "lib-0.2.0.tar.gz").touch()
    mocker.patch.object(
        release,
        "semantic_release",
        return_value={"released": "true", "version": "0.2.0"},
    )
    run = mocker.patch.object(release, "run")

    version = release.release_component(components_dir, "lib", dry_run=False)

    assert version == "0.2.0"
    commands = [call.args[0][:2] for call in run.call_args_list]
    assert commands == [
        ["uv", "publish"],
        ["uv", "lock"],
        ["git", "add"],
        ["git", "commit"],
        ["git", "push"],
    ]
    assert (
        '"lib>=0.2.0,<0.3"' in (components_dir / "app" / "pyproject.toml").read_text()
    )


def test_release_component_dry_run_does_not_commit_or_push(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    components_dir = make_workspace(tmp_path)
    (components_dir / "lib" / "dist").mkdir()
    (components_dir / "lib" / "dist" / "lib-0.2.0.tar.gz").touch()
    mocker.patch.object(
        release,
        "semantic_release",
        return_value={"released": "true", "version": "0.2.0"},
    )
    run = mocker.patch.object(release, "run")

    release.release_component(components_dir, "lib", dry_run=True)

    commands = [call.args[0][:2] for call in run.call_args_list]
    assert commands == [["uv", "publish"], ["uv", "lock"], ["git", "reset"]]
    assert "--dry-run" in run.call_args_list[0].args[0]


def test_release_component_never_released_does_nothing(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    mocker.patch.object(release, "semantic_release", return_value={"released": "false"})
    mocker.patch.object(release, "last_released", return_value=None)
    run = mocker.patch.object(release, "run")

    assert (
        release.release_component(make_workspace(tmp_path), "lib", dry_run=False)
        is None
    )
    run.assert_not_called()


def test_release_component_unpublished_tag_is_published_and_dependents_bumped(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    components_dir = make_workspace(tmp_path)
    mocker.patch.object(release, "semantic_release", return_value={"released": "false"})
    mocker.patch.object(release, "last_released", return_value=("0.2.0", "lib-v0.2.0"))
    mocker.patch.object(release, "published_versions", return_value={"0.1.0"})
    publish_missing = mocker.patch.object(release, "publish_missing_release")
    run = mocker.patch.object(release, "run")

    version = release.release_component(components_dir, "lib", dry_run=False)

    assert version is None
    publish_missing.assert_called_once()
    assert publish_missing.call_args.args[:3] == (components_dir, "lib", "lib-v0.2.0")
    assert [call.args[0][:2] for call in run.call_args_list][:2] == [
        ["uv", "lock"],
        ["git", "add"],
    ]
    assert (
        '"lib>=0.2.0,<0.3"' in (components_dir / "app" / "pyproject.toml").read_text()
    )


def test_release_component_published_and_bumped_tag_changes_nothing(
    tmp_path: Path, mocker: MockerFixture
) -> None:
    components_dir = make_workspace(tmp_path)
    (components_dir / "app" / "pyproject.toml").write_text(
        '[project]\nname = "app"\ndependencies = ["lib>=0.2.0,<0.3"]\n'
    )
    mocker.patch.object(release, "semantic_release", return_value={"released": "false"})
    mocker.patch.object(release, "last_released", return_value=("0.2.0", "lib-v0.2.0"))
    mocker.patch.object(release, "published_versions", return_value={"0.2.0"})
    publish_missing = mocker.patch.object(release, "publish_missing_release")
    run = mocker.patch.object(release, "run")

    release.release_component(components_dir, "lib", dry_run=False)

    publish_missing.assert_not_called()
    run.assert_not_called()
