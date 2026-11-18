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

    def test_codex_starter_targets_the_local_portrait_skill(self):
        manifest = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertIs(manifest["requires_local_executor"], True)
        prompt = manifest["interface"]["defaultPrompt"][0]
        self.assertIn("$gnothi:portrait", prompt)
        self.assertLessEqual(len(prompt), 128)

    def test_codex_import_requires_a_long_description(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "gnothi"
            shutil.copytree(PLUGIN, root)
            path = root / ".codex-plugin/plugin.json"
            manifest = json.loads(path.read_text(encoding="utf-8"))
            for description in (" \t\n", None):
                with self.subTest(description=description):
                    if description is None:
                        del manifest["interface"]["longDescription"]
                    else:
                        manifest["interface"]["longDescription"] = description
                    path.write_text(json.dumps(manifest), encoding="utf-8")
                    self.assertIn(".codex-plugin/plugin.json: interface.longDescription must be non-blank text",
                                  validate.check_manifests(root))

    def test_versions_match(self):
        versions = {json.loads((PLUGIN / folder / "plugin.json").read_text(encoding="utf-8"))["version"]
                    for folder in (".claude-plugin", ".codex-plugin", ".cursor-plugin")}
        self.assertEqual(len(versions), 1, versions)


if __name__ == "__main__":
    unittest.main()
