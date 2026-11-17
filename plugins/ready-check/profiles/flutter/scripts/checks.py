import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "_shared/core"))
sys.path.insert(0, str(HERE))
import core_main
from spec import SPEC

if __name__ == "__main__":
    sys.exit(core_main.main(SPEC))
