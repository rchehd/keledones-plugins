#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
from project import BASE, ensure_excluded, migrate, project_file, toplevel, write_json


def git_bytes(top, *args, stdin=None):
    try:
        result = subprocess.run(["git", "-C", str(top), *args], input=stdin, capture_output=True)
    except OSError as error:
        raise ValueError(f"git {args[0]} failed: {error}") from error

    if result.returncode != 0:
        raise ValueError(f"git {args[0]} failed: {result.stderr.decode(errors='replace').strip()}")

    return result.stdout


def raw_blob_id(content):
    return hashlib.sha1(b"blob %d\0" % len(content) + content, usedforsecurity=False).hexdigest().encode()


def blob_ids(top, names):
    ids, files = {}, []

    for name in names:
        path = top / os.fsdecode(name)

        try:
            if path.is_symlink():
                ids[name] = raw_blob_id(os.fsencode(os.readlink(path)))
            elif path.is_dir():
                ids[name] = git_bytes(path, "rev-parse", "HEAD").strip()
            elif b"\n" in name or name.startswith(b'"') or not os.access(path, os.R_OK):
                ids[name] = raw_blob_id(path.read_bytes())
            else:
                files.append(name)
        except (OSError, ValueError):
            ids[name] = b"unreadable"

    if files:
        # hash-object applies the same autocrlf and clean filters as staging, so staged content keeps its ID.
        hashed = git_bytes(top, "hash-object", "--stdin-paths", stdin=b"\n".join(files) + b"\n").split()
        ids.update(zip(files, hashed))

    return ids


def untracked_mode(top, name, trust_executable):
    mode = (top / os.fsdecode(name)).lstat().st_mode
    if stat.S_ISLNK(mode):
        return b"120000"
    if stat.S_ISDIR(mode):
        return b"160000"
    return b"100755" if trust_executable and mode & stat.S_IXUSR else b"100644"


def work_fingerprint(top):
    # Git modes and blob IDs stay stable when the same files are staged or committed.
    top = Path(top)
    entries = {}

    for row in git_bytes(top, "ls-files", "-s", "-z").split(b"\0"):
        if row:
            info, name = row.split(b"\t", 1)
            mode, blob, _ = info.split()
            entries[name] = entries.get(name, b"") + mode + b" " + blob

    diff = iter(git_bytes(top, "diff", "--raw", "--no-renames", "--no-ext-diff", "-z").split(b"\0")[:-1])
    modes = {name: info.split()[1] for info, name in zip(diff, diff)}
    untracked = git_bytes(top, "ls-files", "-z", "--others", "--exclude-standard").split(b"\0")[:-1]
    if untracked:
        trust_executable = git_bytes(top, "config", "--type=bool", "--default=true", "--get", "core.filemode").strip() == b"true"
        for name in untracked:
            try:
                modes[name] = untracked_mode(top, name, trust_executable)
            except FileNotFoundError:
                continue

    for name, mode in list(modes.items()):
        if mode == b"000000" or not os.path.lexists(top / os.fsdecode(name)):
            del modes[name]
            entries.pop(name, None)

    entries.update((name, modes[name] + b" " + blob) for name, blob in blob_ids(top, modes).items())

    digest = hashlib.sha256()

    for name in sorted(entries):
        digest.update(name + b"\0" + entries[name] + b"\0")

    return digest.hexdigest()


def marker(top):
    return Path(top) / BASE / "state" / "last-check.json"


def mark_checked(top):
    top = Path(top)
    migrate(top)
    ensure_excluded(top)
    data = dict(fingerprint=work_fingerprint(top), ts=datetime.now().isoformat(timespec="seconds"))
    write_json(marker(top), data, top)
    return data


def last_checked(top):
    try:
        data = json.loads(project_file(top, "state", "last-check.json").read_text(encoding="utf-8"))
        return data.get("fingerprint") if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def main():
    parser = argparse.ArgumentParser(description="Record that Ready Check reached a final result for the current code.")
    parser.add_argument("--project", type=Path, required=True)
    args = parser.parse_args()
    result = dict(schema_version=1, action="mark-checked", status="FAIL")

    try:
        top = toplevel(args.project)
        if not top:
            raise ValueError("mark-checked needs a Git work tree")

        result.update(status="PASS", **mark_checked(top))
    except (OSError, ValueError) as error:
        result["reason"] = str(error)

    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
