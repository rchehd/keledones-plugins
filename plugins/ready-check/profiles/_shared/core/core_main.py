import argparse
import hashlib
import json
import sys
import tempfile
from functools import partial
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core_checks import CORE_CHECKS, run_check
from core_runner import Runner
from core_scope import changed_lines, lint_files, snapshot
from core_toolchain import JS, STYLES, node_config, select
from settings import project_config

STATUS_CODES = {"PASS": 0, "N/A": 0, "FAIL": 1, "INCOMPLETE": 2, "READY": 0, "MISSING": 2}


def applicable(files, spec):
    paths = [Path(p) for p in files]
    extensions = {p.suffix for p in paths}
    code = bool(extensions & (JS | spec.code_extensions))
    result = {"debug": code, "diff": any(p.suffix not in {".md", ".patch", ".diff"} for p in paths),
              "js": bool(extensions & (JS | STYLES)), "dup": code or bool(extensions & STYLES)}

    for provider in spec.providers:
        result.update(provider.applies(files, spec))

    result.update({name: bool(extra.applies(paths)) for name, extra in spec.extra_checks.items()})

    return result


def dependencies(check, project, files, runner, core, spec):
    if any((project / name).is_symlink() for name in files):
        raise ValueError("Changed symlinks require a separately agreed verification scope")

    provider = next((p for p in spec.providers if p.claims(check, spec)), None)

    planner = getattr(spec.extra_checks.get(check), "plan", None)

    if check in {"debug", "diff"} or check in spec.extra_checks and not provider and not planner:
        return dict(tools=[], environment={})

    if not runner.available():
        raise ValueError(f"Runner {runner.name} is unavailable; start or configure the intended environment")

    config = partial(node_config, core=core, ignored=spec.core_configs)

    if check in CORE_CHECKS:
        if check == "js" and not runner.command_available("node"):
            raise ValueError("Node.js is missing in the selected runner")

        return select(check, project, files, runner, config, spec)

    if planner and not provider:
        return planner(check, project, files, runner, spec)

    if not provider:
        raise ValueError(f"Check {check} is not implemented by this profile")

    return provider.plan(check, project, files, runner, config, spec)


def verify_bootstrap_files(recovery, runner):
    digests = recovery.get("sha256") if isinstance(recovery, dict) else None
    if not isinstance(digests, dict) or len(digests) != 2:
        raise ValueError("Missing bootstrap file hashes in saved static report; repeat static checks")
    for name, expected in digests.items():
        relative = Path(name)
        if (not name or relative.is_absolute() or relative.drive or ".." in relative.parts or "\\" in name
                or relative.as_posix() != name):
            raise ValueError("Invalid bootstrap file path in saved static report")
        source = runner.project / relative
        runner_path = runner.path(name)
        try:
            match = (source.is_file() and source.resolve() == source and runner.realpath(runner_path) == runner_path
                     and hashlib.sha256(runner.read(runner_path)).hexdigest() == expected)
        except (OSError, RuntimeError, ValueError):
            match = False
        if not match:
            raise ValueError(f"Bootstrap file changed or is unavailable: {name}. Repeat static checks")


def verify_static_result(path, current, runner):
    saved = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(saved, dict) or saved.get("schema_version") != 1 or saved.get("action") != "static"
            or saved.get("status") not in {"PASS", "N/A"} or saved.get("can_proceed") is not True
            or not isinstance(saved.get("checks"), list) or not isinstance(saved.get("scope"), dict)):
        raise ValueError("--static-result requires a successful static report")
    identity = ("profile", "profile_version", "runner")
    scope = ("project", "head", "merge_base", "snapshot")
    if (any(saved.get(key) != current[key] for key in identity)
            or any(saved["scope"].get(key) != current["scope"][key] for key in scope)):
        raise ValueError("Saved static scope or toolchain changed; repeat static checks for the current diff")

    recoveries = {}
    for check in saved["checks"]:
        if not isinstance(check, dict):
            raise ValueError("Invalid check in saved static report")
        if "bootstrap_recovery" not in check:
            continue
        recovery = check["bootstrap_recovery"]
        verify_bootstrap_files(recovery, runner)
        recoveries[check["id"]] = recovery
    return recoveries


def evidence_directory(base, prefix):
    if base:
        base.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix, dir=base))


def main(spec):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("doctor", "static"))
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--static-result", type=Path)
    parser.add_argument("--path", action="append")
    scope_group = parser.add_mutually_exclusive_group(required=True)
    scope_group.add_argument("--base")
    scope_group.add_argument("--commits", nargs="+")
    args = parser.parse_args()
    project = args.project.resolve()
    doctor = args.action == "doctor"
    profile = json.loads(spec.directory.joinpath("profile.json").read_text(encoding="utf-8"))
    result = dict(schema_version=1, action=args.action, profile=profile["id"], profile_version=profile["version"],
                  status="INCOMPLETE", host_platform=sys.platform, checks=[])

    if not doctor:
        result["can_proceed"] = False
    try:
        if args.static_result and not doctor:
            raise ValueError("--static-result is only available with doctor")
        core = spec.core_prefixes
        scope = snapshot(project, spec, args.base, args.commits, args.path)
        result["scope"] = scope
        runner = Runner(project, project_config(project, spec.id), spec.runner)
        result["runner"] = runner.name
        files = lint_files(scope["files"], core, spec)
        scope["excluded_files"] = sorted(set(scope["files"]) - set(files))
        apply = applicable(files, spec)
        plans = {}

        for definition in profile["checks"]:
            check = dict(id=definition["id"], required=definition["required"], findings=[], evidence=[])
            result["checks"].append(check)

            if not definition.get("enabled", True):
                check.update(status="N/A", reason="Opt-in check is disabled")
            elif check["id"] not in apply:
                check.update(status="MISSING" if doctor else "INCOMPLETE", reason="Check is not implemented by this profile")
            elif not apply[check["id"]]:
                check.update(status="N/A", reason="No applicable files in this diff")
            else:
                try:
                    selected = dependencies(check["id"], project, files, runner, core, spec)
                    plans[check["id"]] = selected
                    check.update(status="READY" if doctor else "PASS", tools=selected["tools"],
                                 reason="Tool prerequisites are available; code not checked")
                except (OSError, ValueError, TypeError, KeyError) as error:
                    check.update(status="MISSING" if doctor else "INCOMPLETE", reason=str(error))
        identity = json.dumps(plans, sort_keys=True).encode()
        scope["snapshot"] = hashlib.sha256(scope["snapshot"].encode() + identity).hexdigest()
        log_dir = None

        if not doctor:
            lines = changed_lines(project, scope, files) if plans else {}

            for check in result["checks"]:
                if check["id"] not in plans:
                    continue
                try:
                    if log_dir is None:
                        log_dir = evidence_directory(args.evidence_dir, "static-")
                        result["evidence_directory"] = str(log_dir)
                    check.update(run_check(check["id"], project, runner, log_dir, args.timeout,
                                           dict(plans[check["id"]], scope=scope),
                                           files, lines, scope["merge_base"], spec))
                except (OSError, ValueError, TypeError, KeyError) as error:
                    check.update(status="INCOMPLETE", reason=str(error))
        required = [c["status"] for c in result["checks"] if c["required"]]

        if doctor:
            status = "MISSING" if "MISSING" in required else "READY"
        else:
            status = "FAIL" if "FAIL" in required else "INCOMPLETE" if "INCOMPLETE" in required else "PASS" if "PASS" in required else "N/A"

        if args.static_result and status == "READY":
            recoveries = verify_static_result(args.static_result, result, runner)
            if recoveries:
                lines = changed_lines(project, scope, files)
                log_dir = evidence_directory(args.evidence_dir, "bootstrap-")
                result["evidence_directory"] = str(log_dir)
                result["bootstrap_verification"] = {}
                for check_id, saved in recoveries.items():
                    selected = dict(plans[check_id], scope=scope, fresh_analysis=True)
                    verified = run_check(check_id, project, runner, log_dir, args.timeout, selected,
                                         files, lines, scope["merge_base"], spec)
                    result["bootstrap_verification"][check_id] = verified
                    if verified["status"] != "PASS":
                        raise ValueError(f"Fresh {check_id} analysis did not pass. Review the findings and rerun static checks")
                    if verified.get("bootstrap_recovery", saved) != saved:
                        raise ValueError(f"The {check_id} bootstrap recovery changed. Repeat static checks")
                    verify_bootstrap_files(saved, runner)

        fresh_runner = Runner(project, project_config(project, spec.id), spec.runner)
        current_plans = {}

        for check in result["checks"]:
            if check["id"] in plans:
                try:
                    current_plans[check["id"]] = dependencies(check["id"], project, files, fresh_runner, core, spec)
                except (OSError, ValueError, TypeError, KeyError):
                    pass
        current_identity = json.dumps(current_plans, sort_keys=True).encode()
        current_snapshot = hashlib.sha256(snapshot(project, spec, args.base, args.commits, args.path)["snapshot"].encode() + current_identity).hexdigest()

        if current_snapshot != scope["snapshot"]:
            status = "INCOMPLETE"
            result["reason"] = "Code or toolchain changed during checks; repeat the checks for the current diff"
        elif args.static_result and status == "READY":
            result["verified_static_result"] = str(args.static_result)
        result["status"] = status

        if not doctor:
            result["can_proceed"] = status in {"PASS", "N/A"}
    except (OSError, ValueError, TypeError, KeyError) as error:
        result["reason"] = str(error)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return STATUS_CODES[result["status"]]
