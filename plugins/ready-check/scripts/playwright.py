#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from process_support import execute, launch_argv, node_entry
from dependency_support import PLUGIN, bundle_path, data_root, installed


def live_dir(value):
    path = Path(value).resolve()
    if not path.is_dir():
        raise ValueError("--qa-live-dir requires an existing private session directory and a Playwright command")

    if os.name != "nt":
        info = path.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("--qa-live-dir must be owned by the current user and closed to other users")
    return path


def main():
    source = PLUGIN / "dependencies/browser"
    root = data_root()
    folder = bundle_path(source, root, "browser")
    if not installed(source, folder):
        print(f"Managed Playwright CLI is unavailable; invoke ready:setup or run Python {PLUGIN / 'scripts/ready-check.py'} setup --component browser --project /path/to/application", file=sys.stderr)
        return 2
    env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(root / "browsers"))
    try:
        binary = node_entry(folder, "@playwright/cli", "playwright-cli")
        args = sys.argv[1:]
        if args[:1] == ["--qa-live-dir"]:
            if len(args) < 3:
                raise ValueError("--qa-live-dir requires an existing private session directory and a Playwright command")

            session_dir = live_dir(args[1])
            env.update(PWTEST_DAEMON_SESSION_DIR=str(session_dir), PWTEST_SOCKETS_DIR=str(session_dir),
                       PWTEST_SERVER_REGISTRY=str(session_dir / "registered-browsers"))
            args = args[2:]

            if args == ["show"]:
                dashboard = launch_argv(["node", binary, "show", "--host=127.0.0.1", "--port=0"], env)
                if os.name == "nt":
                    return subprocess.run(dashboard, env=env).returncode
                return os.execve(dashboard[0], dashboard, env)
        code, stdout, stderr = execute(["node", str(binary), *args], os.getcwd(), timeout=180, env=env)
        sys.stdout.buffer.write(stdout)
        sys.stderr.buffer.write(stderr)
        return code
    except (OSError, ValueError) as error:
        print(f"Cannot run managed Playwright CLI: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
