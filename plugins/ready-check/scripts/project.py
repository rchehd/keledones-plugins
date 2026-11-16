import json
import tempfile
from pathlib import Path

import git_exclude

BASE = Path("ai/ready-check")


def toplevel(start):
    try:
        start = Path(start).resolve()
    except (OSError, RuntimeError, TypeError):
        return None

    if not start.is_dir():
        return None

    top = git_exclude.git(start, "rev-parse", "--show-toplevel")
    return Path(top).resolve() if top else None


def ensure_excluded(top):
    git_exclude.apply(git_exclude.plan(top, [BASE.as_posix() + "/"]))


def write_json(path, data, root=None):
    path = Path(path)
    current = Path(root) if root else path.parent

    for part in path.relative_to(current).parts:
        current = current / part

        if current.is_symlink():
            raise ValueError(f"Refusing to write through a symlink: {current}")

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None

    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".ready-check.", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
