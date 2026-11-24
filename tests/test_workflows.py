import re
import unittest

from tests.helpers import REPO

WF = REPO / ".github" / "workflows"


class Workflows(unittest.TestCase):
    def texts(self):
        files = sorted(WF.glob("*.yml"))
        self.assertTrue(files)
        return {f.name: f.read_text() for f in files}

    def test_workflow_self_check(self):
        """T26 I13 S56 S59 R45: upstream CI uses no secrets, no write tokens, no model, no issue triggers."""
        for name, text in self.texts().items():
            with self.subTest(file=name):
                for banned in ("pull_request_target", "secrets.", "issues:", "issue_comment:", "workflow_run:"):
                    self.assertNotIn(banned, text)
                self.assertIsNone(re.search(r"anthropic|claude|ANTHROPIC_API_KEY", text, re.I))
                self.assertIn("permissions:", text)
                for block in re.findall(r"permissions:\s*\n((?:\s+\S.*\n)+)", text):
                    self.assertNotIn("write", block)
                self.assertNotRegex(text, r"permissions:\s*write")

    def test_release_and_single_python(self):
        """T26 T28 S57 DF-1: release runs the release check; CI runs on one Python, the 3.11 floor.
        The 3.10 version gate is covered by tests/test_entry.py, not by a CI job."""
        texts = self.texts()
        self.assertIn("check --release", texts["release.yml"])
        self.assertIn("check --ci --base", texts["check.yml"])
        for name, text in texts.items():
            with self.subTest(file=name):
                self.assertNotIn("matrix:", text)
                self.assertEqual(set(re.findall(r'python-version: "([^"]+)"', text)), {"3.11"})
