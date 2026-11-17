import json
import re
from pathlib import Path

PROFILES = Path(__file__).resolve().parent.parent / "profiles"
COMPOSE = ("docker-compose.dev.yml", "docker-compose.yml", "docker-compose.yaml", "compose.yaml", "compose.yml")
SKIPPED = {"vendor", "node_modules"}
DEFAULT_PRIORITY = 50
FALLBACK = "generic"


def read_json(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def profiles():
    found = []

    for folder in sorted(PROFILES.glob("*/profile.json")):
        manifest = read_json(folder)

        if manifest and isinstance(manifest.get("id"), str) and isinstance(manifest.get("detection"), dict):
            found.append(manifest)

    return sorted(found, key=lambda m: (m.get("priority", DEFAULT_PRIORITY), m["id"]))


def profile_name(profile):
    manifest = next((m for m in profiles() if m["id"] == profile), None)
    return manifest.get("name") if manifest and manifest.get("name") else str(profile).capitalize()


def matches(directory, manifest):
    rules = manifest["detection"]
    required = (read_json(directory / "composer.json") or {}).get("require")
    packages = set(rules.get("composer_packages") or [])

    if isinstance(required, dict) and packages & set(required):
        return True

    return any((directory / path).is_file() for path in (*(rules.get("files") or []), *(rules.get("core_paths") or [])))


def detected(directory):
    return next((m["id"] for m in profiles() if matches(directory, m)), None)


def python_dependencies(directory):
    texts = [p.read_text(encoding="utf-8", errors="replace") for p in sorted(directory.glob("requirements*.txt")) + [directory / "pyproject.toml", directory / "Pipfile"]
             if p.is_file()]
    names = set()

    for text in texts:
        names.update(m.lower().replace("_", "-") for m in re.findall(r"(?im)(?:^|[\"'\s,\[])([a-z][a-z0-9._-]*)(?=\s*(?:[<>=!~\[;\"',\]]|$))", text))

    return names


def framework(directory, manifest):
    rules = (manifest.get("detection") or {}).get("frameworks") or {}
    packages = python_dependencies(directory) if any(r.get("python_packages") for r in rules.values()) else set()

    for name, rule in rules.items():
        if any((directory / path).is_file() for path in rule.get("files") or []) or packages & set(rule.get("python_packages") or []):
            return name

    return None


def profile_version(application, profile):
    manifest = next((m for m in profiles() if m["id"] == profile), None)
    lock = read_json(application / "composer.lock") or {}
    names = (manifest or {}).get("detection", {}).get("composer_packages") or []

    for name in names:
        for package in lock.get("packages") or []:
            if isinstance(package, dict) and package.get("name") == name:
                version = str(package.get("version", "")).lstrip("v")
                return version.split(".")[0] if version[:1].isdigit() else None

    return None


def runner(top, application):
    for directory in dict.fromkeys((application, top)):
        if (directory / ".ddev/config.yaml").is_file():
            return "ddev"

        if any((directory / name).is_file() for name in COMPOSE):
            return "compose"

    return "local"


def candidates(top):
    if detected(top):
        return ["."]

    try:
        children = sorted(child for child in top.iterdir() if child.is_dir())
    except OSError:
        return []

    return [child.name for child in children
            if not child.name.startswith(".") and child.name not in SKIPPED and detected(child)]


def detect(top):
    top = Path(top)
    result = dict(profile=None, name=None, version=None, runner=None, application=".", source="detected", ambiguous=False)
    found = candidates(top)

    if len(found) == 1:
        result.update(profile=detected(top / found[0]), application=found[0])
    elif len(found) > 1:
        result["ambiguous"] = True

    config = read_json(top / ".ready-check.json")

    if config is not None:
        result["source"] = "config"

        for key in ("profile", "runner", "application"):
            if isinstance(config.get(key), str) and config[key]:
                result[key] = config[key]
                if key in {"profile", "application"}:
                    result["ambiguous"] = False

        if config.get("application") and not config.get("profile"):
            result["profile"] = detected(top / result["application"])

    if not result["profile"] and not result["ambiguous"]:
        result["profile"] = FALLBACK

    application = top / result["application"]

    if result["profile"]:
        result["version"] = profile_version(application, result["profile"])
        result["name"] = profile_name(result["profile"])
        manifest = next((m for m in profiles() if m["id"] == result["profile"]), {})

        if (manifest.get("detection") or {}).get("frameworks"):
            result["framework"] = framework(application, manifest)

    result["runner"] = result["runner"] or ("local" if result["profile"] == FALLBACK else runner(top, application))
    return result
