from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4

PLUGIN = Path(__file__).resolve().parent.parent
KNOWN = {"profile.json", "history.jsonl", "cache", "tmp", "reports"}


class StoragePermissionError(PermissionError):
    def __init__(self, path, error):
        self.path = path
        super().__init__(f"Gnothi storage access denied at {path}: {error}")


def data_root():
    if sys.platform == "win32":
        default = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / "Gnothi"
    elif sys.platform == "darwin":
        default = Path.home() / "Library/Application Support/Gnothi"
    else:
        default = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "gnothi"

    return Path(os.environ.get("GNOTHI_DATA_DIR") or default).expanduser().resolve()


def inside_git(path):
    for folder in (path, *path.parents):
        if (folder / ".git").exists():
            return True

    return False


def guard(path):
    path = Path(path).expanduser().resolve()

    if path == Path.home().resolve() or path == Path(path.anchor):
        raise ValueError(f"Refusing to use {path} for Gnothi data")

    if path == PLUGIN or PLUGIN in path.parents:
        raise ValueError("Gnothi data must stay outside the plugin package")

    if inside_git(path):
        raise ValueError(f"Gnothi never writes inside a Git work tree: {path}")

    return path


def private_dir(path):
    path = guard(path)
    root = data_root()
    path.mkdir(parents=True, exist_ok=True)

    if sys.platform != "win32":
        for folder in (path, *path.parents):
            if folder != path and folder != root and root not in folder.parents:
                break

            folder.chmod(0o700)

    return path


def write_private(path, text):
    try:
        return _write_private(path, text)
    except PermissionError as error:
        raise StoragePermissionError(path, error) from error


def _write_private(path, text):
    path = guard(path)
    private_dir(path.parent)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")

    try:
        temporary.write_text(text, encoding="utf-8")

        if sys.platform != "win32":
            temporary.chmod(0o600)

        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()

    return path


def check_writable():
    root = data_root()

    for folder in (root, root / "tmp"):
        try:
            probe = _write_private(folder / f".write-test-{uuid4().hex}", "")
            probe.unlink()
        except PermissionError as error:
            raise StoragePermissionError(folder, error) from error

    return root


def forget():
    root = guard(data_root())

    if not root.exists():
        return root

    unknown = sorted(entry.name for entry in root.iterdir() if entry.name not in KNOWN)

    if unknown:
        raise ValueError(f"{root} holds files Gnothi did not create: {', '.join(unknown)}")

    shutil.rmtree(root)
    return root
