#!/usr/bin/env python3
import os
import sys

sys.dont_write_bytecode = True
from process_support import execute, node_entry
from dependency_support import PLUGIN, bundle_path, data_root, installed


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
        code, stdout, stderr = execute(["node", str(binary), *sys.argv[1:]], os.getcwd(), timeout=180, env=env)
        sys.stdout.buffer.write(stdout)
        sys.stderr.buffer.write(stderr)
        return code
    except (OSError, ValueError) as error:
        print(f"Cannot run managed Playwright CLI: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
