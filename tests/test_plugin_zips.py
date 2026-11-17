import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("build_plugin_zips", ROOT / "scripts/build-plugin-zips.py")
packaging = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packaging)


class PluginZipTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="keledones-zip-test.")
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        self.repo = base / "repo"
        self.repo.mkdir()
        self.output = base / "zips"
        self.git("init", "--quiet")

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)

    def write(self, relative, content):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def manifest(self, relative, version):
        self.write(f"plugins/first/{relative}", json.dumps({"name": "sample", "version": version}))

    def commit(self):
        self.git("add", ".")
        self.git("commit", "--quiet", "-m", "Add plugin fixture")

    def test_zip_uses_committed_plugin_files_and_manifest_version(self):
        self.manifest(".claude-plugin/plugin.json", "0.1.0")
        self.manifest(".codex-plugin/plugin.json", "0.1.0")
        self.write(".claude-plugin/marketplace.json", "{}")
        self.write("plugins/first/scripts/run.sh", "echo ready\n")
        self.write("plugins/first/tests/fixture.txt", "test only")
        self.commit()
        self.manifest(".claude-plugin/plugin.json", "9.9.9")
        self.write("plugins/first/private.txt", "untracked")

        self.assertEqual(packaging.build(self.repo, self.output), ["sample-0.1.0.zip"])
        with ZipFile(self.output / "sample-0.1.0.zip") as archive:
            files = {path for path in archive.namelist() if not path.endswith("/")}
            self.assertEqual(files, {"first/.claude-plugin/plugin.json", "first/.codex-plugin/plugin.json",
                                     "first/scripts/run.sh"})
            self.assertEqual(json.loads(archive.read("first/.claude-plugin/plugin.json"))["version"], "0.1.0")

    def test_disagreeing_client_versions_fail_before_writing_assets(self):
        self.manifest(".claude-plugin/plugin.json", "0.1.0")
        self.manifest(".codex-plugin/plugin.json", "0.2.0")
        self.commit()

        with self.assertRaisesRegex(ValueError, "single plugin name and version"):
            packaging.build(self.repo, self.output)
        self.assertFalse(self.output.exists())
