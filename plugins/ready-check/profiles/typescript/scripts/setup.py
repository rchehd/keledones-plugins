import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "_shared/core"))
sys.path.insert(0, str(HERE))
import core_setup
from spec import SPEC


def setup(project, host_root, override, dry_run, timeout):
    return core_setup.setup(project, host_root, override, dry_run, timeout, SPEC)
