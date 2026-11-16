#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


VERSION = re.compile(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?(?:\+[A-Za-z0-9.-]+)?")
PLUGIN = "ready"
NODE_TOOLS = {"eslint", "@eslint/js", "globals", "stylelint", "stylelint-config-standard-scss", "jscpd"}
PROFILE_TOOLS = {
    "drupal": dict(composer={"drupal/coder", "mglaman/phpstan-drupal", "phpstan/phpstan-deprecation-rules",
                             "vincentlanglet/twig-cs-fixer", "phpmd/phpmd", "symfony/yaml"}, node=NODE_TOOLS),
    "laravel": dict(composer={"larastan/larastan", "laravel/pint", "phpstan/phpstan", "phpmd/phpmd", "rector/rector",
                              "driftingly/rector-laravel", "symfony/yaml"}, node=NODE_TOOLS),
    "symfony": dict(composer={"friendsofphp/php-cs-fixer", "phpstan/phpstan", "phpstan/phpstan-symfony", "phpstan/phpstan-doctrine",
                              "phpmd/phpmd", "symfony/yaml"}, node=NODE_TOOLS),
    "python": dict(pip={"ruff", "mypy", "bandit", "pip-audit"}, node=NODE_TOOLS),
    "go": dict(go={"golangci-lint", "govulncheck"}, node=NODE_TOOLS),
}
SKILLS = {"setup", "check", "review", "qa", "uninstall", "customize", "feedback", "reflect", "contribute"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def resource(root, base, relative, directory=False):
    require(isinstance(relative, str) and relative and not Path(relative).is_absolute(), "Resource paths must be relative")
    path = (base / relative).resolve()
    require(path.is_relative_to(root), f"Resource escapes the package: {relative}")
    require(path.is_dir() if directory else path.is_file(), f"Missing resource: {relative}")
    return path


def read_json(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict), f"Expected JSON object: {path.name}")
    return data


def manifests(root):
    versions = set()
    for folder in (".cursor-plugin", ".claude-plugin", ".codex-plugin"):
        path = resource(root, root, folder + "/plugin.json")
        manifest = read_json(path)
        require(manifest.get("name") == PLUGIN, f"Wrong plugin ID in {folder}")
        version = manifest.get("version")
        require(isinstance(version, str) and VERSION.fullmatch(version), f"Invalid version in {folder}")
        versions.add(version)
        if folder != ".claude-plugin":
            require(resource(root, root, manifest.get("skills"), directory=True) == root / "skills",
                    f"{folder} must discover the shared skills directory")
        else:
            require("skills" not in manifest or manifest["skills"] == "./skills/", "Claude must use the shared skills directory")
        if folder == ".codex-plugin":
            onboarding = resource(root, root, manifest.get("onboardingSkill"))
            require(onboarding == root / "skills/setup/SKILL.md", "Codex onboarding must invoke the packaged setup skill")
    require(len(versions) == 1, "Plugin manifest versions must agree across all harnesses")
    return versions.pop()


def skills(root):
    folder = resource(root, root, "skills", directory=True)
    found = set()
    for child in sorted(folder.iterdir()):
        require(child.is_dir(), f"Unexpected file in skills/: {child.name}")
        path = resource(root, child, "SKILL.md")
        body = path.read_text(encoding="utf-8")
        frontmatter = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", body, re.S)
        require(frontmatter is not None, f"Missing skill frontmatter: {child.name}")
        fields = dict(re.findall(r"^([a-z][a-z-]*):\s*(.+)$", frontmatter[1], re.M))
        require(fields.get("name") == child.name, f"Skill ID differs from directory: {child.name}")
        require(bool(fields.get("description", "").strip()), f"Missing skill description: {child.name}")
        found.add(child.name)
    require(SKILLS <= found, "Missing a required Ready Check skill")
    return sorted(found)


def profiles(root):
    folder = resource(root, root, "profiles", directory=True)
    found = []
    for child in sorted(folder.iterdir()):
        if child.is_dir() and child.name.startswith("_"):
            continue
        require(child.is_dir(), f"Unexpected file in profiles/: {child.name}")
        manifest = read_json(resource(root, child, "profile.json"))
        require(manifest.get("schema_version") == 1 and manifest.get("id") == child.name,
                f"Invalid profile identity/schema: {child.name}")
        require(isinstance(manifest.get("version"), str) and VERSION.fullmatch(manifest["version"]),
                f"Invalid profile version: {child.name}")
        for group, keys in (("instructions", ("requirements", "static", "review", "qa")),
                            ("scripts", ("doctor", "static", "setup"))):
            mapping = manifest.get(group)
            require(isinstance(mapping, dict), f"Missing {group}: {child.name}")
            for key in keys:
                path = resource(root, child, mapping.get(key))
                require(path.is_relative_to(child.resolve()), f"Profile resource escapes {child.name}: {key}")
                require(path.suffix == (".py" if group == "scripts" else ".md"), f"Wrong resource type: {key}")
        checks = manifest.get("checks")
        require(isinstance(checks, list) and checks, f"Missing checks: {child.name}")
        ids = set()
        for check in checks:
            require(isinstance(check, dict) and isinstance(check.get("id"), str) and check["id"] not in ids,
                    f"Missing or duplicate check ID: {child.name}")
            require(type(check.get("required")) is bool, f"Check required flag must be boolean: {child.name}")
            ids.add(check["id"])
        found.append(child.name)
    require(set(PROFILE_TOOLS) <= set(found), "A required profile is missing: " + ", ".join(sorted(set(PROFILE_TOOLS) - set(found))))
    return found


def npm_lock(root, directory):
    manifest = read_json(resource(root, directory, "package.json"))
    lock = read_json(resource(root, directory, "package-lock.json"))
    dependencies = manifest.get("dependencies")
    require(isinstance(dependencies, dict) and dependencies, "Missing pinned npm dependencies")
    packages = lock.get("packages")
    require(isinstance(packages, dict) and isinstance(packages.get(""), dict), "Missing npm lock packages")
    require(packages[""].get("dependencies") == dependencies, "npm manifest and root lock dependencies differ")
    for name, version in dependencies.items():
        require(isinstance(version, str) and VERSION.fullmatch(version), f"npm dependency must be pinned: {name}")
        require(packages.get("node_modules/" + name, {}).get("version") == version, f"Stale npm lock version: {name}")


def pip_tools(root, tools, need):
    for relative in ("eslint.config.mjs", "stylelint.config.json", "ruff.toml", "requirements.in"):
        resource(root, tools, relative)
    pinned = resource(root, tools, "requirements.txt").read_text(encoding="utf-8")
    declared = resource(root, tools, "requirements.in").read_text(encoding="utf-8")

    for package in need["pip"]:
        require(re.search(r"(?m)^" + re.escape(package) + r"==\S+ \\\n\s+--hash=sha256:[0-9a-f]{64}", pinned), f"Python tool must be pinned with hashes: {package}")
        require(re.search(r"(?m)^" + re.escape(package) + r"==\d", declared), f"Python tool must be pinned in requirements.in: {package}")
    require(all("--hash=" in block for block in re.split(r"(?m)^(?=\S)", pinned) if "==" in block.split("\n", 1)[0]),
            "Every Python requirement must carry hashes")


def go_tools(root, tools, need):
    for relative in ("eslint.config.mjs", "stylelint.config.json", "golangci.yml"):
        resource(root, tools, relative)
    require(re.search(r'(?m)^version: "2"$', resource(root, tools, "golangci.yml").read_text(encoding="utf-8")),
            "The default golangci-lint configuration must use the v2 format")
    manifest = read_json(resource(root, tools, "tools.json"))
    require(re.fullmatch(r"\d+\.\d+(?:\.\d+)?", str(manifest.get("go_minimum"))), "tools.json needs go_minimum")
    pinned = manifest.get("tools")
    require(isinstance(pinned, dict) and need["go"] <= pinned.keys(), "Go tools are missing in tools.json")

    for name in need["go"]:
        item = pinned[name]
        require(isinstance(item.get("module"), str) and "/" in item["module"], f"Go tool needs a module path: {name}")
        require(isinstance(item.get("version"), str) and re.fullmatch(r"v\d+\.\d+\.\d+", item["version"]),
                f"Go tool must be pinned to an exact version: {name}")
        require(re.fullmatch(r"h1:[A-Za-z0-9+/]{43}=", str(item.get("sum"))), f"Go tool needs a module checksum: {name}")


def dependencies(root):
    browser = resource(root, root, "dependencies/browser", directory=True)
    npm_lock(root, browser)
    require({"@playwright/cli", "@playwright/mcp"} <= read_json(browser / "package.json")["dependencies"].keys(),
            "Browser bundle needs Playwright CLI and official MCP")
    browser_lock = read_json(browser / "package-lock.json")["packages"]
    require(browser_lock["node_modules/@playwright/cli"]["dependencies"]["playwright-core"] ==
            browser_lock["node_modules/@playwright/mcp"]["dependencies"]["playwright-core"],
            "CLI and MCP must use the same pinned browser revision")
    folders = [browser]
    for name, need in PROFILE_TOOLS.items():
        tools = resource(root, root, f"profiles/{name}/tools", directory=True)
        folders.append(tools)
        npm_lock(root, tools)

        if "go" in need:
            go_tools(root, tools, need)
            require(need["node"] <= read_json(tools / "package.json")["dependencies"].keys(), f"{name} Node tools are missing")
            continue

        if "pip" in need:
            pip_tools(root, tools, need)
            require(need["node"] <= read_json(tools / "package.json")["dependencies"].keys(), f"{name} Node tools are missing")
            continue
        manifest = read_json(resource(root, tools, "composer.json"))
        require(need["composer"] <= manifest.get("require", {}).keys(), f"{name} Composer tools are missing")
        require(need["node"] <= read_json(tools / "package.json")["dependencies"].keys(), f"{name} Node tools are missing")
        for relative in ("eslint.config.mjs", "stylelint.config.json"):
            resource(root, tools, relative)
        lock = read_json(resource(root, tools, "composer.lock"))
        packages = lock.get("packages")
        require(isinstance(packages, list), "Composer lock packages are missing")
        locked = {package["name"]: package["version"].lstrip("v") for package in packages}
        for package, version in manifest.get("require", {}).items():
            if "/" in package:
                require(isinstance(version, str) and VERSION.fullmatch(version), f"Composer dependency must be pinned: {package}")
                require(locked.get(package) == version, f"Stale Composer lock version: {package}")
    for directory in (root, *folders):
        for generated in ("node_modules", "vendor"):
            require(not (directory / generated).exists(), "Runtime dependencies must remain outside the package: " + str(directory / generated))


def entry_points(root):
    for name in ("doctor.sh", "check-static.sh", "check-profile.py", "setup.sh", "setup.py", "dependency_support.py",
                 "process_support.py", "profile_runtime.py", "managed_storage.py", "git_exclude.py", "reports.py", "mcp.py", "mcp.mjs",
                 "ready-check.py", "playwright.sh", "playwright.py", "project.py", "settings.py", "detect.py", "logs.py",
                 "tasks.py", "hook.py", "hook_state.py", "fingerprint.py", "consent.py", "uninstall.py", "rules.py", "a11y.py", "customize.py", "summary.py", "feedback.py", "reflect_collect.py"):
        resource(root, root, "scripts/" + name)
    for name in ("session-rule.md", "first-run.md"):
        resource(root, root, "hooks/" + name)
    for name in ("CONTRIBUTING.md", "templates/improvement.md", "templates/bug.md"):
        resource(root, root, name)
    require(read_json(root / ".mcp.json").get("mcpServers", {}).get("ready-playwright"), "Claude must bundle the ready-playwright MCP server")
    for name in ("core_runner.py", "core_scope.py", "core_toolchain.py", "core_checks.py", "core_main.py", "core_setup.py"):
        resource(root, root, "profiles/_shared/core/" + name)
    for name in ("php_runtime.py", "php_toolchain.py", "php_lint.py", "php_provider.py", "php_setup.py"):
        resource(root, root, "profiles/_shared/php/" + name)
    for profile in PROFILE_TOOLS:
        for name in ("checks.py", "setup.py", "spec.py"):
            resource(root, root, f"profiles/{profile}/scripts/{name}")

    for name in ("python_lint.py", "python_setup.py", "python_tools.py"):
        resource(root, root, "profiles/python/scripts/" + name)

    for name in ("go_lint.py", "go_setup.py", "go_tools.py"):
        resource(root, root, "profiles/go/scripts/" + name)


def hooks(root):
    files = {"hooks/hooks.json": ("claude", {"SessionStart", "UserPromptSubmit", "Stop"}),
             "hooks/cursor-hooks.json": ("cursor", {"sessionStart", "beforeSubmitPrompt"}),
             "hooks/codex-hooks.json": ("codex", {"SessionStart", "UserPromptSubmit", "Stop"})}

    for relative, (client, events) in files.items():
        data = read_json(resource(root, root, relative))
        declared = data.get("hooks")
        require(isinstance(declared, dict) and set(declared) == events, f"Unexpected hook events in {relative}")

        for groups in declared.values():
            for group in groups:
                handlers = group.get("hooks", [group]) if client != "cursor" else [group]

                for handler in handlers:
                    command = handler.get("command", "")
                    require("scripts/ready-check.py\" hook " in command and f"--client {client}" in command,
                            f"Hook command must call the packaged hook entry: {relative}")

    for folder, relative in ((".cursor-plugin", "hooks/cursor-hooks.json"), (".codex-plugin", "hooks/codex-hooks.json")):
        manifest = read_json(root / folder / "plugin.json")
        require(resource(root, root, manifest.get("hooks")) == root / relative, f"{folder} must register {relative}")


def ignored(root):
    result = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--others", "--ignored", "--exclude-standard"],
                            capture_output=True)
    return {root / name for name in result.stdout.decode("utf-8").split("\0") if name} if result.returncode == 0 else set()


def links(root):
    skipped = ignored(root)
    for path in root.rglob("*.md"):
        if ".git" in path.relative_to(root).parts or path in skipped:
            continue
        require(path.resolve().is_relative_to(root), f"Markdown escapes package: {path}")
        body = path.read_text(encoding="utf-8")
        require(len(re.findall(r"^```", body, re.M)) % 2 == 0, f"Unclosed Markdown fence: {path.relative_to(root)}")
        for target in re.findall(r"\]\(([^)]+)\)", body):
            if "://" in target or target.startswith("#"):
                continue
            resource(root, path.parent, target.split("#", 1)[0])


def validate(root):
    result = dict(schema_version=1, action="validate-package", package=str(root), status="PASS", checks=[])
    operations = [("manifests", lambda: manifests(root)), ("skills", lambda: skills(root)), ("profiles", lambda: profiles(root)),
                  ("dependencies", lambda: dependencies(root)), ("entry-points", lambda: entry_points(root)), ("hooks", lambda: hooks(root)),
                  ("local-links", lambda: links(root))]
    for name, operation in operations:
        try:
            value = operation()
            check = dict(id=name, status="PASS")
            if value is not None:
                check["value"] = value
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
            check = dict(id=name, status="FAIL", reason=str(error))
            result["status"] = "FAIL"
        result["checks"].append(check)
    return result


def main():
    parser = argparse.ArgumentParser(description="Validate the Ready Check package offline, without installing or running a harness.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()
    result = validate(args.root.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
