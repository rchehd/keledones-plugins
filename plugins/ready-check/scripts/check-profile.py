#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
from settings import project_config


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run a packaged framework profile without changing project code.")
    parser.add_argument("action", choices=("doctor", "static"))
    parser.add_argument("--profile", required=True)
    parser.add_argument("--project", required=True, type=Path)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--base")
    scope.add_argument("--commits", nargs="+")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    plugin = Path(__file__).resolve().parent.parent
    result = {"schema_version": 1, "action": args.action, "profile": args.profile,
              "status": "INCOMPLETE", "checks": []}
    if args.action == "static":
        result["can_proceed"] = False
    code = 2
    output = None
    try:
        project = args.project.resolve(strict=True)
        if not project.is_dir() or args.timeout <= 0:
            raise ValueError("A project directory and a positive timeout are required")
        if args.output:
            candidate = args.output.resolve()
            git = subprocess.run(["git", "-C", str(project), "rev-parse", "--show-toplevel"],
                                 capture_output=True, text=True, encoding="utf-8")
            forbidden = [plugin, project]
            if git.returncode == 0:
                forbidden.append(Path(git.stdout.strip()).resolve())
            allowed = [root / "ai/ready-check" for root in forbidden[1:]]
            inside = any(data.resolve() == data and candidate.is_relative_to(data) for data in allowed)
            if not inside and any(candidate.is_relative_to(root) for root in forbidden):
                raise ValueError("Save the result outside the project repository and plugin package, or in ai/ready-check")
            output = candidate
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", args.profile):
            raise ValueError("Invalid profile ID")
        folder = plugin / "profiles" / args.profile
        profile = json.loads((folder / "profile.json").read_text(encoding="utf-8"))
        if not isinstance(profile, dict) or profile.get("schema_version") != 1 or profile.get("id") != args.profile:
            raise ValueError("Unsupported or inconsistent profile manifest")
        if project_config(project).get("profile", args.profile) != args.profile:
            raise ValueError("Selected profile conflicts with the project's Ready Check configuration")
        entry = (folder / profile["scripts"][args.action]).resolve(strict=True)
        if not entry.is_relative_to(folder.resolve()) or entry.suffix != ".py":
            raise ValueError("Profile entry point must be a Python file inside the profile")
        argv = [sys.executable, str(entry), args.action, "--project", str(project), "--timeout", str(args.timeout)]
        if output:
            argv += ["--evidence-dir", str(output.parent / "evidence")]
        argv += ["--base", args.base] if args.base else ["--commits", *args.commits]
        process = subprocess.run(argv,
                                 cwd=project, capture_output=True, text=True, encoding="utf-8",
                                 env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        parsed = json.loads(process.stdout)
        if (not isinstance(parsed, dict) or parsed.get("schema_version") != 1 or parsed.get("action") != args.action
                or parsed.get("profile") != args.profile or not isinstance(parsed.get("checks"), list)):
            raise ValueError("Profile returned an invalid report")
        if args.action == "doctor":
            if "can_proceed" in parsed:
                raise ValueError("Doctor report must not contain a stage gate")
            expected = {"READY": 0, "MISSING": 2, "INCOMPLETE": 2}.get(parsed.get("status"))
        else:
            if type(parsed.get("can_proceed")) is not bool:
                raise ValueError("Profile returned an invalid report")
            expected = {"PASS": 0, "N/A": 0, "FAIL": 1, "INCOMPLETE": 2}.get(parsed.get("status"))
        if expected is None or process.returncode != expected:
            raise ValueError("Profile status and process exit code disagree")
        if args.action == "static" and parsed["can_proceed"] != (expected == 0):
            raise ValueError("Profile returned an inconsistent stage gate")
        result, code = parsed, expected
    except (OSError, ValueError, KeyError, TypeError) as error:
        result["reason"] = str(error)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if output:
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as stream:
                stream.write(text)
                temporary = Path(stream.name)
            temporary.replace(output)
        except OSError as error:
            result.update(status="INCOMPLETE", reason=f"Cannot save report: {error}")
            if args.action == "static":
                result["can_proceed"] = False
            text, code = json.dumps(result, ensure_ascii=False, indent=2) + "\n", 2
    sys.stdout.write(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
