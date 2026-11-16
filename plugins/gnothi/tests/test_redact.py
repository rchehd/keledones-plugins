import unittest

import helpers  # noqa: F401
from redact import excerpt, redact


class RedactTest(unittest.TestCase):
    def test_secrets(self):
        cases = {
            "key sk-ant-api03-abcdefghijklmnopqrstuvwx here": "key <secret> here",
            "token ghp_abcdefghijklmnopqrstuvwxyz0123456789": "token <secret>",
            "github_pat_11ABCDEFG0123456789_abcdefghijklmnop": "<secret>",
            "aws AKIAABCDEFGHIJKLMNOP": "aws <secret>",
            "slack xoxb-1234-5678-abcdefgh": "slack <secret>",
            "jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcDEF_123-x": "jwt <secret>",
            "Authorization: Bearer abc.def-123": "Authorization: <secret>",
            "hash 0123456789abcdef0123456789abcdef01": "hash <secret>",
            "blob QUJDREVGR0hJSktMTU5PUFFSU1RVVldYWVphYmNkZWZnaGlqa2xtbm9w": "blob <secret>",
            "password=hunter2 next": "password=<secret> next",
            "DB_SECRET: s3cr3t!": "DB_SECRET: <secret>",
            "api_key = 12345": "api_key = <secret>",
            "-----BEGIN RSA PRIVATE KEY-----\nMIIE\n-----END RSA PRIVATE KEY-----": "<secret>",
        }

        for text, expected in cases.items():
            self.assertEqual(redact(text), expected, text)

    def test_email_and_url(self):
        self.assertEqual(redact("mail jane.doe@corp.example.com now"), "mail <email> now")
        self.assertEqual(redact("open https://jira.corp.local/browse/X-1?a=b and http://x.io"),
                         "open <url:host-hidden> and <url:host-hidden>")

    def test_home_folder_becomes_tilde(self):
        from pathlib import Path
        from unittest import mock

        with mock.patch.object(Path, "home", return_value=Path("/home/jane")):
            self.assertEqual(redact("open /home/jane/Projects/shop/a.py"), "open ~/Projects/shop/a.py")

    def test_plain_prose_is_unchanged(self):
        text = "Fix the login form so the error shows under the field, as in the design."
        self.assertEqual(redact(text), text)

    def test_excerpt(self):
        text = "word " * 100
        result = excerpt(text)
        self.assertLessEqual(len(result), 150)
        self.assertTrue(result.endswith("…"))
        self.assertEqual(excerpt("  short\n\n text "), "short text")
        self.assertEqual(excerpt("see https://a.b/c"), "see <url:host-hidden>")


if __name__ == "__main__":
    unittest.main()
