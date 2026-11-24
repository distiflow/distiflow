from distiflow.overlay import load_practices, load_toml
from distiflow.practices import Malformed, parse_practice
from tests.helpers import KINDS, DistiflowCase, header, practice, sha_of, w


class Overlay(DistiflowCase):
    def test_practice_parse_errors_name_the_reason(self):
        """R10 S22: a malformed practice is rejected with a reason, never half-loaded."""
        rows = {"no-fence": "id='a'", "unclosed": "+++\nid='a'\n", "bad-toml": "+++\nid=\n+++\n",
                "unknown-key": practice("a", ["plan"]).replace("priority", "prio"),
                "bad-stage": practice("a", ["deploy"]),
                "bad-kind": practice("a", ["plan"], kinds=["refactor"]),
                "bad-cost": practice("a", ["plan"], run_cost="huge"),
                "wrong-type": practice("a", ["plan"]).replace("priority = 50", 'priority = "high"'),
                "id-mismatch": practice("b", ["plan"]),
                "gate-no-evidence": practice("a", ["plan"], gate=True).replace('evidence = "e"', 'evidence = ""')}
        for name, text in rows.items():
            with self.subTest(name):
                p = self.tmp / "a.md"
                p.write_text(text)
                with self.assertRaises(Malformed) as e:
                    parse_practice(p, "local", KINDS)
                self.assertTrue(e.exception.reason)

    def test_valid_practice_parses(self):
        """R10: the happy path keeps every field and skips an override header."""
        p = w(self.tmp / "a.md", header("abc") + practice("a", ["plan", "verify"], kinds=["fix"],
                                                          gate=True, evidence="ran it", priority=70))
        got = parse_practice(p, "overridden", KINDS)
        self.assertEqual((got.id, got.stages, got.kinds, got.gate, got.evidence, got.priority, got.source),
                         ("a", ("plan", "verify"), ("fix",), True, "ran it", 70, "overridden"))
        self.assertEqual(got.body.strip(), "text")

    def test_local_clash_does_not_replace_upstream(self):
        """S23 I9: a local practice never silently replaces an upstream one."""
        root = self.fixture_root(practices={"plan/a.md": practice("a", ["plan"], body="UP")})
        proj = self.repo()
        w(proj / ".distiflow/practices/plan/a.md", practice("a", ["plan"], body="LOCAL"))
        ps, issues = load_practices(root, proj)
        self.assertEqual([p.body.strip() for p in ps if p.id == "a"], ["UP"])
        self.assertIn(("clash", "a"), [(i.kind, i.ref) for i in issues])

    def test_override_replaces_and_reports_drift_and_orphan(self):
        """S60 S61 R49 I10: an override wins, and upstream change or removal is reported."""
        root = self.fixture_root(practices={"plan/a.md": practice("a", ["plan"], body="v1")})
        proj = self.repo()
        w(proj / ".distiflow/overrides/practices/plan/a.md",
          header(sha_of(root, "practices/plan/a.md")) + practice("a", ["plan"], body="mine"))
        ps, issues = load_practices(root, proj)
        self.assertEqual(next(p for p in ps if p.id == "a").source, "overridden")
        self.assertFalse(issues)
        w(root / "core/practices/plan/a.md", practice("a", ["plan"], body="v2"))
        ps, issues = load_practices(root, proj)
        self.assertEqual(next(p for p in ps if p.id == "a").body.strip(), "mine")
        self.assertIn("drift", [i.kind for i in issues])
        (root / "core/practices/plan/a.md").unlink()
        self.assertIn("orphan", [i.kind for i in load_practices(root, proj)[1]])

    def test_toml_override_merges_and_survives_removed_key(self):
        """R50: an override key upstream no longer has is ignored and reported, not a crash."""
        root = self.fixture_root()
        proj = self.repo()
        w(proj / ".distiflow/overrides/limits.toml",
          "# distiflow-override upstream=x version=0.1.0\n[budget]\nplan = 9000\n[gone]\nk = 1\n")
        merged, issues = load_toml("limits.toml", root, proj)
        self.assertEqual((merged["budget"]["plan"], merged["budget"]["verify"]), (9000, 3000))
        self.assertNotIn("gone", merged)
        self.assertIn("stale-key", [i.kind for i in issues])
