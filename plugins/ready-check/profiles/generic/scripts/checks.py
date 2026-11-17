#!/usr/bin/env python3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "_shared/core"))
sys.dont_write_bytecode = True
import core_main
from spec import SPEC

if __name__ == "__main__":
    sys.exit(core_main.main(SPEC))
