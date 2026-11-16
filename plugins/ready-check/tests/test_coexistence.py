import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PLUGIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN / "scripts"))
from dependency_support import asset_id, bundle_path
from managed_storage import MARKER, prepare_storage
from process_support import execute

SPEC = importlib.util.spec_from_file_location("ready_check_coexistence_setup", PLUGIN / "scripts/setup.py")
SETUP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SETUP)


class CoexistenceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready-check-coexistence.")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = self.root / "project"
        self.project.mkdir()
        self.data = self.root / "ready-check"
        self.source = PLUGIN / "dependencies/browser"
        self.bundle = bundle_path(self.source, self.data, "browser")

    def test_setup_preserves_other_toolkit_instructions_and_configurations(self):
        other = b"<!-- companion-toolkit:begin -->\n@./.companion/rules.md\nKeep this toolkit enabled.\n<!-- companion-toolkit:end -->\n"
        for name in ("AGENTS.md", "CLAUDE.local.md"):
            (self.project / name).write_bytes(other)
        paths = (".claude/settings.json", ".codex/config.toml", ".cursor/rules/companion.mdc",
                 ".agents/skills/setup/SKILL.md", ".companion/rules.md", "vendor/bin/companion", "node_modules/companion/package.json")
        for name in paths:
            path = self.project / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"Companion toolkit installation and custom settings\n")
        sibling = self.root / "companion-tools/keep.txt"
        sibling.parent.mkdir()
        sibling.write_bytes(b"Other toolkit managed data\n")
        snapshot = {self.project / name: (self.project / name).read_bytes() for name in paths}
        snapshot[sibling] = sibling.read_bytes()
        args = ["setup.py", "--component", "browser", "--project", str(self.project), "--data-dir", str(self.data)]
        for attempt in range(2):
            with patch.object(sys, "argv", args), patch.object(sys, "stdout", io.StringIO()) as output, patch.object(
                    SETUP, "browser_setup", return_value=dict(component="browser", status="PASS")):
                self.assertEqual(SETUP.main(), 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "PASS")
            for path, original in snapshot.items():
                self.assertEqual(path.read_bytes(), original)
            for name in ("AGENTS.md", "CLAUDE.local.md"):
                self.assertEqual((self.project / name).read_bytes(), other)

    def test_nonempty_foreign_data_root_is_rejected_before_any_installation(self):
        self.data.mkdir()
        file = self.data / "package.json"
        file.write_bytes(b'{"name":"companion-toolkit"}\n')
        with patch.object(SETUP, "command") as command, self.assertRaisesRegex(ValueError, "ownership"):
            SETUP.browser_setup(self.data, self.project, "chromium", False, 30)
        command.assert_not_called()
        self.assertEqual(file.read_bytes(), b'{"name":"companion-toolkit"}\n')
        self.assertEqual(list(self.data.iterdir()), [file])

    def test_foreign_bundle_in_owned_root_is_not_claimed_or_overwritten(self):
        prepare_storage(self.data, self.bundle, self.source, "browser")
        (self.bundle / MARKER).unlink()
        file = self.bundle / "package.json"
        file.write_bytes(b"Foreign toolkit data\n")
        with self.assertRaisesRegex(ValueError, "ownership"):
            prepare_storage(self.data, self.bundle, self.source, "browser")
        self.assertEqual(file.read_bytes(), b"Foreign toolkit data\n")
        self.assertFalse((self.bundle / MARKER).exists())

    def test_wrong_owner_marker_is_not_overwritten(self):
        self.data.mkdir()
        marker = self.data / MARKER
        content = b'{"owner":"companion-toolkit"}\n'
        marker.write_bytes(content)
        with self.assertRaises(ValueError):
            prepare_storage(self.data, self.bundle, self.source, "browser")
        self.assertEqual(marker.read_bytes(), content)

    def test_owned_interrupted_install_can_be_retried_without_ready_marker(self):
        prepare_storage(self.data, self.bundle, self.source, "browser")
        (self.bundle / "package.json").write_bytes(b"Partial owned download\n")
        prepare_storage(self.data, self.bundle, self.source, "browser")
        self.assertFalse((self.bundle / "ready.json").exists())
        self.assertEqual(json.loads((self.bundle / MARKER).read_bytes())["owner"], "ready-check")

    def test_symlink_to_other_toolkit_is_refused_without_modification(self):
        foreign = self.root / "companion"
        foreign.mkdir()
        payload = foreign / "package.json"
        payload.write_bytes(b"Companion installation\n")
        self.bundle.parent.mkdir(parents=True)
        try:
            self.bundle.symlink_to(foreign, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symlinks unavailable: {error}")
        with self.assertRaisesRegex(ValueError, "link"):
            prepare_storage(self.data, self.bundle, self.source, "browser")
        self.assertEqual(payload.read_bytes(), b"Companion installation\n")
        self.assertEqual(list(foreign.iterdir()), [payload])

    def test_external_link_inside_owned_dependencies_is_refused(self):
        prepare_storage(self.data, self.bundle, self.source, "browser")
        foreign = self.root / "companion"
        foreign.mkdir()
        try:
            (self.bundle / "node_modules").symlink_to(foreign, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symlinks unavailable: {error}")
        with self.assertRaisesRegex(ValueError, "link"):
            prepare_storage(self.data, self.bundle, self.source, "browser")
        self.assertFalse(list(foreign.iterdir()))

    def test_preview_never_claims_fresh_storage(self):
        prepare_storage(self.data, self.bundle, self.source, "browser", dry_run=True)
        self.assertFalse(self.data.exists())

    def test_bundle_cannot_redirect_into_a_different_tool_under_the_data_root(self):
        prepare_storage(self.data, self.bundle, self.source, "browser")
        foreign = self.data / "companion-toolkit"
        foreign.mkdir()
        try:
            (self.bundle / "node_modules").symlink_to(foreign, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Symlinks unavailable: {error}")
        with self.assertRaisesRegex(ValueError, "link"):
            prepare_storage(self.data, self.bundle, self.source, "browser")
        self.assertFalse(list(foreign.iterdir()))

    def test_container_storage_backend_preserves_ownership_and_rejects_foreign_data(self):
        sys.path.insert(0, str(PLUGIN / "profiles/_shared/core"))
        from core_runner import Runner

        class SimulatedRunner:
            name = "compose"
            sh, read, mkdir = Runner.sh, Runner.read, Runner.mkdir

            def exec(inner, argv, timeout=15, input=None):
                return execute(argv, self.project, timeout=timeout, input=input)

            def exists(inner, path, kind="file"):
                return Path(path).is_dir() if kind == "dir" else Path(path).exists()

        if os.name == "nt":
            self.skipTest("POSIX container paths require a Unix shell simulator")
        runner = SimulatedRunner()
        prepare_storage(str(self.data), str(self.bundle), self.source, "browser", runner)
        self.assertEqual(json.loads((self.bundle / MARKER).read_bytes())["owner"], "ready-check")
        marker = self.bundle / MARKER
        marker.write_bytes(b'{"owner":"companion-toolkit"}\n')
        with self.assertRaises(ValueError):
            prepare_storage(str(self.data), str(self.bundle), self.source, "browser", runner)
        self.assertEqual(marker.read_bytes(), b'{"owner":"companion-toolkit"}\n')


if __name__ == "__main__":
    unittest.main()
