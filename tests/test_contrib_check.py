import json

from tests.helpers import DistiflowCase, practice, w, write_profile
from tests.test_glossary_similar import CORPUS

PROFILE = ('[project]\nname = "Zentrix"\ndeny_terms = ["quokka"]\n[commands]\ndeploy = "ssh deploy.zentrix.dev"\n'
           '[glossary]\ntenant = "workspace"\n')
NEAR = ("Before fixing, write a test that fails. Watch the test fail for the right reason, then fix it. "
        "Each tenant gets its own run; the tenant id is in the log.")


class ContribCase(DistiflowCase):
    SKILLS = {}

    def setUp(self):
        super().setUp()
        self.root = self.fixture_root(practices={"plan/%s.md" % k: practice(k, ["plan"], body=v) for k, v in CORPUS.items()},
                                      skills=self.SKILLS)
        self.proj = self.repo("zentrix-api")
        write_profile(self.proj, PROFILE)

    def c(self, *args, **kw):
        return self.distiflow("contrib", *args, cwd=self.proj, root=self.root, **kw)

    def draft(self, body=NEAR, slug="test-first-fix", pid="test-first-fix", **meta):
        r = self.c("new", *slug.split("-"))
        self.assertEqual(r.returncode, 0, r.stderr)
        d = self.proj / ".distiflow/contrib" / slug
        w(d / "draft.md", practice(pid, meta.get("stages", ["plan"]), kinds=["fix"], body=body))
        return d


class ContribCheck(ContribCase):
    def test_check_output_sections(self):
        """T23 S41: the confirm view shows classification, every check, replaced terms, the diff and a shortlist."""
        d = self.draft()
        r = self.c("check", "test-first-fix")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        sections = [line for line in r.stdout.splitlines() if line.startswith("## ")]
        self.assertEqual(sections, ["## Classification", "## Checks", "## Replaced terms", "## Diff",
                                    "## Similar upstream practices"])
        self.assertIn("stages: plan", r.stdout)
        self.assertIn("tenant → workspace ×2", r.stdout)
        similar = r.stdout.split("## Similar upstream practices\n", 1)[1].strip().splitlines()
        self.assertEqual(len(similar), 5)
        self.assertTrue(similar[0].startswith("tests-first "), similar)
        self.assertRegex(r.stdout, r"\n-[^\n]*Each tenant gets")
        self.assertRegex(r.stdout, r"\n\+[^\n]*Each workspace gets")
        self.assertNotIn("tenant", (d / "sanitized.md").read_text())
        self.assertIn("tenant", (d / "original.md").read_text())
        self.assertTrue(json.loads((d / "check.json").read_text())["passed"])

    def test_failed_check_lists_every_check_and_blocks_confirm(self):
        """T22 S49: a failing check still lists every check, and confirm is refused."""
        self.draft(body="Use token ghp_" + "a" * 36 + " for the api.")
        r = self.c("check", "test-first-fix")
        self.assertEqual(r.returncode, 1)
        checks = r.stdout.split("## Checks\n", 1)[1].split("\n## ", 1)[0]
        for name in ("format: pass", "size: pass", "leaks: FAIL", "hostile: pass", "glossary-alias: pass"):
            self.assertIn(name, checks)
        self.assertIn("secret", checks)
        r = self.c("confirm", "test-first-fix", "--verdict", "new")
        self.assertEqual(r.returncode, 1)
        self.assertFalse((self.proj / ".distiflow/contrib/test-first-fix/confirmed.json").exists())

    def test_sensitive_kinds_never_survive(self):
        """S44: each sensitive kind is blocked by name, or rewritten away and listed; never left in sanitized.md."""
        rows = [("secret", "key AKIAIOSFODNN7EXAMPLE here", "secret"), ("email", "ask ops@zentrix.dev", "email"),
                ("host", "see https://admin.zentrix.dev/x", "host"), ("deny term", "the Quokka board", "deny-term"),
                ("repo name", "in zentrix-api we", "deny-term"), ("project name", "Zentrix style", "deny-term"),
                ("command host", "run on deploy.zentrix.dev", "host"), ("glossary", "every tenant", None)]
        for i, (name, text, rule) in enumerate(rows):
            with self.subTest(row=name):
                slug = "kind-%d" % i
                d = self.draft(body="Keep it short. " + text, slug=slug, pid=slug)
                r = self.c("check", slug)
                word = text.split()[-1] if rule is None else None
                if rule:
                    self.assertEqual(r.returncode, 1, r.stdout)
                    self.assertIn(rule, r.stdout.split("## Checks\n", 1)[1].split("\n## ", 1)[0])
                else:
                    self.assertEqual(r.returncode, 0, r.stdout)
                    self.assertIn("%s → workspace ×1" % word, r.stdout)
                    self.assertNotIn(word, (d / "sanitized.md").read_text())

    def test_confirm_binds_hash(self):
        """I1 R37: an edit to sanitized.md after check makes confirm refuse."""
        d = self.draft()
        self.assertEqual(self.c("check", "test-first-fix").returncode, 0)
        first = (d / "original.md").read_text()
        (d / "draft.md").write_text((d / "draft.md").read_text() + "\nsecond pass\n")
        self.assertEqual(self.c("check", "test-first-fix").returncode, 0)
        self.assertEqual((d / "original.md").read_text(), first)  # the first draft is kept for the diff
        (d / "sanitized.md").write_text((d / "sanitized.md").read_text() + "\nextra line\n")
        r = self.c("confirm", "test-first-fix", "--verdict", "new")
        self.assertEqual(r.returncode, 1)
        self.assertIn("changed after check", r.stderr)
        self.assertEqual(self.c("check", "test-first-fix").returncode, 0)
        r = self.c("confirm", "test-first-fix", "--verdict", "new")
        self.assertEqual(r.returncode, 0, r.stderr)
        conf = json.loads((d / "confirmed.json").read_text())
        self.assertEqual((conf["verdict"], conf["target"]), ("new", "core/practices/plan/test-first-fix.md"))

    def test_extends_and_duplicate_verdicts(self):
        """S43: extends targets the installed upstream file; duplicate sends nothing; an unknown id is refused."""
        d = self.draft()
        self.c("check", "test-first-fix")
        r = self.c("confirm", "test-first-fix", "--verdict", "duplicate:tests-first")
        self.assertEqual(r.returncode, 1)
        self.assertIn("duplicate of tests-first; nothing to send", r.stderr)
        self.assertFalse((d / "confirmed.json").exists())
        r = self.c("confirm", "test-first-fix", "--verdict", "extends:nope")
        self.assertEqual(r.returncode, 1)
        self.assertIn("verdict must be", r.stderr)
        self.assertEqual(self.c("confirm", "test-first-fix", "--verdict", "extends:tests-first").returncode, 0)
        self.assertEqual(json.loads((d / "confirmed.json").read_text())["target"], "core/practices/plan/tests-first.md")

    def test_new_twice_reports_draft(self):
        """SP9: starting the same idea again points at the existing draft."""
        d = self.draft()
        r = self.c("new", "test", "first", "fix")
        self.assertEqual(r.returncode, 0)
        self.assertIn("draft exists: %s" % d, r.stdout)
        self.assertTrue((d / "draft.md").exists())

    def test_discard_and_bad_slug(self):
        """S50 R16: discard needs --confirm; a slug that is not a slug never reaches the filesystem."""
        d = self.draft()
        self.assertEqual(self.c("discard", "test-first-fix").returncode, 2)
        self.assertTrue(d.exists())
        self.assertEqual(self.c("discard", "test-first-fix", "--confirm").returncode, 0)
        self.assertFalse(d.exists())
        w(self.proj / ".distiflow/x/draft.md", "outside the contrib folder")
        for slug in ("../x", "..", "A/b", "-rf"):
            with self.subTest(slug=slug):
                r = self.c("check", slug)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("not a contribution slug" if slug[0] != "-" else "error:", r.stderr)
        self.assertFalse((self.proj / ".distiflow/x/sanitized.md").exists())
