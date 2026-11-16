#!/usr/bin/env python3
"""Set one new plugin version in the Claude Code, Codex and Cursor manifests."""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFESTS = (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", ".cursor-plugin/plugin.json")
SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
FIELD = re.compile(r'("version"\s*:\s*")([^"]*)(")')


def current(root):
    versions = {json.loads((root / name).read_text(encoding="utf-8")).get("version") for name in MANIFESTS}

    if len(versions) != 1:
        raise ValueError(f"Manifest versions differ: {', '.join(sorted(map(str, versions)))}")

    return versions.pop()


def key(version):
    match = SEMVER.fullmatch(version or "")

    if not match:
        raise ValueError(f"Not a release version X.Y.Z: {version}")

    return tuple(int(part) for part in match.groups())


def bump(root, version):
    old = current(root)

    if key(version) <= key(old):
        raise ValueError(f"New version {version} must be greater than {old}")

    for name in MANIFESTS:
        path = root / name
        text, count = FIELD.subn(lambda m: m[1] + version + m[3], path.read_text(encoding="utf-8"), count=1)

        if count != 1:
            raise ValueError(f"No version field in {name}")
        path.write_text(text, encoding="utf-8")

    return old


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="new version, for example 0.2.0")
    args = parser.parse_args()
    try:
        old = bump(ROOT, args.version)
    except (OSError, ValueError) as error:
        print(f"bump-version: {error}", file=sys.stderr)
        return 1

    print(f"Ready Check {old} -> {args.version} in {', '.join(MANIFESTS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
