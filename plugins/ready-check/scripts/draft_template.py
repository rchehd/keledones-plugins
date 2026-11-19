import argparse
import json
import os
from pathlib import Path

import settings
from dependency_support import PLUGIN
from project import BASE, LEGACY_BASE, git_commit_template, project_file, relocated_reference, toplevel

KINDS = {
    "commit": ("commitTemplate", "commit-message.txt"),
    "pr": ("pullRequestTemplate", "pull-request.md"),
    "task-comment": ("taskCommentTemplate", "task-comment.md"),
}
COMMENT_OPTIONS = ("CLAUDE_PLUGIN_OPTION_TASK_COMMENT_TEMPLATE", "READY_CHECK_TASK_COMMENT_TEMPLATE")


def client_comment_template():
    return next((os.environ[name].strip() for name in COMMENT_OPTIONS if os.environ.get(name, "").strip()), None)


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


def migrated_path(path, top):
    return Path(relocated_reference(str(path), top / LEGACY_BASE, top / BASE)) if top else path


def select(kind, top=None, client_template=None):
    key, default = KINDS[kind]
    native_git = None
    if top:
        override = configured(project_file(top, "settings.json"), key, top)
        if override:
            return "project", override
        if kind == "pr":
            if native := repository_pr(top):
                return "repository", native
        elif kind == "commit":
            scope, native_git = git_commit_template(top)
            if native_git:
                native_git = migrated_path(native_git, top)
            if native_git and scope in {"local", "worktree", "command"}:
                return "repository", native_git

    if kind == "task-comment":
        if value := client_template or client_comment_template():
            if not settings.valid(key, value):
                raise ValueError("Invalid task comment template path from client settings")
            relative_to = top if not Path(value).expanduser().is_absolute() else None
            return "client", migrated_path(settings.template_path(value, relative_to), top)
    if custom := configured(settings.user_path(), key):
        return "user", migrated_path(custom, top)
    if native_git:
        return "git", native_git
    return "default", PLUGIN / "templates" / default


def main():
    parser = argparse.ArgumentParser(description="Get the effective Ready Check commit, PR or task-comment template.")
    parser.add_argument("kind", choices=KINDS)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--client-template", help="Task-comment template path supplied by the client hook")
    args = parser.parse_args()
    result = dict(schema_version=1, action="template", kind=args.kind, status="FAIL")
    try:
        top = toplevel(args.project) if args.project else None
        if args.project and top is None:
            raise ValueError("Project templates need a Git work tree")
        if args.client_template is not None and args.kind != "task-comment":
            raise ValueError("--client-template applies only to task comments")
        source, path = select(args.kind, top, args.client_template)
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
