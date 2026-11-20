import hashlib
import json
import time

from dependency_support import data_root
from project import write_json


def path(client, session):
    digest = hashlib.sha256(str(session).encode("utf-8", "replace")).hexdigest()[:16]
    return data_root() / "state" / f"{client}-{digest}.json"


def load(client, session):
    try:
        data = json.loads(path(client, session).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(client, session, data):
    write_json(path(client, session), data, data_root())


def prune(days=7):
    folder = data_root() / "state"
    cutoff = time.time() - days * 86400
    removed = 0

    if folder.is_symlink() or not folder.is_dir():
        return removed

    for item in folder.glob("*.json"):
        try:
            if item.is_file() and not item.is_symlink() and item.stat().st_mtime < cutoff:
                item.unlink(missing_ok=True)
                removed += 1
        except OSError:
            continue

    return removed
