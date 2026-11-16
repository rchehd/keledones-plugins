import json
import os
import socket
import sys
import tempfile
import time
import unittest
from pathlib import Path


PLUGIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN / "scripts"))
import dependency_support as support


class LockTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="ready-check-lock-test.")
        self.addCleanup(temporary.cleanup)
        self.lock = str(Path(temporary.name) / ".setup-lock")

    def abandon(self, **owner):
        Path(self.lock).mkdir()
        (Path(self.lock) / "owner.json").write_text(json.dumps(owner))

    def dead_pid(self):
        pid = 4000000
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return pid
            except OSError:
                pass
            pid += 1

    def test_take_writes_owner_and_release_removes_both(self):
        support.take_lock(self.lock, 60)
        owner = json.loads((Path(self.lock) / "owner.json").read_text())
        self.assertEqual((owner["pid"], owner["host"]), (os.getpid(), socket.gethostname()))
        support.release_lock(self.lock)
        self.assertFalse(Path(self.lock).exists())

    @unittest.skipIf(os.name == "nt", "PID liveness is not probed on Windows")
    def test_dead_owner_on_this_host_is_recovered(self):
        self.abandon(pid=self.dead_pid(), host=socket.gethostname(), started=time.time())
        support.take_lock(self.lock, 60)
        self.assertEqual(json.loads((Path(self.lock) / "owner.json").read_text())["pid"], os.getpid())

    def test_live_owner_is_refused_with_details(self):
        self.abandon(pid=os.getpid(), host=socket.gethostname(), started=time.time())
        with self.assertRaisesRegex(ValueError, str(os.getpid())):
            support.take_lock(self.lock, 60)
        self.assertTrue(Path(self.lock).exists())

    def test_foreign_host_owner_is_refused_even_when_old(self):
        self.abandon(pid=os.getpid(), host="other-host", started=time.time())
        with self.assertRaises(ValueError):
            support.take_lock(self.lock, 60)
        old = time.time() - 700
        os.utime(self.lock, (old, old))
        with self.assertRaises(ValueError):
            support.take_lock(self.lock, 60)

    def test_old_live_owner_is_not_reclaimed(self):
        self.abandon(pid=os.getpid(), host=socket.gethostname(), started=time.time() - 700)
        original = (Path(self.lock) / "owner.json").read_bytes()
        old = time.time() - 700
        os.utime(self.lock, (old, old))
        with self.assertRaises(ValueError):
            support.take_lock(self.lock, 60)
        self.assertEqual((Path(self.lock) / "owner.json").read_bytes(), original)

    def test_unknown_liveness_on_windows_does_not_expire_owner(self):
        from unittest.mock import patch
        owner = dict(pid=os.getpid(), host=socket.gethostname(), started=0)
        with patch.object(support.os, "name", "nt"):
            self.assertFalse(support.lock_is_stale(owner, 700, 60))

    def test_ownerless_old_lock_is_recovered(self):
        Path(self.lock).mkdir()
        old = time.time() - 700
        os.utime(self.lock, (old, old))
        support.take_lock(self.lock, 60)
        self.assertTrue((Path(self.lock) / "owner.json").is_file())

    def test_staleness_rules(self):
        self.assertTrue(support.lock_is_stale(None, 661, 60))
        self.assertFalse(support.lock_is_stale(None, 10, 60))
        self.assertFalse(support.lock_is_stale("garbage", 10, 60))


if __name__ == "__main__":
    unittest.main()
