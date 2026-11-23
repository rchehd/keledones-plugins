import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core_checks import Parser
from php_runtime import is_php, php


def files_report(tool):
    def report(lint, data):
        reported = False
        entries = data["files"]

        if entries == []:
            entries = {}

        for file, entry in entries.items():
            for item in entry["messages"]:
                reported = True
                identifier = item.get("source") or item.get("identifier") or tool

                if tool == "deadcode" and not identifier.startswith("shipmonk.dead"):
                    continue

                lint.add(file, item.get("line"), item["message"],
                         "warning" if tool == "deadcode" else item.get("type", "error"), identifier, True)

        if data.get("errors"):
            raise ValueError("; ".join(map(str, data["errors"])))

        return reported

    return report


def phpmd_report(lint, data):
    reported = False

    for entry in data["files"]:
        for item in entry["violations"]:
            reported = True
            begin = item["beginLine"]
            scope = lint.lines.get(lint.relative(entry["file"]))
            span = range(begin, int(item.get("endLine") or begin) + 1)
            line = next((n for n in span if scope is None or n in scope), begin)
            lint.add(entry["file"], line, item["description"], "warning", item.get("rule"), True)

    if data.get("errors"):
        raise ValueError(str(data["errors"]))

    return reported


PARSERS = {"phpcs": Parser({0, 1, 2, 3}, "{", files_report("phpcs")), "phpstan": Parser({0, 1}, "{", files_report("phpstan")),
           "deadcode": Parser({0, 1}, "{", files_report("deadcode")), "phpmd": Parser({0, 2}, "{", phpmd_report)}


def syntax(lint):
    for file in lint.files:
        suffix = Path(file).suffix

        if is_php(lint.spec, file):
            code, stdout, stderr = lint.call(["php", "-l", lint.runner.path(file)])
            text = (stdout + stderr).decode(errors="replace")

            if code:
                if "Errors parsing" in text:
                    line = re.search(r" on line (\d+)", text)
                    lint.add(file, line[1] if line else 0, text.strip())
                else:
                    lint.incomplete.append(f"PHP syntax process failed for {file} ({code})")
        elif suffix in {".yml", ".yaml"}:
            script = ('require $argv[1]; $y=$argv[3]; try { $y::parseFile($argv[2], (int)$argv[5]); echo "[]"; } '
                      'catch(Throwable $e) { if(!($e instanceof $argv[4])) { fwrite(STDERR,$e->getMessage()); exit(2); } '
                      'echo json_encode([$e->getMessage()]); }')
            code, stdout, _ = lint.call(["php", "-r", script, "--", lint.selected["environment"]["LINT_YAML_AUTOLOAD"], lint.runner.path(file),
                                        lint.spec.yaml["parser"], lint.spec.yaml["exception"], lint.spec.yaml.get("flags", 0)])

            if code:
                lint.incomplete.append(f"YAML parser failed for {file} ({code})")
            else:
                messages = json.loads(stdout)

                if not isinstance(messages, list):
                    raise ValueError("Invalid YAML parser result")

                for message in messages:
                    lint.add(file, 0, message)

def phpcs(lint):
    groups = {}

    for file in lint.files:
        if not is_php(lint.spec, file):
            continue
        parent = (lint.project / file).parent
        config = None

        while parent.is_relative_to(lint.project):
            config = next((p for p in (parent / n for n in ("phpcs.xml", ".phpcs.xml", "phpcs.xml.dist", ".phpcs.xml.dist")) if p.is_file()), None)

            if config or parent == lint.project:
                break
            parent = parent.parent
        groups.setdefault(config, []).append(file)

    for index, (config, files) in enumerate(groups.items()):
        root = ET.Element("ruleset", name="Ready Check")

        if config:
            ET.SubElement(root, "rule", ref=lint.runner.path(config.relative_to(lint.project).as_posix()))
        else:
            ET.SubElement(root, "arg", name="extensions", value=lint.spec.phpcs["extensions"])

            for standard in lint.spec.phpcs["standards"]:
                ET.SubElement(root, "rule", ref=standard)
            rule = ET.SubElement(root, "rule", ref="PSR12.ControlStructures.BooleanOperatorPlacement")
            ET.SubElement(ET.SubElement(rule, "properties"), "property", name="allowOnly", value="last")
        vendor = lint.binary("phpcs").rsplit("/vendor/bin/", 1)[0] + "/vendor"

        if not config and lint.runner.exists(vendor + "/slevomat", "dir"):
            rule = ET.SubElement(root, "rule", ref="SlevomatCodingStandard.ControlStructures.BlockControlStructureSpacing")
            ET.SubElement(rule, "type").text = "warning"

        if lint.runner.exists(vendor + "/phpcompatibility", "dir"):
            ET.SubElement(root, "rule", ref="PHPCompatibility")
            version = php(lint.runner, 'echo PHP_MAJOR_VERSION.".".PHP_MINOR_VERSION;')
            ET.SubElement(root, "config", name="testVersion", value=version + "-")
        config_path = lint.temporary(f"phpcs-{index}.xml", ET.tostring(root, encoding="unicode"))
        lint.parse("phpcs", *lint.call([lint.binary("phpcs"), "-q", "--report=json", "--standard=" + config_path, *files]))

def phpstan(lint):
    tool = next(t for t in lint.selected["tools"] if t["name"] == "phpstan")
    configuration = tool["configuration"]
    config = lint.runner.path(configuration["path"]) if configuration["source"] == "project" else None
    paths = [file for file in lint.files if is_php(lint.spec, file)]

    if not paths:
        raise ValueError("No analysable PHP files")

    generated = None
    if not config:
        root = lint.selected["environment"]["LINT_PHPSTAN_TOOLS"]
        optional = [e for package, e in lint.spec.phpstan.get("optional_includes", ()) if lint.runner.exists(lint.runner.path("vendor", package), "dir")]
        includes = [root + "/vendor/" + p for p in (*lint.spec.phpstan["includes"], *optional)]
        generated = "includes:\n" + "".join("  - " + json.dumps(p) + "\n" for p in includes)
        generated += f"parameters:\n  level: {lint.spec.phpstan['level']}\n  reportUnmatchedIgnoredErrors: false\n"
        if lint.selected.get("fresh_analysis"):
            generated += f"  tmpDir: {json.dumps(lint.temporary_path('phpstan-cache'))}\n"
        config = lint.temporary("phpstan.neon", generated)
    args = [tool["path"], "analyse", "-c", config, "--error-format=json", "--no-progress", "--memory-limit=-1"]

    if tool["source"] != "project":
        args += ["-a", lint.runner.path("vendor/autoload.php")]

    if os.environ.get("LINT_LEVEL"):
        args += ["--level=" + os.environ["LINT_LEVEL"]]
    result = lint.call([*args, *paths])
    handle_report = lint.spec.phpstan.get("handle_report")
    if handle_report:
        handle_report(lint, result, args, paths, generated if tool["source"] == "profile" else None)
    else:
        lint.parse("phpstan", *result)

def composer(lint):
    for directory in sorted({Path(f).parent.as_posix() for f in lint.files if Path(f).name in {"composer.json", "composer.lock"}}):
        code, stdout, stderr = lint.call(["composer", "validate", "--no-check-publish", "--no-interaction"], cwd=lint.runner.path(directory))

        if code not in {0, 1, 2}:
            lint.incomplete.append(f"Composer validate failed ({code})")
        elif code:
            lint.add(directory + "/composer.json", 0, (stdout + stderr).decode(errors="replace").strip())

def audit(lint):
    for file in (f for f in lint.files if Path(f).name == "composer.lock"):
        code, stdout, _ = lint.call(["composer", "audit", "--locked", "--no-interaction", "--format=json"], cwd=lint.runner.path(Path(file).parent.as_posix()))
        data = json.loads(stdout)
        start = len(lint.findings)

        if not isinstance(data, dict) or "advisories" not in data:
            raise ValueError("Composer audit returned an invalid report")
        advisories = data["advisories"] or {}

        for package, items in advisories.items() if isinstance(advisories, dict) else []:
            for item in items:
                lint.add(file, 0, f"{package}: {item.get('title', '')} ({item.get('cve') or item.get('advisoryId', '')})", "warning")

        for package in data.get("abandoned") or {}:
            lint.add(file, 0, f"{package}: abandoned dependency", "warning")

        if code not in range(8) or code and len(lint.findings) == start:
            lint.incomplete.append(f"Composer audit did not complete ({code})")

def phpmd(lint):
    tool = next(t for t in lint.selected["tools"] if t["name"] == "phpmd")
    conf = tool["configuration"]
    config = lint.runner.path(conf["path"]) if conf["source"] == "project" else lint.temporary("phpmd.xml",
        lint.spec.phpmd["ruleset"])
    files = [f for f in lint.files if is_php(lint.spec, f)]

    if any("," in f for f in files):
        raise ValueError("PHPMD cannot represent comma characters in source filenames")
    lint.parse("phpmd", *lint.call([tool["path"], ",".join(files), "json", config, "--suffixes", lint.spec.phpmd["suffixes"]]))

def deadcode(lint):
    root = lint.selected["environment"]["LINT_PHPSTAN_TOOLS"]

    if not lint.custom:
        raise ValueError("Dead-code analysis needs custom-code directories")
    config = lint.temporary("deadcode.neon", "includes:\n" + "".join("  - " + json.dumps(root + "/vendor/" + p) + "\n" for p in
        (lint.spec.phpstan["extension"], "shipmonk/dead-code-detector/rules.neon")) + "parameters:\n  level: 0\n")
    lint.parse("deadcode", *lint.call([lint.binary("phpstan"), "analyse", "-a", lint.runner.path("vendor/autoload.php"), "-c", config,
                                      "--error-format=json", "--no-progress", "--memory-limit=-1", *lint.custom]))


CHECKS = dict(syntax=syntax, phpcs=phpcs, phpstan=phpstan, composer=composer, audit=audit, phpmd=phpmd, deadcode=deadcode)
