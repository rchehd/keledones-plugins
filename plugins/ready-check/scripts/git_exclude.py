import os
import posixpath
import stat
import subprocess
import tempfile
from pathlib import Path


BEGIN = b"# ready-check:begin"
END = b"# ready-check:end"


def git(project, *args):
    result = subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True, encoding="utf-8")
    return result.stdout.strip() if result.returncode == 0 else None


def exclude_file(path):
    if path.is_symlink() or path.exists() and not path.is_file():
        raise ValueError(f"Git exclude file must be a regular file, not a symlink or directory: {path}")
    return path


def updated_content(original, anchored):
    newline = b"\r\n" if b"\r\n" in original else b"\n"
    lines = original.splitlines(keepends=True)
    begins = [index for index, line in enumerate(lines) if line.strip() == BEGIN]
    ends = [index for index, line in enumerate(lines) if line.strip() == END]
    if len(begins) != len(ends) or len(begins) > 1 or begins and begins[0] > ends[0]:
        raise ValueError("Ready Check Git exclude markers are incomplete or duplicated; resolve them before setup")
    existing = [line.strip() for line in lines[begins[0] + 1:ends[0]] if line.strip()] if begins else []
    entries = existing + [entry for entry in anchored if entry not in existing]
    block = newline.join([BEGIN, *entries, END]) + newline
    if begins:
        return b"".join(lines[:begins[0]]) + block + b"".join(lines[ends[0] + 1:])
    if original and not original.endswith(b"\n"):
        original += newline
    return original + block


def plan(project, entries):
    project = Path(project).resolve()
    top = git(project, "rev-parse", "--show-toplevel")
    location = git(project, "rev-parse", "--git-path", "info/exclude")
    if not top or not location:
        return None
    relative = project.relative_to(Path(top).resolve()).as_posix()
    anchored = ["/" + posixpath.normpath(posixpath.join(relative, entry)) + ("/" if entry.endswith("/") else "")
                for entry in entries]
    path = exclude_file(Path(os.path.abspath(project / location)))
    original = path.read_bytes() if path.exists() else None
    updated = updated_content(original or b"", [entry.encode() for entry in anchored])
    return dict(path=path, original=original, updated=updated, entries=anchored, applied=False,
                action="create" if original is None else "unchanged" if original == updated else "update")


def describe(plan, status, reason=None):
    if plan is None:
        return dict(status="SKIPPED", path=None, entries=[], action=None, reason="Project is not inside a Git work tree")
    if status == "INCOMPLETE" and plan["applied"]:
        status = "PASS"
    return dict(status=status, path=str(plan["path"]), entries=plan["entries"], action=plan["action"],
                reason=None if status == "PASS" else reason)


def verify(plan):
    path = exclude_file(plan["path"])
    current = path.read_bytes() if path.exists() else None
    if current != plan["original"]:
        raise ValueError(f"Git exclude file changed during setup; repeat setup to preserve current edits: {path}")


def apply(plan):
    if plan is None or plan["action"] == "unchanged":
        return
    path = plan["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    verify(plan)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".ready-check-exclude.", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(plan["updated"])
        if plan["original"] is not None:
            os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        verify(plan)
        temporary.replace(path)
        plan["applied"] = True
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
