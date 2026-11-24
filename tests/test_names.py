import re
import subprocess
import unittest

from golden import names

INPUTS = ["Fix login", "../../etc", "-rf --force", "Виправити вхід", "!!!", "a" * 200, "feat/x..y", "x@{y}",
          "Ünïcödé ok", "", "   ", ".lock", "a.lock", "HEAD"]
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def ref_ok(branch):
    return subprocess.run(["git", "check-ref-format", "--branch", branch], capture_output=True).returncode == 0


class Names(unittest.TestCase):
    def test_slug_and_branch_table(self):
        """T30 R16 Review Focus 3: any user text gives a non-empty, safe slug and a valid branch."""
        for text in INPUTS:
            with self.subTest(text=text[:20]):
                s = names.slug(text)
                self.assertRegex(s, SLUG)
                self.assertLessEqual(len(s), 40)
                self.assertFalse(s.endswith("-"))
                for kind in ("feature", "fix", "debug", "perf", "ux"):
                    b = names.branch_name("{type}/{slug}_{id}", kind, text, "T-20261124-1")
                    self.assertTrue(ref_ok(b), b)
                    self.assertFalse(b.startswith("-"), b)

    def test_known_slugs(self):
        """T30: readable slugs for ordinary text, a fallback for text with no letters."""
        self.assertEqual(names.slug("Fix login"), "fix-login")
        self.assertEqual(names.slug("Ünïcödé ok"), "unicode-ok")
        self.assertEqual(names.slug("!!!"), "task")
        self.assertEqual(names.slug("Виправити вхід"), "task")
        self.assertEqual(names.branch_name("{type}/{slug}_{id}", "debug", "Fix login", "T-1"), "fix/fix-login_T-1")
        self.assertEqual(names.branch_name("{kind}-{slug}", "ux", "Fix login", "T-1"), "ux-fix-login")

    def test_invalid_pattern_refused(self):
        """R16: a profile branch pattern that yields an invalid ref is refused, not passed to git."""
        for pattern in ("{slug}..{id}", "-{slug}", "{slug} {id}", "{slug}.lock"):
            with self.subTest(pattern=pattern):
                with self.assertRaises(ValueError):
                    names.branch_name(pattern, "fix", "x", "T-1")
