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
import urllib.error
import urllib.request
from pathlib import Path

from monorepo_release.bump_dependents import bump_dependents, component_package_name
from monorepo_release.workspace import release_order

logger = logging.getLogger(__name__)

DEFAULT_CHECK_URL = "https://pypi.org/simple/"
HTTP_NOT_FOUND = 404


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


def last_released(component_dir: Path) -> tuple[str, str] | None:
    """Return the last released version and its tag, if any."""
    results = []
    for option in ("--print-last-released", "--print-last-released-tag"):
        command = [sys.executable, "-m", "semantic_release", "version", option]
        result = subprocess.run(  # noqa: S603
            command, cwd=component_dir, check=False, capture_output=True, text=True
        )
        value = result.stdout.strip()
        if result.returncode != 0 or not value:
            return None
        results.append(value.splitlines()[-1])
    return results[0], results[1]


def published_versions(check_url: str, package: str) -> set[str]:
    """Return the versions of a package published to a PEP 691 / 700 index."""
    url = f"{check_url.rstrip('/')}/{package}/"
    request = urllib.request.Request(  # noqa: S310
        url, headers={"Accept": "application/vnd.pypi.simple.v1+json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return set(json.load(response).get("versions", []))
    except urllib.error.HTTPError as error:
        if error.code == HTTP_NOT_FOUND:
            return set()
        raise


def publish(component_dir: Path, check_url: str, *, dry_run: bool) -> None:
    """Publish the built distributions of a component, skipping uploaded files."""
    dist_dir = component_dir / "dist"
    distributions = sorted([*dist_dir.glob("*.whl"), *dist_dir.glob("*.tar.gz")])
    if not distributions:
        msg = f"No distributions found in {component_dir / 'dist'}"
        raise SystemExit(msg)
    command = ["uv", "publish", "--check-url", check_url]
    if dry_run:
        command.append("--dry-run")
    run([*command, *(str(path) for path in distributions)], cwd=component_dir)


def publish_missing_release(
    components_dir: Path, component: str, tag: str, check_url: str, *, dry_run: bool
) -> None:
    """Build and publish a tagged release that was never published.

    Recovers from a run that pushed the release tag but failed before publishing.
    """
    root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    relative = (components_dir / component).relative_to(root)
    with tempfile.TemporaryDirectory() as tmp:
        worktree = Path(tmp) / "worktree"
        run(["git", "worktree", "add", "--detach", str(worktree), tag])
        try:
            component_dir = worktree / relative
            run(["uv", "build", "--out-dir", "dist"], cwd=component_dir)
            publish(component_dir, check_url, dry_run=dry_run)
        finally:
            run(["git", "worktree", "remove", "--force", str(worktree)])


def raise_dependent_requirements(
    components_dir: Path,
    component: str,
    version: str,
    *,
    only_raise: bool,
    dry_run: bool,
) -> None:
    """Raise the requirements of dependents, then lock and commit the changes."""
    dependents = bump_dependents(
        components_dir, component, version, only_raise=only_raise
    )
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
    components_dir: Path,
    component: str,
    check_url: str = DEFAULT_CHECK_URL,
    *,
    dry_run: bool,
) -> str | None:
    """Release one component and bring its publication and dependents up to date.

    Every step is derived from the repository and index state instead of only from
    this run's release, so a run that failed halfway is completed by running again.
    Return the version released by this run, if any.
    """
    component_dir = components_dir / component
    outputs = semantic_release(component_dir, dry_run=dry_run)
    released = outputs.get("released") == "true"

    if released:
        version = outputs["version"]
        publish(component_dir, check_url, dry_run=dry_run)
    else:
        previous = last_released(component_dir)
        if previous is None:
            logger.info("No release for %s.", component)
            return None
        version, tag = previous
        package = component_package_name(component_dir)
        if version not in published_versions(check_url, package):
            logger.info("Publishing unpublished release %s of %s.", tag, component)
            publish_missing_release(
                components_dir, component, tag, check_url, dry_run=dry_run
            )

    raise_dependent_requirements(
        components_dir, component, version, only_raise=not released, dry_run=dry_run
    )
    if dry_run:
        run(["git", "reset", "--hard", "HEAD"])
    return version if released else None


def main() -> None:
    """Release the given components, or all components in dependency order."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "components",
        help='Newline or comma separated component names, or "auto" for all.',
    )
    parser.add_argument("--components-dir", type=Path, default=Path("components"))
    parser.add_argument("--check-url", default=DEFAULT_CHECK_URL)
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
            args.components_dir, component, args.check_url, dry_run=args.dry_run
        )
        if version is not None:
            releases[component] = version

    if output_file := os.environ.get("GITHUB_OUTPUT"):
        with Path(output_file).open("a") as file:
            file.write(f"released={str(bool(releases)).lower()}\n")
            file.write(f"releases={json.dumps(releases)}\n")


if __name__ == "__main__":
    main()
