# Copyright (c) 2026 National Land Survey of Finland
# (https://www.maanmittauslaitos.fi/en).
# This file is part of the Python Monorepo Release Action.
# Licensed under the MIT License; see the repository LICENSE file.

import subprocess
import sys
from pathlib import Path

import pytest

from monorepo_release.bump_dependents import (
    bump_requirements,
    update_requirement,
    version_range,
)


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("1.2.3", ">=1.2.3,<2"),
        ("0.4.2", ">=0.4.2,<0.5"),
    ],
)
def test_version_range_stable_release_uses_next_compatible_bound(
    version: str, expected: str
) -> None:
    assert version_range(version) == expected


def test_bump_requirements_matching_dependency_preserves_extras_and_marker() -> None:
    text = (
        "[project]\n"
        "dependencies = [\n"
        '    "Pinta_DB[psycopg]>=0.1; python_version < \\"3.13\\"",\n'
        '    "other-package>=1",\n'
        "]\n"
    )

    updated = bump_requirements(text, "pinta-db", "0.2.1")

    assert '"Pinta_DB[psycopg]>=0.2.1,<0.3; python_version < \\"3.13\\""' in updated
    assert '"other-package>=1"' in updated


def test_bump_requirements_only_updates_dependency_tables() -> None:
    text = (
        "[project]\n"
        'name = "consumer"\n'
        'dependencies = ["pinta-lib>=0.1"]\n'
        "[tool.example]\n"
        'dependencies = ["pinta-lib>=0.1"]\n'
        "[project.optional-dependencies]\n"
        'test = ["pinta-lib>=0.1"]\n'
    )

    updated = bump_requirements(text, "pinta-lib", "0.2.0")

    assert updated.count('"pinta-lib>=0.2.0,<0.3"') == 2
    assert '[tool.example]\ndependencies = ["pinta-lib>=0.1"]' in updated


def test_bump_dependents_updates_matching_component_and_prints_its_name(
    tmp_path: Path,
) -> None:
    components_dir = tmp_path / "packages"
    library_dir = components_dir / "lib"
    consumer_dir = components_dir / "consumer"
    library_dir.mkdir(parents=True)
    consumer_dir.mkdir()
    (library_dir / "pyproject.toml").write_text('[project]\nname = "sample-lib"\n')
    (consumer_dir / "pyproject.toml").write_text(
        '[project]\nname = "consumer"\ndependencies = ["sample_lib>=0.1"]\n'
    )
    script = (
        Path(__file__).parents[1] / "src" / "monorepo_release" / "bump_dependents.py"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "lib",
            "0.2.0",
            "--components-dir",
            str(components_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout == "consumer\n"
    assert (
        'dependencies = ["sample_lib>=0.2.0,<0.3"]'
        in (consumer_dir / "pyproject.toml").read_text()
    )


@pytest.mark.parametrize(
    ("requirement", "expected"),
    [
        ("lib>=0.1", "lib>=0.2.0,<0.3"),
        ("lib>=0.1,<1", "lib>=0.2.0,<0.3"),
        ("lib>=0.2.0,<0.3", "lib>=0.2.0,<0.3"),
        ("lib>=0.2.1", "lib>=0.2.1"),
        ("lib<1", "lib<1"),
        ("lib", "lib"),
        ("other>=0.1", "other>=0.1"),
    ],
)
def test_update_requirement_only_raise_never_lowers_or_rewrites_unbounded(
    requirement: str, expected: str
) -> None:
    assert update_requirement(requirement, "lib", "0.2.0", only_raise=True) == expected
