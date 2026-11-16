import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path


PLUGIN = Path(__file__).resolve().parent.parent


def asset_files(source):
    return sorted(path for path in source.iterdir() if path.is_file())


def asset_id(source):
    digest = hashlib.sha256()
    for path in asset_files(source):
        digest.update(path.name.encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def data_root():
    if sys.platform == "win32":
        default = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / "ReadyCheck"
    elif sys.platform == "darwin":
        default = Path.home() / "Library/Application Support/ReadyCheck"
    else:
        default = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "ready-check"
    return Path(os.environ.get("READY_CHECK_DATA_DIR", default)).expanduser().resolve()


def bundle_path(source, root, component):
    return Path(root) / component / asset_id(source)[:20]


def outside_repositories(path, project):
    path = path.resolve()
    forbidden = [PLUGIN, project.resolve()]
    result = subprocess.run(["git", "-C", str(project), "rev-parse", "--show-toplevel"],
                            capture_output=True, text=True, encoding="utf-8")
    if result.returncode == 0:
        forbidden.append(Path(result.stdout.strip()).resolve())
    if any(path.is_relative_to(root) for root in forbidden):
        raise ValueError("Dependency data must be outside the project repository and plugin package")
    return path


def installed(source, destination):
    try:
        marker = json.loads((destination / "ready.json").read_text(encoding="utf-8"))
        return isinstance(marker, dict) and marker.get("asset_id") == asset_id(source) and all(
            (destination / path.name).read_bytes() == path.read_bytes() for path in asset_files(source))
    except (OSError, ValueError):
        return False


def write_marker(source, destination, details):
    temporary = destination / "ready.tmp"
    temporary.write_text(json.dumps(dict(asset_id=asset_id(source), **details), indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination / "ready.json")


class LocalStorage:
    def mkdir(self, path):
        Path(path).mkdir(mode=0o700)

    def exists(self, path, kind="file"):
        return Path(path).is_dir()

    def read(self, path):
        return Path(path).read_bytes()

    def write(self, path, content):
        Path(path).write_bytes(content)

    def unlink(self, path):
        Path(path).unlink(missing_ok=True)

    def rmdir(self, path):
        Path(path).rmdir()


def lock_owner():
    return dict(pid=os.getpid(), host=socket.gethostname(), started=time.time())


def lock_is_stale(owner, age_seconds, timeout):
    if owner is None:
        return age_seconds > timeout + 600
    if not isinstance(owner, dict) or owner.get("host") != socket.gethostname() or os.name == "nt":
        return False
    pid = owner.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except OSError:
        return False
    return False


def lock_age(storage, lock):
    if getattr(storage, "name", "local") == "local":
        return time.time() - Path(lock).stat().st_mtime
    script = 'm=$(stat -c %Y -- "$1" 2>/dev/null || stat -f %m -- "$1") && echo $(( $(date +%s) - m ))'
    return float(storage.sh(script, lock).decode().strip())


def take_lock(lock, timeout, storage=None):
    storage = storage or LocalStorage()
    owner_file = lock + "/owner.json"
    for attempt in range(2):
        try:
            storage.mkdir(lock)
        except (OSError, ValueError):
            if attempt or not storage.exists(lock, "dir"):
                raise
            try:
                owner = json.loads(storage.read(owner_file))
            except (OSError, ValueError):
                owner = None
            try:
                age = lock_age(storage, lock)
            except (OSError, ValueError):
                age = 0
            if not lock_is_stale(owner, age, timeout):
                details = f"pid {owner.get('pid')} on {owner.get('host')} since {time.ctime(owner.get('started', 0))}" if isinstance(owner, dict) else "an unknown owner"
                raise ValueError(f"Another setup holds {lock} ({details}); wait for it or remove the lock after confirming no setup runs")
            release_lock(lock, storage)
            continue
        try:
            storage.write(owner_file, json.dumps(lock_owner()).encode())
        except (OSError, ValueError):
            release_lock(lock, storage)
            raise
        return


def release_lock(lock, storage=None):
    storage = storage or LocalStorage()
    storage.unlink(lock + "/owner.json")
    storage.rmdir(lock)
