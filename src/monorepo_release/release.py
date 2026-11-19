# Copyright (c) 2026 National Land Survey of Finland
# (https://www.maanmittauslaitos.fi/en).
# This file is part of the Python Monorepo Release Action.
# Licensed under the MIT License; see the repository LICENSE file.

"""Release components of a uv workspace in dependency order."""

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from monorepo_release.bump_dependents import bump_dependents
from monorepo_release.workspace import release_order

logger = logging.getLogger(__name__)


def run(
    command: list[str], cwd: Path | None = None, env: dict[str, str] | None = None
) -> None:
    """Run a command and fail if it fails."""
    logger.info("$ %s", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True, env=env)  # noqa: S603


def semantic_release(component_dir: Path, *, dry_run: bool) -> dict[str, str]:
    """Run python-semantic-release and return its GitHub Actions outputs."""
    command = [sys.executable, "-m", "semantic_release", "version", "--no-vcs-release"]
    if dry_run:
        command += ["--no-commit", "--no-tag", "--no-push"]
    with tempfile.TemporaryDirectory() as tmp:
        output_file = Path(tmp) / "output"
        output_file.touch()
        env = {**os.environ, "GITHUB_OUTPUT": str(output_file)}
        run(command, cwd=component_dir, env=env)
        lines = output_file.read_text().splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line)


def publish(component_dir: Path, *, dry_run: bool) -> None:
    """Publish the built distributions of a component."""
    distributions = sorted((component_dir / "dist").glob("*"))
    if not distributions:
        msg = f"No distributions found in {component_dir / 'dist'}"
        raise SystemExit(msg)
    command = ["uv", "publish", *(["--dry-run"] if dry_run else [])]
    run([*command, *(str(path) for path in distributions)], cwd=component_dir)


def raise_dependent_requirements(
    components_dir: Path, component: str, version: str, *, dry_run: bool
) -> None:
    """Raise the requirements of dependents, then lock and commit the changes."""
    dependents = bump_dependents(components_dir, component, version)
    if not dependents:
        logger.info("No dependent requirements to update.")
        return

    run(["uv", "lock"])
    if dry_run:
        for dependent in dependents:
            logger.info("Would update dependent: %s", dependent)
        return

    run(
        [
            "git",
            "add",
            "uv.lock",
            *(f"{components_dir}/{d}/pyproject.toml" for d in dependents),
        ]
    )
    run(
        [
            "git",
            "commit",
            "-m",
            f"build(deps): require {component} >={version} in dependents",
        ]
    )
    run(["git", "push", "origin", "HEAD"])


def release_component(
    components_dir: Path, component: str, *, dry_run: bool
) -> str | None:
    """Release one component and return the released version, if any."""
    component_dir = components_dir / component
    outputs = semantic_release(component_dir, dry_run=dry_run)
    if outputs.get("released") != "true":
        logger.info("No release for %s.", component)
        return None

    version = outputs["version"]
    publish(component_dir, dry_run=dry_run)
    raise_dependent_requirements(components_dir, component, version, dry_run=dry_run)
    if dry_run:
        run(["git", "reset", "--hard", "HEAD"])
    return version


def main() -> None:
    """Release the given components, or all components in dependency order."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "components",
        help='Newline or comma separated component names, or "auto" for all.',
    )
    parser.add_argument("--components-dir", type=Path, default=Path("components"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args.components_dir = args.components_dir.resolve()
    if args.components.strip() == "auto":
        components = release_order(args.components_dir)
    else:
        components = args.components.replace(",", "\n").split()
    logger.info("Release order: %s", ", ".join(components))

    run(["git", "config", "--global", "user.name", "semantic-release"])
    run(["git", "config", "--global", "user.email", "semantic-release"])

    releases = {}
    for component in components:
        version = release_component(
            args.components_dir, component, dry_run=args.dry_run
        )
        if version is not None:
            releases[component] = version

    if output_file := os.environ.get("GITHUB_OUTPUT"):
        with Path(output_file).open("a") as file:
            file.write(f"released={str(bool(releases)).lower()}\n")
            file.write(f"releases={json.dumps(releases)}\n")


if __name__ == "__main__":
    main()
