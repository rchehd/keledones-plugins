import ast
import unittest

from helpers import PLUGIN

FORBIDDEN = {"socket", "urllib", "http", "ssl", "ftplib", "smtplib", "subprocess", "requests"}


class NoNetworkTest(unittest.TestCase):
    def test_scripts_import_no_network(self):
        found = {}

        for path in (PLUGIN / "scripts").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names = []

                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                    names = [node.module]

                for name in names:
                    if name.split(".")[0] in FORBIDDEN:
                        found.setdefault(path.name, []).append(name)

        self.assertEqual(found, {})


if __name__ == "__main__":
    unittest.main()
