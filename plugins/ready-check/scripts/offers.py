#!/usr/bin/env python3
import argparse
import json
import sys

import hook_state

CLIENTS = ("claude", "cursor", "codex")


def main():
    parser = argparse.ArgumentParser(description="Turn Ready Check offers off for one client session.")
    parser.add_argument("state", choices=("off",))
    parser.add_argument("--client", required=True, choices=CLIENTS)
    parser.add_argument("--session", required=True)
    args = parser.parse_args()
    result = dict(schema_version=1, action="offers", status="FAIL")

    try:
        hook_state.save(args.client, args.session, dict(hook_state.load(args.client, args.session), off=True))
        result.update(status="PASS", offers="off", client=args.client)
    except (OSError, ValueError) as error:
        result["reason"] = str(error)

    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
