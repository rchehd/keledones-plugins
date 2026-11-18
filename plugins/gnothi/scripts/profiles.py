from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import storage
from sessions import PERIODS

TEMPLATES = Path(__file__).resolve().parent.parent / "templates/axes"
ID = re.compile(r"[a-z0-9-]{2,32}")
OPTIONS = {"archetypes": False, "metrics_only": False, "period": "month"}


def path():
    return storage.data_root() / "profile.json"


def read():
    target = path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        data = {}
    except PermissionError as error:
        raise storage.StoragePermissionError(target, error) from error
    except (OSError, ValueError) as error:
        raise ValueError(f"{target} is unreadable ({error}); fix or remove it, nothing was changed")

    if not isinstance(data, dict):
        raise ValueError(f"{target} is not a Gnothi profile; fix or remove it, nothing was changed")

    return {"schema_version": 1, "epochs": data.get("epochs") or [], "options": dict(OPTIONS, **(data.get("options") or {}))}


def save(profile):
    storage.write_private(path(), json.dumps(profile, ensure_ascii=False, indent=2))
    return profile


def current_epoch(profile):
    return profile["epochs"][-1] if profile["epochs"] else None


def validate_axes(axes):
    if not isinstance(axes, list) or not 4 <= len(axes) <= 6:
        raise ValueError("A profile needs 4–6 personal axes")

    for axis in axes:
        if not isinstance(axis, dict) or not ID.fullmatch(str(axis.get("id", ""))):
            raise ValueError(f"Axis id must be 2–32 characters of a-z, 0-9 and '-': {axis}")

        for key in ("name", "measures"):
            if not isinstance(axis.get(key), str) or not axis[key].strip():
                raise ValueError(f"Axis {axis['id']} needs {key}")

        if not isinstance(axis.get("signals", []), list):
            raise ValueError(f"Axis {axis['id']}: signals must be a list")

    if len({axis["id"] for axis in axes}) != len(axes):
        raise ValueError("Axis ids must be unique")

    return [{"id": axis["id"], "name": axis["name"].strip(), "measures": axis["measures"].strip(),
             "signals": [str(signal) for signal in axis.get("signals", [])]} for axis in axes]


def set_axes(axes, description, template):
    axes = validate_axes(axes)
    profile = read()
    epoch = current_epoch(profile)

    if epoch and epoch["axes"] == axes:
        epoch.update(description=description, template=template)
    else:
        profile["epochs"].append({"id": len(profile["epochs"]) + 1, "started": date.today().isoformat(),
                                  "description": description, "template": template, "axes": axes})

    return save(profile)


def set_options(**options):
    profile = read()

    for key, value in options.items():
        if key not in OPTIONS:
            raise ValueError(f"Unknown option {key}")

        if key == "period" and value not in PERIODS:
            raise ValueError(f"Unknown period {value}")

        profile["options"][key] = value if key == "period" else bool(value)

    return save(profile)


def templates():
    return {item.stem: json.loads(item.read_text(encoding="utf-8")) for item in sorted(TEMPLATES.glob("*.json"))}
