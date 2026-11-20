#!/usr/bin/env python3
import argparse
import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True


def hook_fallback():
    # Hooks must never block the client: exit 0 and keep Cursor prompts allowed.
    if sys.argv[2:3] == ["prompt"] and "cursor" in sys.argv[3:]:
        print('{"continue": true}')
    return 0


def main():
    if sys.version_info < (3, 9):
        if sys.argv[1:2] == ["hook"]:
            return hook_fallback()
        print("Ready Check requires Python 3.9 or newer", file=sys.stderr)
        return 2
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Ready Check native entry point for Linux, macOS, Windows and WSL.")
    parser.add_argument("action", choices=("setup", "profiles", "doctor", "static", "playwright", "qa-gate", "qa-record", "qa-replay", "mcp", "validate-package", "reports", "config", "template", "tasks", "hook", "mark-checked", "offers", "consent", "uninstall", "rules", "a11y", "customize", "summary", "feedback", "reflect-collect", "publication"))
    args = parser.parse_args(sys.argv[1:2])
    remaining = sys.argv[2:]
    root = Path(__file__).resolve().parent
    filename = {"doctor": "check-profile.py", "static": "check-profile.py", "config": "settings.py", "template": "draft_template.py", "profiles": "profile_selection.py", "mark-checked": "fingerprint.py", "reflect-collect": "reflect_collect.py", "qa-replay": "qa-record.py"}.get(args.action, args.action + ".py")
    spec = importlib.util.spec_from_file_location("ready_check_entry", root / filename)
    module = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(module)
    except Exception:
        if args.action == "hook":
            return hook_fallback()
        raise

    sys.argv = [str(root / filename), *([args.action] if args.action in {"doctor", "static"} else []), *remaining]
    if args.action == "qa-replay":
        return module.replay_main()
    return module.main()


if __name__ == "__main__":
    sys.exit(main())
