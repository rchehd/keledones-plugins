import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


PLUGIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN / "scripts"))
from process_support import execute


def digest_tree(directory):
    return {path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob("*") if path.is_file()}


def main():
    parser = argparse.ArgumentParser(description="Test native Claude plugin coexistence in an isolated configuration.")
    parser.add_argument("--report-dir", type=Path)
    args = parser.parse_args()
    if not shutil.which("claude"):
        raise RuntimeError("This optional smoke test needs an existing Claude CLI; it does not install a harness")
    reports = args.report_dir.resolve() if args.report_dir else Path(tempfile.mkdtemp(prefix="ready-check-plugin-report."))
    if reports.is_relative_to(PLUGIN):
        raise ValueError("Save smoke reports outside the plugin checkout")
    reports.mkdir(parents=True, exist_ok=True)
    protected = [Path.home() / path for path in (".claude.json", ".claude/settings.json", ".claude/plugins/installed_plugins.json",
                 ".claude/plugins/known_marketplaces.json", ".codex/config.toml", ".cursor/cli-config.json")]
    before_global = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None for path in protected}
    with tempfile.TemporaryDirectory(prefix="ready-check-plugin-coexistence.") as temporary:
        root = Path(temporary)
        config, companion = root / "claude-config", root / "companion"
        (companion / ".claude-plugin").mkdir(parents=True)
        (companion / ".claude-plugin/plugin.json").write_text(json.dumps(dict(name="companion-toolkit", version="1.0.0")))
        (companion / ".claude-plugin/marketplace.json").write_text(json.dumps(dict(name="companion-marketplace",
            owner=dict(name="Fixture"), plugins=[dict(name="companion-toolkit", source="./")])))
        (companion / "skills/setup").mkdir(parents=True)
        (companion / "skills/setup/SKILL.md").write_text("---\nname: setup\ndescription: Companion toolkit setup fixture.\n---\n\nKeep the companion toolkit installed.\n")
        config.mkdir()
        sentinel = dict(language="ukrainian", env=dict(COMPANION_SETTING="preserve"))
        (config / "settings.json").write_text(json.dumps(sentinel))
        env = dict(os.environ, CLAUDE_CONFIG_DIR=str(config), CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1")
        counter = 0

        def call(*args):
            nonlocal counter
            counter += 1
            code, stdout, stderr = execute(["claude", *args], root, timeout=60, env=env)
            (reports / f"command-{counter:02}.log").write_bytes(stdout + b"\n" + stderr)
            if code:
                raise RuntimeError(f"Claude {' '.join(args)} failed; see command-{counter:02}.log")
            return stdout.decode(encoding="utf-8")

        companion_id = "companion-toolkit@companion-marketplace"
        ready_check_id = "ready@keledones"
        call("plugin", "marketplace", "add", str(companion))
        call("plugin", "install", companion_id, "--scope", "user")
        registry = config / "plugins/installed_plugins.json"
        original_entry = json.loads(registry.read_bytes())["plugins"][companion_id]
        original_marketplace = json.loads((config / "plugins/known_marketplaces.json").read_bytes())["companion-marketplace"]
        companion_cache = Path(original_entry[0]["installPath"])
        original_cache = digest_tree(companion_cache)
        data = config / "plugins/data" / companion_id
        data.mkdir(parents=True)
        (data / "sentinel.txt").write_bytes(b"Companion persistent data\n")

        def verify_companion():
            if json.loads(registry.read_bytes())["plugins"].get(companion_id) != original_entry:
                raise RuntimeError("Companion plugin registry entry changed")
            if digest_tree(companion_cache) != original_cache or (data / "sentinel.txt").read_bytes() != b"Companion persistent data\n":
                raise RuntimeError("Companion cached skills or persistent data changed")
            settings = json.loads((config / "settings.json").read_bytes())
            if any(settings.get(key) != value for key, value in sentinel.items()) or not settings["enabledPlugins"].get(companion_id):
                raise RuntimeError("Existing settings or companion enabled state changed")
            if json.loads((config / "plugins/known_marketplaces.json").read_bytes())["companion-marketplace"] != original_marketplace:
                raise RuntimeError("Companion marketplace registration changed")

        call("plugin", "marketplace", "add", str(PLUGIN.parent.parent))
        call("plugin", "install", ready_check_id, "--scope", "user")
        verify_companion()
        call("plugin", "list", "--json")
        call("plugin", "install", ready_check_id, "--scope", "user")
        verify_companion()
        call("plugin", "uninstall", ready_check_id, "--scope", "user")
        verify_companion()
        if ready_check_id in json.loads(registry.read_bytes())["plugins"]:
            raise RuntimeError("Ready Check uninstall left an active registry entry")
        call("plugin", "list", "--json")
    after_global = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None for path in protected}
    if after_global != before_global:
        raise RuntimeError("Global client configuration changed during the isolated smoke test")
    result = dict(status="PASS", native_client="Claude Code", companion_registry="unchanged", companion_cache="unchanged",
                  companion_data="unchanged", existing_settings="preserved", global_configuration="unchanged", commands=counter)
    (reports / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(result, reports=str(reports)), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
