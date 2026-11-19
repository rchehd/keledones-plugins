from helpers import RepoTest


class DraftTemplateTest(RepoTest):
    def template(self, kind, code=0, **options):
        return self.entry_json("template", kind, "--project", str(self.repo), code=code,
                               env={"GIT_CONFIG_GLOBAL": str(self.root / "git-global"), "GIT_CONFIG_NOSYSTEM": "1", **options})

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_uses_packaged_defaults(self):
        self.assertEqual(self.template("commit")["source"], "default")
        pr = self.template("pr")
        self.assertEqual(pr["source"], "default")
        self.assertIn("## How to verify (QA)", pr["content"])

    def test_project_native_and_user_precedence_for_both_kinds(self):
        for kind, key, native_name in (("commit", "commitTemplate", ".gitmessage"),
                                       ("pr", "pullRequestTemplate", ".github/PULL_REQUEST_TEMPLATE.md")):
            with self.subTest(kind=kind):
                global_file = self.write(self.root / f"{kind} global.txt", "Global layout\n")
                self.entry_json("config", "set", key, str(global_file))
                self.assertEqual(self.template(kind)["source"], "user")

                native_file = self.write(self.repo / native_name, "Repository layout\n")
                if kind == "commit":
                    self.git("config", "--local", "commit.template", native_name)
                self.assertEqual(self.template(kind)["source"], "repository")

                personal = self.write(self.repo / "templates" / f"{kind} local.txt", "Project override\n")
                nested = self.repo / "templates"
                self.entry_json("config", "set", key, personal.relative_to(self.repo).as_posix(), "--project", str(nested))
                self.assertEqual(self.template(kind)["content"], "Project override\n")
                self.assertEqual(self.template(kind)["source"], "project")

                self.entry_json("config", "unset", key, "--project", str(self.repo))
                self.assertEqual(self.template(kind)["content"], "Repository layout\n")
                if kind == "commit":
                    self.git("config", "--local", "--unset", "commit.template")
                native_file.unlink()
                self.assertEqual(self.template(kind)["content"], "Global layout\n")

    def test_native_git_global_template_is_below_user_override(self):
        system_file = self.write(self.root / "git commit.txt", "Git layout\n")
        self.git("config", "--file", str(self.root / "git-global"), "commit.template", str(system_file))
        self.assertEqual(self.template("commit")["source"], "git")
        user_file = self.write(self.root / "ready commit.txt", "Ready Check layout\n")
        self.entry_json("config", "set", "commitTemplate", str(user_file))
        self.assertEqual(self.template("commit")["content"], "Ready Check layout\n")
        self.entry_json("config", "unset", "commitTemplate")
        self.assertEqual(self.template("commit")["content"], "Git layout\n")

    def test_uses_native_gitlab_body(self):
        self.write(self.repo / ".gitlab/merge_request_templates/Default.md", "## Merge request\n")
        self.assertEqual(self.template("pr")["content"], "## Merge request\n")

    def test_task_comment_template_uses_project_client_user_then_default(self):
        kind = "task-comment"
        self.git("config", "--local", "commit.template", "irrelevant")
        default = self.template(kind)
        self.assertEqual(default["source"], "default")
        self.assertIn("1. ", default["content"])
        user = self.write(self.root / "user.md", "User layout\n")
        cli = self.write(self.repo / "claude.md", "Claude layout\n")
        cursor = self.write(self.root / "cursor.md", "Cursor layout\n")
        local = self.write(self.repo / "local.md", "Project layout\n")
        self.entry_json("config", "set", "taskCommentTemplate", str(user))
        self.assertEqual(self.template(kind)["source"], "user")
        for option, value, file in (("CLAUDE_PLUGIN_OPTION_TASK_COMMENT_TEMPLATE", "claude.md", cli),
                                    ("READY_CHECK_TASK_COMMENT_TEMPLATE", str(cursor), cursor)):
            with self.subTest(option=option):
                template = self.template(kind, **{option: value})
                self.assertEqual((template["source"], template["content"]), ("client", file.read_text()))
        self.entry_json("config", "set", "taskCommentTemplate", str(local), "--project", str(self.repo))
        self.assertEqual(self.template(kind, READY_CHECK_TASK_COMMENT_TEMPLATE=str(cursor))["content"], "Project layout\n")
        self.entry_json("config", "unset", "taskCommentTemplate", "--project", str(self.repo))
        self.assertEqual(self.template(kind)["content"], "User layout\n")

    def test_bad_task_comment_client_override_reports_error(self):
        result = self.template("task-comment", code=2, CLAUDE_PLUGIN_OPTION_TASK_COMMENT_TEMPLATE="missing.md")
        self.assertIn("does not exist", result["reason"])

    def test_missing_or_outside_project_template_is_reported(self):
        local_file = self.write(self.repo / "local.md", "Project layout\n")
        self.entry_json("config", "set", "pullRequestTemplate", "local.md", "--project", str(self.repo))
        local_file.unlink()
        self.assertIn("does not exist", self.template("pr", code=2)["reason"])
        result = self.entry_json("config", "set", "pullRequestTemplate", "../outside.md", "--project", str(self.repo), code=2)
        self.assertIn("inside the repository", result["reason"])
