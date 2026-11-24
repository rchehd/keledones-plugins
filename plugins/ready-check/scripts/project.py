import errno
import json
import os
import re
import shutil
import stat
import tempfile
from contextlib import contextmanager, suppress
from pathlib import Path

import git_exclude
from file_lock import exclusive_lock

BASE = Path(".ai/ready-check")
LEGACY_BASE = Path("ai/ready-check")
BRANCH_REPORT = ".branch-report"
MARKDOWN_PATH = re.compile(r"(\]\()(<[^>\r\n]+>|[^)\r\n]+)(\))|(`)([^`\r\n]+)(`)")
TASK_REPORT = re.compile(r".+-\d{4}-\d{2}-\d{2}\Z")


def toplevel(start):
    try:
        start = Path(start).resolve()
    except (OSError, RuntimeError, TypeError):
        return None

    if not start.is_dir():
        return None

    top = git_exclude.git(start, "rev-parse", "--show-toplevel")
    return Path(top).resolve() if top else None


def ensure_excluded(top, *, legacy=False):
    directory = Path(top) / BASE
    if redirected(directory) or directory.exists() and not directory.is_dir():
        raise ValueError(f"Ready Check storage must be a real directory: {directory}")
    entries = (BASE, LEGACY_BASE) if legacy else (BASE,)
    paths = [entry.as_posix() + "/" for entry in entries]
    plan = git_exclude.plan(top, paths)
    git_exclude.apply(plan, merge_entries=True)
    return plan


def is_reparse_point(path):
    try:
        attributes = path.lstat().st_file_attributes
    except (AttributeError, FileNotFoundError):
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def redirected(path):
    return path.is_symlink() or is_reparse_point(path) or path.resolve() != path


def project_locations(top, *parts):
    return tuple(Path(top) / root / Path(*parts) for root in (BASE, LEGACY_BASE))


def project_file(top, *parts):
    current, legacy = project_locations(top, *parts)
    return legacy if not os.path.lexists(current) and legacy.exists() and not redirected(legacy) else current


def team_files(top, *parts):
    current, legacy = project_locations(top, *parts)
    paths = [path for path in (current, legacy) if path.is_file() and not redirected(path)]
    if len(paths) == 2 and not git_exclude.git(top, "ls-files", "--", legacy.relative_to(top).as_posix()):
        paths.pop()
    return paths


def git_commit_template(top):
    value = git_exclude.git(top, "config", "--null", "--show-scope", "--path", "--get", "commit.template")
    if not value:
        return None, None
    scope, _, name = value.partition("\0")
    name = name.removesuffix("\0")
    return (scope, (top / Path(name).expanduser()).resolve()) if name else (None, None)


@contextmanager
def migration_lock(destination):
    if redirected(destination) or destination.exists() and not destination.is_dir():
        raise ValueError(f"Ready Check storage must be a real directory: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    lock = destination / ".migration.lock"
    if redirected(lock) or lock.exists() and not lock.is_file():
        raise ValueError(f"Ready Check migration lock must be a regular file: {lock}")
    with exclusive_lock(lock):
        yield


def staged_copy(source, target, content=None, original=None):
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".migration-", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        if content is None:
            version = file_version(source)
            shutil.copy2(source, temporary)
            if file_version(source) != version:
                return
            if os.path.lexists(target):
                raise FileExistsError(target)
        else:
            temporary.write_bytes(content)
            shutil.copystat(source, temporary)
            if redirected(target) or target.read_bytes() != original:
                raise ValueError(f"Report changed during Ready Check migration; retry: {target}")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def file_version(path):
    status = path.lstat()
    return status.st_dev, status.st_ino, status.st_mode, status.st_size, status.st_mtime_ns, status.st_ctime_ns


def move_or_copy(source, target, copy):
    if os.path.lexists(target):
        return
    try:
        source.rename(target)
    except OSError as error:
        if error.errno not in {errno.EXDEV, errno.ENOTSUP, errno.EACCES, errno.EPERM} and getattr(error, "winerror", None) != 17:
            raise
        copy(source, target)


def branch_task_dirs(folder, names):
    return [name for name in names
            if name == BRANCH_REPORT or TASK_REPORT.fullmatch(name) and (folder / name).is_dir()]


def report_version(root, *, branch_only=False):
    version = {}
    for directory, folders, files in os.walk(root):
        folder = Path(directory)
        if branch_only and folder == root:
            ignored = branch_task_dirs(folder, folders + files)
            folders[:] = [name for name in folders if name not in ignored]
            files = [name for name in files if name not in ignored]
        for path in (folder, *(folder / name for name in folders + files)):
            if redirected(path):
                return None
            entry = file_version(path)
            if not (stat.S_ISDIR(entry[2]) or stat.S_ISREG(entry[2])):
                return None
            version[path.relative_to(root)] = entry
    return version


def copy_report(source, target, *, branch_only=False):
    before = report_version(source, branch_only=branch_only)
    if before is None:
        return
    with tempfile.TemporaryDirectory(dir=target.parent, prefix=".report-migration-") as directory:
        bundle = Path(directory) / "bundle"

        def ignore(folder, names):
            return branch_task_dirs(source, names) if branch_only and Path(folder) == source else []

        shutil.copytree(source, bundle, symlinks=True, ignore=ignore)
        rebase_report_tree(bundle, source, target, set(), staged=bundle)
        if report_version(source, branch_only=branch_only) == before and not os.path.lexists(target):
            bundle.rename(target)


def move_report(source, target, preserved, pending):
    if os.path.lexists(target) or not source.is_dir() or redirected(source) or redirected(target.parent):
        return False
    if any(path.is_relative_to(source) or path.is_relative_to(target) for path in preserved):
        return False
    if report_version(source) is None:
        return False
    target.parent.mkdir(exist_ok=True)
    pending.touch()
    move_or_copy(source, target, copy_report)
    return True


def branch_report_directory(branch):
    for folder in (branch, branch / BRANCH_REPORT):
        report = folder / "report.md"
        if report.is_file() and not redirected(report):
            return folder
    return None


def copy_branch_report(source, target, preserved):
    report = source / "report.md"
    bundle = target / BRANCH_REPORT
    if not report.is_file() or redirected(report) or branch_report_directory(target) or os.path.lexists(bundle):
        return
    version = report_version(source, branch_only=True)
    if version is None or any(source / path in preserved or bundle / path in preserved for path in version):
        return
    target.mkdir(exist_ok=True)
    copy_report(source, bundle, branch_only=True)


def move_reports(source, destination, preserved, pending):
    if redirected(destination) or destination.exists() and not destination.is_dir():
        return
    destination.mkdir(exist_ok=True)
    for branch in list(source.iterdir()):
        target = destination / branch.name
        if (redirected(branch) or not branch.is_dir() or branch in preserved or redirected(target)
                or target.exists() and not target.is_dir()):
            continue
        if move_report(branch, target, preserved, pending):
            continue
        if branch.is_dir():
            copy_branch_report(branch, target, preserved)
            for task in list(branch.iterdir()):
                if TASK_REPORT.fullmatch(task.name):
                    move_report(task, target / task.name, preserved, pending)
        with suppress(OSError):
            branch.rmdir()


def move_data(source, destination, preserved, pending):
    if redirected(destination) or destination.exists() and not destination.is_dir():
        return
    destination.mkdir(parents=True, exist_ok=True)

    for item in list(source.iterdir()):
        target = destination / item.name
        try:
            mode = item.lstat().st_mode
            if item in preserved or target in preserved or redirected(item):
                continue
            if stat.S_ISDIR(mode):
                if target == pending.parent / "reports":
                    move_reports(item, target, preserved, pending)
                else:
                    move_data(item, target, preserved, pending)
                with suppress(OSError):
                    item.rmdir()
            elif stat.S_ISREG(mode):
                if item.suffix == ".jsonl":
                    if not os.path.lexists(target):
                        staged_copy(item, target)
                else:
                    move_or_copy(item, target, staged_copy)
        except (FileExistsError, FileNotFoundError):
            continue


def relocated_reference(value, source, destination, *, staged=None):
    path = Path(value)
    if not path.is_absolute() or not path.is_relative_to(source) or staged is None and os.path.lexists(path):
        return value
    relative = path.relative_to(source)
    evidence = (staged if staged is not None else destination) / relative
    if not evidence.exists() or redirected(evidence):
        return value
    moved = destination / relative
    return moved.as_posix() if "/" in value and "\\" not in value else str(moved)


def rebase_metadata(path, source, destination, *, staged=None):
    try:
        original = path.read_bytes()
        text = original.decode("utf-8-sig")
    except UnicodeDecodeError:
        return

    def reference(value):
        return relocated_reference(value, source, destination, staged=staged)

    if path.suffix == ".json":
        def relocate(value):
            if isinstance(value, str):
                return reference(value)
            if isinstance(value, list):
                return [relocate(item) for item in value]
            if isinstance(value, dict):
                return {key: relocate(item) for key, item in value.items()}
            return value

        try:
            data = json.loads(text)
        except ValueError:
            return
        updated = relocate(data)
        if updated == data:
            return
        text = json.dumps(updated, ensure_ascii=False, indent=2) + "\n"
    else:
        def markdown(match):
            prefix, value, suffix = match.groups()[:3] if match[1] else match.groups()[3:]
            if value.startswith("<") and value.endswith(">"):
                return prefix + "<" + reference(value[1:-1]) + ">" + suffix
            return prefix + reference(value) + suffix

        text = MARKDOWN_PATH.sub(markdown, text)

    content = text.encode("utf-8-sig" if original.startswith(b"\xef\xbb\xbf") else "utf-8")
    if content != original:
        staged_copy(path, path, content, original)


def rebase_report_tree(root, source, destination, tracked, *, staged=None):
    if redirected(root):
        return
    for directory, folders, files in os.walk(root):
        folder = Path(directory)
        folders[:] = [name for name in folders if not redirected(folder / name)]
        for name in files:
            path = folder / name
            if path not in tracked and path.suffix in {".json", ".md"} and path.is_file() and not redirected(path):
                rebase_metadata(path, source, destination, staged=staged)


def rebase_reports(source, destination, tracked):
    for root in (destination / "reports", source / "reports"):
        rebase_report_tree(root, source, destination, tracked)


def migrate(top):
    top = Path(top)
    source = top / LEGACY_BASE
    if not os.path.lexists(source):
        return
    destination = top / BASE
    with migration_lock(destination):
        if not os.path.lexists(source):
            return
        if redirected(source) or not source.is_dir():
            raise ValueError(f"Legacy Ready Check storage must be a real directory: {source}")
        tracked = git_exclude.git(top, "ls-files", "-z", "--", LEGACY_BASE.as_posix(), BASE.as_posix())
        if tracked is None and toplevel(top):
            raise ValueError("Cannot identify Git-tracked files in legacy Ready Check storage")
        tracked = {top / name for name in (tracked or "").split("\0") if name}
        template = None
        with suppress(OSError, RuntimeError, ValueError):
            _, template = git_commit_template(top)
        preserved = tracked | ({template} if template and template.is_relative_to(source) else set())
        ensure_excluded(top, legacy=True)
        pending = destination / ".report-migration"
        if redirected(pending):
            raise ValueError(f"Ready Check migration marker must be a regular file: {pending}")
        move_data(source, destination, preserved, pending)
        if pending.is_file():
            rebase_reports(source, destination, tracked)
            pending.unlink()
        with suppress(OSError):
            source.rmdir()


UNCHECKED = object()


def write_json(path, data, root=None, *, original=UNCHECKED):
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
        if original is not UNCHECKED:
            if redirected(path) or path.exists() and not path.is_file():
                raise ValueError(f"File changed during setup. Retry to preserve current edits: {path}")
            try:
                current_bytes = path.read_bytes()
            except FileNotFoundError:
                current_bytes = None
            if current_bytes != original:
                raise ValueError(f"File changed during setup. Retry to preserve current edits: {path}")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
