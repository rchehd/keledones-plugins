import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from git_exclude import git
from process_support import find_command
from project import toplevel


PROVIDERS = {
    "github.com": "github",
    "gitlab.com": "gitlab",
}
SSH_HOSTS = {"ssh.github.com": "github.com", "altssh.gitlab.com": "gitlab.com"}


def repository(url):
    port = None
    if "://" in url:
        try:
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https", "ssh", "git"}:
                return None
            host, path = parsed.hostname, parsed.path.lstrip("/")
            if parsed.scheme in {"http", "https"} and parsed.port not in {None, 80 if parsed.scheme == "http" else 443}:
                port = parsed.port
        except ValueError:
            return None
    else:
        if re.match(r"^[a-zA-Z]:", url):
            return None
        match = re.fullmatch(r"(?:[^@/:]+@)?([^/:]+):([^/].*)", url)
        if not match:
            return None
        host, path = match.groups()
    if not host or not re.fullmatch(r"[a-zA-Z0-9.-]+", host):
        return None
    path = path.rstrip("/").removesuffix(".git")
    parts = path.split("/")
    if len(parts) < 2 or any(part in {".", ".."} or not re.fullmatch(r"[\w.-]+", part) for part in parts):
        return None
    host = host.lower()
    host = f"{host}:{port}" if port else SSH_HOSTS.get(host, host)
    return {"host": host, "path": path, "provider": PROVIDERS.get(host)}


def remote_repositories(top, remote, *options):
    urls = git(top, "remote", "get-url", "--all", *options, "--", remote) or ""
    return [repository(url) for url in urls.splitlines()]


def describe(top):
    remotes = {}
    for name in (git(top, "remote") or "").splitlines():
        prefix = f"refs/remotes/{name}/"
        head = git(top, "symbolic-ref", "--quiet", prefix + "HEAD")
        remotes[name] = {
            "fetch": remote_repositories(top, name),
            "push": remote_repositories(top, name, "--push"),
            "cachedDefaultBranch": head.removeprefix(prefix) if head and head.startswith(prefix) else None,
        }
    return {
        "branch": git(top, "symbolic-ref", "--quiet", "--short", "HEAD"),
        "upstream": git(top, "rev-parse", "--symbolic-full-name", "@{upstream}"),
        "remotes": remotes,
        "cliOnPath": {name: bool(find_command(name)) for name in ("gh", "glab")},
    }


def main():
    parser = argparse.ArgumentParser(description="Discover local Git and CLI context for PR/MR delivery.")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    top = toplevel(parser.parse_args().project)
    if not top:
        print(json.dumps({"error": "The project is not a Git worktree."}))
        return 1
    print(json.dumps(describe(top)))
    return 0
