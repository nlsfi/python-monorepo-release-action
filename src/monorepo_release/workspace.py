# Copyright (c) 2026 National Land Survey of Finland
# (https://www.maanmittauslaitos.fi/en).
# This file is part of the Python Monorepo Release Action.
# Licensed under the MIT License; see the repository LICENSE file.

"""Discover workspace components and order them by their dependencies."""

import tomllib
from graphlib import TopologicalSorter
from pathlib import Path

from monorepo_release.bump_dependents import REQUIREMENT_NAME_PATTERN, normalize


def _requirement_names(project: dict, groups: dict) -> set[str]:
    requirements = list(project.get("dependencies", []))
    for optional in project.get("optional-dependencies", {}).values():
        requirements.extend(optional)
    for group in groups.values():
        requirements.extend(item for item in group if isinstance(item, str))

    names = set()
    for requirement in requirements:
        match = REQUIREMENT_NAME_PATTERN.match(requirement.split(";")[0].strip())
        if match is not None:
            names.add(normalize(match.group(1)))
    return names


def release_order(components_dir: Path) -> list[str]:
    """Return component names so that dependencies precede their dependents."""
    packages = {}
    requirements = {}
    for path in sorted(components_dir.glob("*/pyproject.toml")):
        with path.open("rb") as file:
            data = tomllib.load(file)
        if "name" not in data.get("project", {}):
            continue
        packages[normalize(data["project"]["name"])] = path.parent.name
        requirements[path.parent.name] = _requirement_names(
            data["project"], data.get("dependency-groups", {})
        )

    sorter = TopologicalSorter()
    for component, names in requirements.items():
        sorter.add(component, *(packages[name] for name in names if name in packages))
    return list(sorter.static_order())
