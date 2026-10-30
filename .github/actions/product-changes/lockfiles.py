"""Resolve changed pnpm importer closures without installing dependencies."""

import subprocess

import yaml


def closure(lock, importer):
    result = {"importer": importer, "snapshots": {}, "packages": {}}
    pending = []
    for section in ("dependencies", "devDependencies", "optionalDependencies"):
        for name, dependency in importer.get(section, {}).items():
            pending.append((name, dependency["version"]))
    while pending:
        name, version = pending.pop()
        if version.startswith("link:"):
            continue
        key = version[4:] if version.startswith("npm:") else f"{name}@{version}"
        if key in result["snapshots"]:
            continue
        snapshot = lock["snapshots"][key]
        result["snapshots"][key] = snapshot
        package = key.split("(", 1)[0]
        result["packages"][package] = lock["packages"][package]
        for section in ("dependencies", "optionalDependencies"):
            pending.extend(snapshot.get(section, {}).items())
    return result


def changed_importers(before, after):
    if any(before.get(key) != after.get(key) for key in before.keys() | after.keys()
           if key not in ("importers", "packages", "snapshots")):
        return None
    importers = before["importers"].keys() | after["importers"].keys()
    try:
        return [name for name in sorted(importers)
                if name not in before["importers"] or name not in after["importers"]
                or closure(before, before["importers"][name]) != closure(after, after["importers"][name])]
    except (KeyError, TypeError, AttributeError):
        return None


def expand_lockfile(paths, base, root):
    if "product/pnpm-lock.yaml" not in paths or not base:
        return paths
    try:
        before = yaml.safe_load(subprocess.check_output(
            ["git", "show", f"{base}:product/pnpm-lock.yaml"], cwd=root, text=True,
            stderr=subprocess.DEVNULL))
        path = root / "product/pnpm-lock.yaml"
        after = yaml.safe_load(path.read_text() if path.exists() else subprocess.check_output(
            ["git", "show", "HEAD:product/pnpm-lock.yaml"], cwd=root, text=True))
        changed = changed_importers(before, after)
    except (subprocess.CalledProcessError, OSError, yaml.YAMLError):
        return paths
    if changed is None or "." in changed:
        return paths
    return [path for path in paths if path != "product/pnpm-lock.yaml"] + [
        f"product/{importer}/package.json" for importer in changed]


if __name__ == "__main__":
    import os
    import sys
    from pathlib import Path

    paths = sys.stdin.read().splitlines()
    print("\n".join(expand_lockfile(paths, os.environ.get("BASE"), Path.cwd())))
