import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core_checks import Provider
import php_lint
import php_toolchain


class Extra:
    def __init__(self, applies, run, tool=None, php=False, configure=None):
        self.applies, self.run, self.tool, self.php, self.configure = applies, run, tool, php, configure


PHP = Provider(directory=Path(__file__).resolve().parent, applies=php_toolchain.applies, claims=php_toolchain.claims,
               plan=php_toolchain.plan, checks=php_lint.CHECKS, parsers=php_lint.PARSERS)
