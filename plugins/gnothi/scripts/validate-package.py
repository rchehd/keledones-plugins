#!/usr/bin/env python3
"""Check the Gnothi package: manifests, versions and the resources they point to."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PLUGIN = "gnothi"
ROOT = Path(__file__).resolve().parent.parent
MANIFESTS = (".claude-plugin", ".codex-plugin", ".cursor-plugin")
VERSION = re.compile(r"\d+\.\d+\.\d+")
RESOURCE_KEYS = ("icon", "logo", "composerIcon", "skills", "onboardingSkill")
SKILLS = ("setup", "portrait")
ICON = re.compile(r'icon_(?:small|large):\s*"([^"]+)"')


def resources(manifest):
    found = [manifest.get(key) for key in RESOURCE_KEYS]
    interface = manifest.get("interface") or {}
    found += [interface.get(key) for key in RESOURCE_KEYS]
    return [value for value in found if isinstance(value, str)]


def check_manifests(root):
    problems, versions = [], set()

    for folder in MANIFESTS:
        path = root / folder / "plugin.json"

        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            problems.append(f"{folder}/plugin.json: {error}")
            continue

        if manifest.get("name") != PLUGIN:
            problems.append(f"{folder}/plugin.json: name must be {PLUGIN}")
        version = manifest.get("version")

        if not isinstance(version, str) or not VERSION.fullmatch(version):
            problems.append(f"{folder}/plugin.json: version must be X.Y.Z")
        versions.add(version)

        if folder == ".codex-plugin":
            interface = manifest.get("interface")
            description = interface.get("longDescription") if isinstance(interface, dict) else None
            if not isinstance(description, str) or not description.strip():
                problems.append(f"{folder}/plugin.json: interface.longDescription must be non-blank text")
                continue
            capabilities = interface.get("capabilities")
            if not isinstance(capabilities, list) or any(not isinstance(item, str) for item in capabilities):
                problems.append(f"{folder}/plugin.json: interface.capabilities must be a list of strings")

        for relative in resources(manifest):
            target = (root / relative).resolve()

            if Path(relative).is_absolute() or not target.is_relative_to(root.resolve()):
                problems.append(f"{folder}/plugin.json: {relative} escapes the package")
            elif not target.exists():
                problems.append(f"{folder}/plugin.json: missing {relative}")

    if len(versions) > 1:
        problems.append("Manifest versions differ")

    return problems


def check_templates(root):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from profiles import validate_axes

    problems, found = [], sorted((root / "templates/axes").glob("*.json"))

    if not found:
        problems.append("templates/axes: no axis templates")

    for path in found:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            validate_axes(data.get("axes"))

            if not data.get("name") or not data.get("description"):
                raise ValueError("needs name and description")
        except (OSError, ValueError, AttributeError) as error:
            problems.append(f"templates/axes/{path.name}: {error}")

    return problems


def check_report(root):
    problems = []
    library = root / "report/vendor/chart.umd.min.js"

    for relative in ("report/style.css", "report/vendor/LICENSE.chart.js"):
        if not (root / relative).is_file():
            problems.append(f"missing {relative}")

    try:
        if not library.read_text(encoding="utf-8")[:40].startswith("/*!\n * Chart.js v4"):
            problems.append("report/vendor/chart.umd.min.js is not Chart.js 4")
    except OSError:
        problems.append("missing report/vendor/chart.umd.min.js")

    for relative in ("scripts/widget.py", "report/widget/THIRD_PARTY_NOTICES.md"):
        if not (root / relative).is_file():
            problems.append(f"missing {relative}")

    try:
        page = (root / "report/widget/portrait.html").read_text(encoding="utf-8")
        if page.count('<script id="portrait-data" type="application/json">null</script>') != 1:
            problems.append("Gnothi portrait widget requires one empty data placeholder")
        if re.search(r"""<script\b[^>]*\bsrc\s*=|<link\b[^>]*rel=['"]stylesheet|@import\s+(?:url\()?['"]?https?://""",
                     page, re.I):
            problems.append("Gnothi portrait widget must bundle its JavaScript and CSS locally")
    except OSError:
        problems.append("missing report/widget/portrait.html")

    return problems


def check_skills(root, names=SKILLS):
    problems = []

    for name in names:
        folder = root / "skills" / name

        try:
            text = (folder / "SKILL.md").read_text(encoding="utf-8")
        except OSError:
            problems.append(f"skills/{name}/SKILL.md: missing")
            continue

        if not text.startswith(f"---\nname: {name}\ndescription: "):
            problems.append(f"skills/{name}/SKILL.md: frontmatter must start with name {name} and a description")
        else:
            description = text.split("\n---", 1)[0].split("description: ", 1)[1]
            description = " ".join(description.removeprefix(">-").split())

            if not 0 < len(description) < 1024:
                problems.append(f"skills/{name}/SKILL.md: description must have 1 to 1023 characters")

        try:
            icons = ICON.findall((folder / "agents/openai.yaml").read_text(encoding="utf-8"))
        except OSError:
            problems.append(f"skills/{name}/agents/openai.yaml: missing")
            continue

        for icon in icons:
            if not (folder / icon).is_file():
                problems.append(f"skills/{name}: missing icon {icon}")

    return problems


def check(root):
    root = Path(root)
    return check_manifests(root) + check_templates(root) + check_report(root) + check_skills(root)


def main():
    problems = check(ROOT)

    for problem in problems:
        print(problem, file=sys.stderr)

    print("Package is valid" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
