import os
import sys
import tempfile
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN / "scripts"))
sys.dont_write_bytecode = True
ENV = ("GNOTHI_DATA_DIR", "GNOTHI_CLAUDE_DIR", "GNOTHI_CODEX_DIR", "GNOTHI_CURSOR_DIR")


def fixture(*parts):
    return PLUGIN.joinpath("tests", "fixtures", *parts)


class TempHome:
    def __enter__(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="gnothi-test.")
        self.root = Path(self.temporary.name).resolve()
        self.saved = {name: os.environ.get(name) for name in ENV}

        for name in ENV:
            os.environ[name] = str(self.root / name.split("_")[1].lower())

        return self

    def __exit__(self, *error):
        for name, value in self.saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

        self.temporary.cleanup()
