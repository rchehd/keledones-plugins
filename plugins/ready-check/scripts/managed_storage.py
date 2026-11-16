import json
import os
import stat
from pathlib import Path, PurePosixPath

from dependency_support import asset_files, asset_id


MARKER = ".ready-check-owned.json"
ROOT_STATE = {"settings.json", "install-result.json", "rules.md", "disabled.json", "extensions", "logs", "state"}


class Storage:
    def __init__(self, runner=None):
        self.runner = runner if runner is not None and runner.name != "local" else None
        self.path = PurePosixPath if self.runner else Path

    def exists(self, path):
        return self.runner.exists(str(path)) if self.runner else path.exists() or path.is_symlink()

    def directory(self, path):
        return self.runner.exists(str(path), "dir") if self.runner else path.is_dir()

    def linked(self, path):
        if self.runner:
            return self.runner.sh('if [ -L "$1" ]; then echo yes; else echo no; fi', path).decode().strip() == "yes"
        return path.is_symlink() or path.exists() and bool(
            getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))

    def read(self, path):
        return self.runner.read(str(path)) if self.runner else path.read_bytes()

    def children(self, path):
        if self.runner:
            listing = self.runner.sh('find "$1" -mindepth 1 -maxdepth 1 -print0', path)
            return [path / PurePosixPath(os.fsdecode(entry)).name for entry in listing.split(b"\0") if entry]
        return list(path.iterdir())

    def mkdir(self, path):
        if self.runner:
            self.runner.mkdir(str(path), parents=True)
        else:
            path.mkdir(parents=True, exist_ok=True, mode=0o700)

    def create(self, path, value):
        content = (json.dumps(value, sort_keys=True) + "\n").encode()
        if self.runner:
            self.runner.sh('set -C; cat > "$1"', path, input=content)
        else:
            with path.open("xb") as stream:
                stream.write(content)

    def safe_path(self, root, path):
        relative = path.relative_to(root)
        for index in range(len(relative.parts) + 1):
            current = root.joinpath(*relative.parts[:index])
            if self.linked(current):
                raise ValueError(f"Managed storage path redirects through a link: {current}")

    def safe_tree(self, root):
        if not self.exists(root):
            return
        if self.runner:
            script = ('root=$(readlink -f -- "$1") && [ -n "$root" ] || exit 1; '
                      'find "$root" -type l -exec sh -c \'for f; do p=$(readlink -f -- "$f") || p=; [ -e "$f" ] || p=; '
                      'case "$p" in "$0"|"$0"/*) ;; *) printf "%s" "$f"; exit 0;; esac; done\' "$root" {} +')
            escaped = self.runner.sh(script, root).decode().strip()
            if escaped:
                raise ValueError(f"Managed storage contains an external link: {escaped}")
        else:
            resolved = root.resolve()
            for directory, children, files in os.walk(root, followlinks=False):
                for name in children + files:
                    path = Path(directory) / name
                    if self.linked(path) and not path.resolve().is_relative_to(resolved):
                        raise ValueError(f"Managed storage contains an external link: {path}")

    def foreign(self, directory, allowed=()):
        return [path for path in self.children(directory) if path.name not in allowed]

    def claim(self, directory, identity, allowed=()):
        marker = directory / MARKER
        if self.linked(marker):
            raise ValueError(f"Managed storage ownership marker is a link: {marker}")
        if self.exists(directory):
            if not self.directory(directory):
                raise ValueError(f"Managed storage must be a directory: {directory}")
            if self.exists(marker):
                try:
                    valid = json.loads(self.read(marker)) == identity
                except (OSError, ValueError):
                    valid = False
                if not valid:
                    raise ValueError(f"Storage belongs to another tool or has an invalid ownership marker: {directory}")
                return
            if self.foreign(directory, allowed):
                raise ValueError(f"Refusing to overwrite nonempty storage without Ready Check ownership: {directory}")
        self.mkdir(directory)
        try:
            self.create(marker, identity)
        except (OSError, ValueError):
            if not self.exists(marker) or json.loads(self.read(marker)) != identity:
                raise


def prepare_storage(root, destination, source, component, runner=None, dry_run=False):
    storage = Storage(runner)
    root, destination = storage.path(root), storage.path(destination)
    protected = [root / name for name in ("browser", "browsers", "profiles", "npm-cache", "composer-home", "composer-cache")]
    protected += [destination / name for name in [MARKER, "ready.json", "ready.tmp", "setup.log", ".setup-lock", "vendor", "node_modules"]]
    protected += [destination / file.name for file in asset_files(source)]
    for path in [root / MARKER, destination, *protected]:
        storage.safe_path(root, path)
    storage.safe_tree(root)
    storage.safe_tree(destination)
    for name in ("browsers", "npm-cache", "composer-home", "composer-cache"):
        storage.safe_tree(root / name)
    identity = dict(owner="ready-check", schema_version=1)
    if dry_run:
        for directory, expected, allowed in ((root, identity, ROOT_STATE),
                (destination, dict(identity, component=component, asset_id=asset_id(source)), ())):
            marker = directory / MARKER
            if storage.exists(marker):
                if json.loads(storage.read(marker)) != expected:
                    raise ValueError(f"Invalid Ready Check ownership: {directory}")
            elif storage.exists(directory) and (not storage.directory(directory) or storage.foreign(directory, allowed)):
                raise ValueError(f"Refusing to overwrite nonempty storage without Ready Check ownership: {directory}")
        return
    storage.claim(root, identity, ROOT_STATE)
    storage.claim(destination, dict(identity, component=component, asset_id=asset_id(source)))
