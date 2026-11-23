import importlib.util
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
SHARED = PLUGIN / "profiles/_shared/core"


def load_spec(profile):
    path = PLUGIN / "profiles" / profile / "scripts/spec.py"
    module = importlib.util.spec_from_file_location("ready_check_spec_" + profile.replace("-", "_"), path)
    loaded = importlib.util.module_from_spec(module)
    module.loader.exec_module(loaded)
    return loaded.SPEC


def profile_runner(application, profile):
    sys.path.insert(0, str(SHARED))
    from core_runner import application_runner
    spec = load_spec(profile)
    return application_runner(application, spec), spec
