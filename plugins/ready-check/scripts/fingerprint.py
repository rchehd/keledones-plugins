#!/usr/bin/env python3
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
from project import BASE, ensure_excluded, migrate, project_file, toplevel, write_json


def git_bytes(top, *args):
    result = subprocess.run(["git", "-C", str(top), *args], capture_output=True)
    return result.stdout if result.returncode == 0 else b""


def work_fingerprint(top):
    top = Path(top)
    digest = hashlib.sha256()

    plain = ("--no-ext-diff", "--no-textconv", "--no-color", "--binary")

    for args in (("rev-parse", "HEAD"), ("diff", *plain), ("diff", "--cached", *plain)):
        digest.update(git_bytes(top, *args) + b"\0")

    untracked = git_bytes(top, "ls-files", "-z", "--others", "--exclude-standard").split(b"\0")

    for name in sorted(item for item in untracked if item):
        path = top / name.decode("utf-8", "surrogateescape")

        try:
            info = path.stat()
            content = f"{info.st_size}:{info.st_mtime_ns}".encode()
        except OSError:
            content = b"missing"

        digest.update(name + b"\0" + content + b"\0")

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
