#!/usr/bin/env python3
"""Check that every plugin in plugins/ is listed in the catalog of each client it has a manifest for."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "keledones"
CATALOGS = {
    "claude": (".claude-plugin/marketplace.json", ".claude-plugin/plugin.json"),
    "codex": (".agents/plugins/marketplace.json", ".codex-plugin/plugin.json"),
    "cursor": (".cursor-plugin/marketplace.json", ".cursor-plugin/plugin.json"),
}


def read_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"{path.relative_to(ROOT)}: {error}")

    if not isinstance(data, dict):
        raise ValueError(f"{path.relative_to(ROOT)}: expected a JSON object")

    return data


def plugin_directory(client, entry):
    source = entry.get("source")

    if client == "codex":
        if not isinstance(source, dict) or source.get("source") != "local":
            raise ValueError(f"{client}: {entry.get('name')} must use a local source")
        source = source.get("path")

    if not isinstance(source, str) or not source or Path(source).is_absolute() or ".." in Path(source).parts:
        raise ValueError(f"{client}: {entry.get('name')} needs a relative source inside the repository")
    directory = (ROOT / source).resolve()

    if directory.parent != (ROOT / "plugins").resolve() or not directory.is_dir():
        raise ValueError(f"{client}: {entry.get('name')} must point to an existing folder in plugins/")

    return directory


def check_catalog(client):
    catalog, manifest = CATALOGS[client]
    data = read_json(ROOT / catalog)

    if data.get("name") != NAME:
        raise ValueError(f"{catalog}: the catalog name must be {NAME}")
    entries = data.get("plugins")

    if not isinstance(entries, list) or not entries:
        raise ValueError(f"{catalog}: no plugins listed")
    found = {}

    for entry in entries:
        name = entry.get("name") if isinstance(entry, dict) else None

        if not name or name in found:
            raise ValueError(f"{catalog}: missing or duplicate plugin name {name!r}")
        directory = plugin_directory(client, entry)

        if read_json(directory / manifest).get("name") != name:
            raise ValueError(f"{catalog}: {name} differs from the name in {directory.name}/{manifest}")
        found[name] = directory.name

    return found


def validate():
    listed = {client: check_catalog(client) for client in CATALOGS}
    plugins = {}

    for client, found in listed.items():
        for name, folder in found.items():
            if plugins.setdefault(folder, (name, []))[0] != name:
                raise ValueError(f"plugins/{folder} is listed under two names: {plugins[folder][0]} and {name}")
            plugins[folder][1].append(client)

    for path in sorted(p for p in (ROOT / "plugins").iterdir() if p.is_dir()):
        clients = [client for client, (_, manifest) in CATALOGS.items() if (path / manifest).is_file()]

        if not clients:
            raise ValueError(f"plugins/{path.name} has no plugin manifest")

        for client in clients:
            if client not in plugins.get(path.name, ("", []))[1]:
                raise ValueError(f"plugins/{path.name} has a {client} manifest but is missing from the {client} catalog")

    return plugins


def main():
    try:
        plugins = validate()
    except ValueError as error:
        print(f"FAIL: {error}")
        return 1

    print("PASS: " + "; ".join(f"{name} (plugins/{folder}: {', '.join(clients)})"
                                for folder, (name, clients) in sorted(plugins.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
