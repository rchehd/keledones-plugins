import shutil
import unittest

from helpers import RepoTest


class TypeScriptTest(RepoTest):
    def write(self, name, value):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def test_named_typescript_config_and_drupal_are_detected_together(self):
        self.write("composer.json", '{"require":{"drupal/core":"^11"}}')
        self.write("workspace/frontend/tsconfig.app.json", "{}")
        result = self.entry_json("profiles", "--project", str(self.repo))
        self.assertEqual({(item["profile"], item["application"]) for item in result["profiles"]},
                         {("drupal", "."), ("typescript", "workspace/frontend")})

    @unittest.skipUnless(shutil.which("node"), "Node.js is required")
    def test_doctor_prefers_hoisted_project_tools_and_eslint_config(self):
        self.write("frontend/tsconfig.json", "{}")
        self.write("frontend/src/index.ts", "export const value = 1;\n")
        self.write("eslint.config.mjs", "export default [];\n")
        self.write("node_modules/typescript/bin/tsc", "#!/usr/bin/env node\nconsole.log('Version 5.8.0');\n")
        self.write("node_modules/eslint/bin/eslint.js", "console.log('v9.30.0');\n")

        result = self.entry_json("doctor", "--profile", "typescript", "--project", str(self.repo / "frontend"),
                                 "--base", "main")
        checks = {check["id"]: check for check in result["checks"]}
        for name in ("typecheck", "eslint"):
            self.assertEqual(checks[name]["status"], "READY")
            self.assertEqual(checks[name]["tools"][-1]["source"], "project")
        self.assertEqual(checks["typecheck"]["tools"][-1]["version"], "5.8.0")
        self.assertTrue(checks["eslint"]["tools"][-1]["path"].endswith("/eslint/bin/eslint.js"))
