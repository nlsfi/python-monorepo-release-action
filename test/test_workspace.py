# Copyright (c) 2026 National Land Survey of Finland
# (https://www.maanmittauslaitos.fi/en).
# This file is part of the Python Monorepo Release Action.
# Licensed under the MIT License; see the repository LICENSE file.

from pathlib import Path

import pytest

from monorepo_release.workspace import release_order


def write_component(root: Path, directory: str, name: str, body: str = "") -> None:
    (root / directory).mkdir(parents=True)
    (root / directory / "pyproject.toml").write_text(
        f'[project]\nname = "{name}"\n{body}'
    )


def test_release_order_places_dependencies_before_dependents(tmp_path: Path) -> None:
    write_component(
        tmp_path, "app", "app", 'dependencies = ["Pinta_DB[x]>=1; os_name=\\"nt\\""]\n'
    )
    write_component(tmp_path, "db", "pinta-db", 'dependencies = ["pinta-lib>=1"]\n')
    write_component(tmp_path, "lib", "pinta-lib", 'dependencies = ["requests"]\n')
    write_component(
        tmp_path,
        "tool",
        "tool",
        '[dependency-groups]\ndev = ["pinta-lib", {include-group = "x"}]\n',
    )

    order = release_order(tmp_path)

    assert order.index("lib") < order.index("db") < order.index("app")
    assert order.index("lib") < order.index("tool")


def test_release_order_dependency_cycle_raises(tmp_path: Path) -> None:
    write_component(tmp_path, "a", "a", 'dependencies = ["b"]\n')
    write_component(tmp_path, "b", "b", 'dependencies = ["a"]\n')

    with pytest.raises(Exception, match="cycle"):
        release_order(tmp_path)
