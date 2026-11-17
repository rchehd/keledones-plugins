import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import detect
import settings
from project import toplevel

FIELDS = ("profile", "runner", "application")


def selection(item):
    return {key: item[key] for key in FIELDS}


def argument(item):
    return ":".join(item[key] for key in FIELDS)


def parse_argument(value):
    parts = value.split(":", 2)
    if len(parts) != len(FIELDS):
        raise ValueError("Use --selection PROFILE:RUNNER:APPLICATION")
    return dict(zip(FIELDS, parts))


def describe(top, item, source, manifest, evidence):
    directory = settings.application_root(top, item["application"])
    return dict(item, source=source, evidence=evidence, name=detect.profile_name(item["profile"]),
                version=detect.profile_version(directory, item["profile"]),
                framework=detect.framework(directory, manifest))


def discover(project):
    project = Path(project).resolve(strict=True)
    top = toplevel(project) or project
    if not project.is_dir():
        raise ValueError("A project directory is required")
    manifests = {manifest["id"]: manifest for manifest in detect.profiles()}
    configured = settings.configured_profiles(top)
    if configured:
        selected = [describe(top, item, "config", manifests[item["profile"]],
                             detect.evidence(settings.application_root(top, item["application"]), manifests[item["profile"]]))
                    for item in configured]
        return top, [item for item in selected if (top / item["application"]).is_relative_to(project)], []

    preferences = settings.shared_config(top) | settings.read(settings.project_path(top))
    explicit = preferences.get("application")
    roots = [settings.application_root(top, explicit)] if explicit is not None else detect.application_roots(top, manifests.values())
    selected, conflicts = [], []
    for directory in roots:
        if not directory.is_relative_to(project):
            continue
        application = directory.relative_to(top).as_posix()
        local = settings.shared_config(directory)
        matches = {}
        for profile, manifest in manifests.items():
            evidence = detect.evidence(directory, manifest, top if explicit is None else None)
            if evidence or local.get("profile") == profile:
                matches[profile] = evidence
        php = [profile for profile in matches if manifests[profile]["detection"].get("composer_packages")]
        if "profile" in local:
            if not settings.valid("profile", local["profile"]):
                raise ValueError(f"Invalid profile in {application}/.ready-check.json")
            php = []
            matches = {local["profile"]: matches[local["profile"]]}
        elif len(php) > 1:
            conflicts.append(dict(application=application, profiles=php))
        for profile, evidence in matches.items():
            runner = (local.get("runner") or preferences.get("runner") or
                      ("local" if profile == detect.FALLBACK else detect.runner(directory, directory)))
            if not settings.valid("runner", runner):
                raise ValueError(f"Invalid runner in project configuration for {application}")
            item = dict(profile=profile, application=application, runner=runner)
            selected.append(describe(top, item, "detected" if evidence else "config", manifests[profile], evidence))
    if not selected and (explicit is None or roots[0].is_relative_to(project)):
        directory = roots[0] if explicit is not None else project
        profile = detect.FALLBACK
        runner = settings.shared_config(directory).get("runner") or preferences.get("runner") or "local"
        if not settings.valid("runner", runner):
            raise ValueError("Invalid runner in project configuration")
        item = dict(profile=profile, application=directory.relative_to(top).as_posix(), runner=runner)
        selected.append(describe(top, item, "fallback", manifests[profile], []))
    return top, selected, conflicts


def main():
    parser = argparse.ArgumentParser(description="List Ready Check profiles, application roots and runners.")
    parser.add_argument("--project", type=Path, required=True)
    args = parser.parse_args()
    result = dict(schema_version=1, action="profiles", status="INCOMPLETE", profiles=[], conflicts=[])
    try:
        top, profiles, conflicts = discover(args.project)
        result.update(repository=str(top), profiles=profiles, conflicts=conflicts)
        if profiles and not conflicts:
            result["status"] = "PASS"
        elif not conflicts:
            result["reason"] = "No configured profile for the requested scope"
    except (OSError, ValueError) as error:
        result["reason"] = str(error)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 2
