import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import go_setup
from spec import SPEC


def setup(project, host_root, override, dry_run, timeout):
    return go_setup.setup(project, host_root, override, dry_run, timeout, spec=SPEC)
