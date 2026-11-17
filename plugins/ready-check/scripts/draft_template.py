import argparse
import json
from pathlib import Path

import settings
from dependency_support import PLUGIN
from git_exclude import git
from project import toplevel

KINDS = {
    "commit": ("commitTemplate", "commit-message.txt"),
    "pr": ("pullRequestTemplate", "pull-request.md"),
}


def configured(path, key, top=None):
    values = settings.read(path)
    if key not in values:
        return None
    if not settings.valid(key, values[key]):
        raise ValueError(f"Invalid value for {key} in {path}")
    return settings.template_path(values[key], top)


def repository_pr(top):
    for directory, filename in ((".github", "pull_request_template.md"), (".", "pull_request_template.md"),
                                ("docs", "pull_request_template.md"), (".gitlab/merge_request_templates", "default.md")):
        folder = top / directory
        if folder.resolve().is_relative_to(top) and folder.is_dir():
            for entry in sorted(folder.iterdir()):
                if entry.name.lower() == filename and entry.is_file():
                    return settings.template_path(entry, top)
    return None


def git_commit(top):
    value = git(top, "config", "--null", "--show-scope", "--path", "--get", "commit.template")
    if not value:
        return None, None
    scope, _, name = value.partition("\0")
    name = name.removesuffix("\0")
    if not name:
        return None, None
    return scope, (top / Path(name).expanduser()).resolve()


def select(kind, top=None):
    key, default = KINDS[kind]
    native_git = None
    if top:
        override = configured(settings.project_path(top), key, top)
        if override:
            return "project", override
        if kind == "pr":
            if native := repository_pr(top):
                return "repository", native
        else:
            scope, native_git = git_commit(top)
            if native_git and scope in {"local", "worktree", "command"}:
                return "repository", native_git

    if custom := configured(settings.user_path(), key):
        return "user", custom
    if native_git:
        return "git", native_git
    return "default", PLUGIN / "templates" / default


def main():
    parser = argparse.ArgumentParser(description="Get the effective Ready Check commit message or PR body template.")
    parser.add_argument("kind", choices=KINDS)
    parser.add_argument("--project", type=Path)
    args = parser.parse_args()
    result = dict(schema_version=1, action="template", kind=args.kind, status="FAIL")
    try:
        top = toplevel(args.project) if args.project else None
        if args.project and top is None:
            raise ValueError("Project templates need a Git work tree")
        source, path = select(args.kind, top)
        result.update(source=source, path=str(path))
        if not path.is_file():
            raise ValueError(f"Template file does not exist: {path}")
        content = path.read_text(encoding="utf-8-sig")
        if not content.strip() or "\0" in content:
            raise ValueError(f"Template must be nonempty UTF-8 text: {path}")
        result.update(status="PASS", content=content)
    except (OSError, ValueError, RuntimeError) as error:
        result["reason"] = str(error)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2
