import importlib.util
import json
import unittest

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

    def test_versions_match(self):
        versions = {json.loads((PLUGIN / folder / "plugin.json").read_text(encoding="utf-8"))["version"]
                    for folder in (".claude-plugin", ".codex-plugin", ".cursor-plugin")}
        self.assertEqual(versions, {"0.1.0"})


if __name__ == "__main__":
    unittest.main()
