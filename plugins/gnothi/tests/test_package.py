import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import PLUGIN

SPEC = importlib.util.spec_from_file_location("validate_package", PLUGIN / "scripts/validate-package.py")
validate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate)


class PackageTest(unittest.TestCase):
    def test_package_is_valid(self):
        self.assertEqual(validate.check(PLUGIN), [])

    def test_skills(self):
        for name in ("setup", "portrait"):
            text = (PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(text.startswith(f"---\nname: {name}\ndescription: "), name)
            self.assertIn("## Privacy", text, name)
            self.assertTrue((PLUGIN / "skills" / name / "agents/openai.yaml").is_file(), name)

    def test_validator_reports_missing_skill(self):
        problems = validate.check_skills(PLUGIN, ("setup", "portrait", "absent"))
        self.assertEqual(problems, ["skills/absent/SKILL.md: missing"])

    def test_codex_starter_targets_the_portrait_skill_in_cloud_and_local_chats(self):
        manifest = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertFalse(manifest.get("requires_local_executor", False))
        prompt = manifest["interface"]["defaultPrompt"][0]
        self.assertIn("$gnothi:portrait", prompt)
        self.assertLessEqual(len(prompt), 128)

    def test_codex_import_metadata(self):
        cases = (
            ("longDescription", " \t\n", "must be non-blank text"),
            ("longDescription", None, "must be non-blank text"),
            ("capabilities", "Read", "must be a list of strings"),
            ("capabilities", ["Read", 1], "must be a list of strings"),
            ("capabilities", None, "must be a list of strings"),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "gnothi"
            shutil.copytree(PLUGIN, root)
            path = root / ".codex-plugin/plugin.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            for field, value, message in cases:
                with self.subTest(field=field, value=value):
                    interface = manifest["interface"].copy()
                    if value is None:
                        del interface[field]
                    else:
                        interface[field] = value
                    path.write_text(json.dumps(dict(manifest, interface=interface)), encoding="utf-8")
                    self.assertIn(f".codex-plugin/plugin.json: interface.{field} {message}",
                                  validate.check_manifests(root))

    def test_versions_match(self):
        versions = {json.loads((PLUGIN / folder / "plugin.json").read_text(encoding="utf-8"))["version"]
                    for folder in (".claude-plugin", ".codex-plugin", ".cursor-plugin")}
        self.assertEqual(len(versions), 1, versions)


if __name__ == "__main__":
    unittest.main()
