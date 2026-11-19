# Copyright (c) 2026 National Land Survey of Finland
# (https://www.maanmittauslaitos.fi/en).
# This file is part of the Python Monorepo Release Action.
# Licensed under the MIT License; see the repository LICENSE file.

"""Raise version requirements of components that depend on a released component."""

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

KEY_PATTERN = re.compile(r"^([A-Za-z0-9_-]+)\s*=")
STRING_PATTERN = re.compile(r'"((?:\\.|[^"\\])*)"')
REQUIREMENT_NAME_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)(\[[^\]]*\])?(.*)$")
VERSION_PATTERN = re.compile(r"^(\d+)\.(\d+)")


def normalize(name: str) -> str:
    """Return a PEP 503 normalized package name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def version_range(version: str) -> str:
    """Return a lower bound and the next compatible major or minor bound."""
    match = VERSION_PATTERN.match(version)
    if match is None:
        raise ValueError(version)
    major, minor = (int(part) for part in match.groups())
    upper = f"{major + 1}" if major else f"0.{minor + 1}"
    return f">={version},<{upper}"


def update_requirement(value: str, dependency: str, version: str) -> str:
    """Update a matching requirement while preserving extras and environment markers."""
    marker_index = value.find(";")
    requirement, marker = (
        (value[:marker_index].rstrip(), value[marker_index:])
        if marker_index >= 0
        else (value, "")
    )
    match = REQUIREMENT_NAME_PATTERN.fullmatch(requirement.strip())
    if match is None or normalize(match.group(1)) != dependency:
        return value

    name, extras, specifier = match.groups()
    if specifier and not re.match(r"\s*[<>=!~]", specifier):
        return value
    return f"{name}{extras or ''}{version_range(version)}{marker}"


def bump_requirements(text: str, dependency: str, version: str) -> str:
    """Update dependency requirements in project dependencies and optional groups."""
    table = key = ""
    updated_lines = []
    for line in text.splitlines(keepends=True):
        if line.startswith("["):
            table, key = line.strip(), ""
        elif found := KEY_PATTERN.match(line):
            key = found.group(1)

        is_dependency = (table, key) == ("[project]", "dependencies") or (
            table == "[project.optional-dependencies]" and bool(key)
        )
        if not is_dependency:
            updated_lines.append(line)
            continue

        def replace(match: re.Match[str]) -> str:
            value = tomllib.loads(f'value = "{match.group(1)}"')["value"]
            updated = update_requirement(value, dependency, version)
            return json.dumps(updated, ensure_ascii=False)

        updated_lines.append(STRING_PATTERN.sub(replace, line))
    return "".join(updated_lines)


def component_package_name(component_dir: Path) -> str:
    """Read and normalize the package name from a component's pyproject.toml."""
    with (component_dir / "pyproject.toml").open("rb") as file:
        return normalize(tomllib.load(file)["project"]["name"])


def bump_dependents(components_dir: Path, component: str, version: str) -> list[str]:
    """Update dependent components and return their names relative to components_dir."""
    components_dir = components_dir.resolve()
    component_dir = (components_dir / component).resolve()
    component_is_outside = not component_dir.is_relative_to(components_dir)
    if component_is_outside or component_dir == components_dir:
        msg = "component must be a directory inside components_dir"
        raise ValueError(msg)

    dependency = component_package_name(component_dir)
    dependents = []
    for path in sorted(components_dir.glob("*/pyproject.toml")):
        if path.parent.resolve() == component_dir:
            continue
        text = path.read_text()
        updated = bump_requirements(text, dependency, version)
        if updated != text:
            path.write_text(updated)
            dependents.append(path.parent.relative_to(components_dir).as_posix())
    return dependents


def main() -> None:
    """Update dependent components and print their paths relative to components_dir."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", help="Released component directory name.")
    parser.add_argument("version", help="Released version.")
    parser.add_argument(
        "--components-dir",
        type=Path,
        default=Path("components"),
        help="Directory containing component directories.",
    )
    args = parser.parse_args()

    try:
        dependents = bump_dependents(args.components_dir, args.component, args.version)
    except ValueError as error:
        parser.error(str(error))
    for dependent in dependents:
        sys.stdout.write(f"{dependent}\n")


if __name__ == "__main__":
    main()
