import hashlib
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from process_support import execute
from project import BASE, LEGACY_BASE
from settings import project_config, valid

DATA = BASE.as_posix()
DATA_DIRS = (DATA, LEGACY_BASE.as_posix())
CORE = Path(__file__).resolve().parent
BLAME = re.compile(r"^([0-9a-f]{40}) \d+ (\d+) (\d+)$", re.M)
HUNK = re.compile(r"^@@ .*?\+(\d+)(?:,(\d+))? @@", re.M)
UNCOMMITTED = "0" * 40
LEGACY_TEMP = ".ready-check-lint."


def git(project, *args):
    code, stdout, stderr = execute(["git", *args], project, timeout=120)

    if code:
        raise ValueError(stderr.decode(errors="replace").strip() or "Git command failed")
    return stdout


def listing(data):
    return {os.fsdecode(p) for p in data.split(b"\0") if p}


def own(path):
    return any(path == data or path.startswith(data + "/") for data in DATA_DIRS) or path.split("/")[0].startswith(LEGACY_TEMP)


def untracked(project):
    return {p for p in listing(git(project, "ls-files", "--others", "--exclude-standard", "-z")) if not own(p)}


def base_scope(project, head, base):
    if base.startswith("-"):
        raise ValueError("Base ref must not be an option")
    merge_base = git(project, "merge-base", "HEAD", base).decode().strip()
    spec = (".", *(":(exclude)" + data for data in DATA_DIRS))
    flags = ("--relative", "--name-only", "--no-renames", "-z")
    diff = git(project, "diff", "--no-ext-diff", "--no-textconv", "--binary", merge_base, "--", *spec)
    changed = listing(git(project, "diff", *flags, merge_base, "--", *spec))
    existing = listing(git(project, "diff", *flags, "--diff-filter=d", merge_base, "--", *spec))
    new = untracked(project)
    return dict(mode="base", commits=None, base=base, merge_base=merge_base, files=sorted(existing | new),
                changed_files=sorted(changed | new), hashed=sorted(new),
                seed=head.encode() + b"\0" + merge_base.encode() + b"\0" + diff, outside=None)


def commit_scope(project, root, head, commits):
    shas = []

    for commit in commits:
        if commit.startswith("-"):
            raise ValueError("Commit must not be an option")
        sha = git(project, "rev-parse", "--verify", commit + "^{commit}").decode().strip()
        code, _, _ = execute(["git", "merge-base", "--is-ancestor", sha, "HEAD"], project)

        if code == 1:
            raise ValueError(f"Commit {sha[:12]} is not an ancestor of HEAD")

        if code:
            raise ValueError("Cannot verify commit ancestry")

        if sha not in shas:
            shas.append(sha)
    flags = ("diff-tree", "--no-commit-id", "-r", "--name-only", "--no-renames", "-z", "--root")
    task, repository = set(), set()

    for sha in shas:
        task |= listing(git(project, *flags, "--relative", sha))
        repository |= listing(git(root, *flags, sha))
    task = {p for p in task if not own(p)}
    names = sorted(task)
    existing = [p for p in names if os.path.lexists(project / p)]
    dirty = {p for p in listing(git(project, "diff", "--relative", "--name-only", "--no-renames", "-z", "HEAD", "--", "."))
             if not own(p)} | untracked(project)
    diff = git(project, "--literal-pathspecs", "diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD", "--", *names) if names else b""
    return dict(mode="commits", commits=shas, base=None, merge_base=None, files=existing, changed_files=names,
                hashed=sorted(p for p in untracked(project) if p in task), outside=repository,
                uncommitted_outside_task=sorted(dirty - task),
                seed=head.encode() + b"\0commits\0" + b"\0".join(s.encode() for s in sorted(shas)) + b"\0" + diff)


def snapshot(project, spec, base=None, commits=None, paths=None):
    root = Path(os.fsdecode(git(project, "rev-parse", "--show-toplevel")).strip()).resolve()
    head = git(project, "rev-parse", "HEAD").decode().strip()
    prefix = project.relative_to(root).as_posix()
    part = commit_scope(project, root, head, commits) if commits else base_scope(project, head, base)
    omitted = set()
    if paths:
        if not all(valid("application", path) for path in paths):
            raise ValueError("Each --path must be relative to the application")
        paths = sorted(set(paths))
        omitted = {name for name in part["changed_files"]
                   if not any(path == "." or name == path or name.startswith(path + "/") for path in paths)}
        for key in ("files", "changed_files"):
            part[key] = [name for name in part[key] if name not in omitted]

    if not part["changed_files"]:
        raise ValueError("No changes found; clarify the application and scope")
    digest = hashlib.sha256(part["seed"])
    if paths:
        digest.update(json.dumps(paths).encode())
    digest.update(json.dumps(project_config(project, spec.id), sort_keys=True).encode())
    digest.update(spec.directory.joinpath("profile.json").read_bytes())

    for folder in (spec.directory / "scripts", CORE, *(p.directory for p in spec.providers)):
        for path in sorted(folder.glob("*")):
            if path.suffix in {".py", ".sh"}:
                digest.update(path.name.encode() + path.read_bytes())

    for path in sorted((Path(__file__).resolve().parents[3] / "scripts").glob("*.py")):
        digest.update(path.name.encode() + path.read_bytes())
    settings = {k: v for k, v in os.environ.items() if (k.startswith("LINT_") and k != "LINT_EVENTS")
                or k in {"READY_CHECK_DATA_DIR", "READY_CHECK_RUNNER_DATA_DIR"}}
    digest.update(json.dumps(settings, sort_keys=True).encode())

    for name in part["hashed"]:
        path = project / name
        digest.update(os.fsencode(name) + b"\0" + str(path.lstat().st_mode).encode() + b"\0")
        digest.update(os.fsencode(os.readlink(path)) if path.is_symlink() else path.read_bytes())
    outside = part["outside"]

    if outside is None:
        outside = listing(git(root, "diff", "--name-only", "--no-renames", "-z", part["merge_base"])) | listing(
            git(root, "ls-files", "--others", "--exclude-standard", "-z"))
    outside = [p for p in outside if prefix != "." and not p.startswith(prefix + "/") and not own(p)]
    scope = {"repository": str(root), "project": str(project), "mode": part["mode"], "commits": part["commits"],
             "head": head, "base": part["base"], "merge_base": part["merge_base"], "snapshot": digest.hexdigest(),
             "files": part["files"], "changed_files": part["changed_files"], "outside_scope": sorted(outside)}
    if paths:
        scope["paths"] = paths
        scope["outside_scope"] = sorted(set(outside) | {(Path(prefix) / name).as_posix() for name in omitted})

    if "uncommitted_outside_task" in part:
        scope["uncommitted_outside_task"] = part["uncommitted_outside_task"]
    return scope


def lint_files(files, core, spec):
    return [p for p in files if not (set(Path(p).parts) & spec.excluded)
            and not p.startswith(core) and not p.startswith(tuple(getattr(spec, "excluded_prefixes", ())))
            and not p.endswith((".min.js", ".min.css"))]


def changed_lines(project, scope, files):
    new = untracked(project)
    lines = {}

    for file in files:
        if file in new:
            lines[file] = None
        elif scope["mode"] == "base":
            patch = git(project, "--literal-pathspecs", "diff", "--no-ext-diff", "--no-textconv", "-U0",
                        scope["merge_base"], "--", file).decode(errors="replace")
            lines[file] = {n for m in HUNK.finditer(patch) for n in range(int(m[1]), int(m[1]) + int(m[2] or 1))}
        else:
            keep = {*scope["commits"], UNCOMMITTED}
            blame = git(project, "blame", "--incremental", "--", file).decode(errors="replace")
            lines[file] = {n for m in BLAME.finditer(blame) if m[1] in keep for n in range(int(m[2]), int(m[2]) + int(m[3]))}
    return lines
