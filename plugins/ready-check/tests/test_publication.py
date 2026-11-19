from unittest.mock import patch

from helpers import RepoTest
from publication import describe, repository


class PublicationTest(RepoTest):
    def test_repository_coordinates(self):
        cases = (
            ("git@github.com:org/repo.git", "github.com", "org/repo", "github"),
            ("ssh://git@ssh.github.com:443/org/repo.git", "github.com", "org/repo", "github"),
            ("https://gitlab.com/team/subgroup/app.git", "gitlab.com", "team/subgroup/app", "gitlab"),
            ("https://user:secret@code.example:8443/team/app.git?token=secret", "code.example:8443", "team/app", None),
            ("https://github.com.example/team/app.git", "github.com.example", "team/app", None),
        )
        for url, host, path, provider in cases:
            with self.subTest(url=url):
                self.assertEqual(repository(url), {"host": host, "path": path, "provider": provider})

    def test_local_and_unsupported_remote_paths(self):
        for url in ("../team/app.git", "C:team/app.git", "C:\\team\\app.git", "file:///team/app.git",
                    "https://gitlab.com/team/../app.git", "https://gitlab.com:invalid/team/app.git"):
            with self.subTest(url=url):
                self.assertIsNone(repository(url))

    def test_entry_lists_fetch_push_and_feature_tracking_separately(self):
        self.git("remote", "add", "origin", "https://user:secret@github.com/upstream/app.git")
        self.git("remote", "set-url", "--push", "origin", "git@github.com:fork/app.git")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.git("update-ref", "refs/remotes/origin/topic", "HEAD")
        self.git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        self.git("checkout", "-qb", "topic", "--track", "origin/topic")
        data = self.entry_json("publication", "--project", str(self.repo))
        self.assertEqual(data["branch"], "topic")
        self.assertEqual(data["upstream"], "refs/remotes/origin/topic")
        remote = data["remotes"]["origin"]
        self.assertEqual(remote["cachedDefaultBranch"], "main")
        self.assertEqual(remote["fetch"], [{"host": "github.com", "path": "upstream/app", "provider": "github"}])
        self.assertEqual(remote["push"], [{"host": "github.com", "path": "fork/app", "provider": "github"}])
        self.assertNotIn("secret", str(data))
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertFalse((self.repo / ".ai").exists())

    def test_cli_discovery_with_detached_head_and_no_remote(self):
        self.git("checkout", "--detach", "-q", "HEAD")
        with patch("publication.find_command", side_effect=lambda name: "gh" if name == "gh" else None):
            data = describe(self.repo)
        self.assertIsNone(data["branch"])
        self.assertIsNone(data["upstream"])
        self.assertEqual(data["remotes"], {})
        self.assertEqual(data["cliOnPath"], {"gh": True, "glab": False})

    def test_outside_git(self):
        data = self.entry_json("publication", "--project", str(self.root), code=1)
        self.assertIn("not a Git worktree", data["error"])
