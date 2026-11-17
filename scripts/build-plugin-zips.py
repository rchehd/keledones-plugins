#!/usr/bin/env python3
"""Build one installable ZIP per plugin from the checked-out Git commit."""

import argparse
import io
import json
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parent.parent
MANIFESTS = (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", ".cursor-plugin/plugin.json")
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
VERSION = re.compile(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?(?:\+[A-Za-z0-9.-]+)?")


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def archive_name(archive, folder):
    paths = set(archive.namelist())
    identities = set()
    for manifest in MANIFESTS:
        path = f"{folder}/{manifest}"
        if path not in paths:
            continue
        data = json.loads(archive.read(path))
        name, version = data.get("name"), data.get("version")
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise ValueError(f"{path}: invalid plugin name")
        if not isinstance(version, str) or not VERSION.fullmatch(version):
            raise ValueError(f"{path}: invalid plugin version")
        identities.add((name, version))

    if len(identities) != 1:
        raise ValueError(f"{folder}: expected manifests with a single plugin name and version")
    name, version = identities.pop()
    return f"{name}-{version}.zip"


def validate_extracted(plugin):
    validator = plugin / "scripts/validate-package.py"
    if validator.is_file():
        subprocess.run([sys.executable, "-B", str(validator)], cwd=plugin, check=True)

    hooks = plugin / "hooks/hooks.json"
    if hooks.is_file():
        for module in json.loads(hooks.read_text(encoding="utf-8")).get("modules", []):
            if not (hooks.parent / module).is_file():
                raise ValueError(f"{plugin.name}: missing hook module {module}")


def build(root, output):
    commit = git(root, "rev-parse", "HEAD").decode().strip()
    entries = git(root, "ls-tree", "-d", "-z", "--name-only", f"{commit}:plugins").decode()
    folders = entries.rstrip("\0").split("\0") if entries else []
    if not folders:
        raise ValueError("No plugin folders in the checked-out commit")

    packages = {}
    with TemporaryDirectory() as directory:
        extracted = Path(directory)
        for folder in folders:
            content = git(root, "archive", "--format=zip", f"--prefix={folder}/", f"{commit}:plugins/{folder}",
                          "--", ".", ":(exclude)tests", ":(exclude).gitignore", ":(exclude).gitattributes")
            with ZipFile(io.BytesIO(content)) as archive:
                filename = archive_name(archive, folder)
                if filename in packages:
                    raise ValueError(f"Duplicate release asset {filename}")
                archive.extractall(extracted)
            validate_extracted(extracted / folder)
            packages[filename] = content

    output.mkdir(parents=True, exist_ok=True)
    for filename, content in packages.items():
        (output / filename).write_bytes(content)
    return sorted(packages)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        for filename in build(ROOT, args.output):
            print(f"Built {args.output / filename}")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Build failed: {error}\n")


if __name__ == "__main__":
    main()
