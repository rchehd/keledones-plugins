import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("bump_version", PLUGIN / "scripts/bump-version.py")
bump_version = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bump_version)


class BumpVersionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready-check-bump.")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

        for name in bump_version.MANIFESTS:
            (self.root / name).parent.mkdir(parents=True)
            shutil.copy2(PLUGIN / name, self.root / name)
        self.version = bump_version.current(self.root)

    def versions(self):
        return [json.loads((self.root / name).read_text())["version"] for name in bump_version.MANIFESTS]

    def test_sets_the_version_in_every_manifest_and_keeps_the_rest(self):
        before = {name: (self.root / name).read_text() for name in bump_version.MANIFESTS}
        major, minor, patch = bump_version.key(self.version)
        new = f"{major}.{minor + 1}.0"
        self.assertEqual(bump_version.bump(self.root, new), self.version)
        self.assertEqual(self.versions(), [new] * 3)

        for name, text in before.items():
            self.assertEqual((self.root / name).read_text(), text.replace(f'"{self.version}"', f'"{new}"', 1))

    def test_rejects_a_version_that_is_not_greater(self):
        with self.assertRaises(ValueError):
            bump_version.bump(self.root, self.version)
        self.assertEqual(self.versions(), [self.version] * 3)

    def test_rejects_a_malformed_version(self):
        for value in ("1.0", "v1.0.0", "01.0.0", "1.0.0-beta"):
            with self.assertRaises(ValueError):
                bump_version.bump(self.root, value)

    def test_refuses_when_manifests_disagree(self):
        path = self.root / bump_version.MANIFESTS[1]
        data = json.loads(path.read_text())
        data["version"] = "9.9.9"
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError) as error:
            bump_version.bump(self.root, "10.0.0")
        self.assertIn("differ", str(error.exception))


if __name__ == "__main__":
    unittest.main()
