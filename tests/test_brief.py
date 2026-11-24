import tomllib

from tests.helpers import KINDS, REPO, GoldenCase, header, practice, sha_of, w, write_profile

EMPHASIS = {k: v["emphasis"] for k, v in tomllib.loads((REPO / "core/kinds.toml").read_text())["kinds"].items()}


def section(out, name):
    return out.split("## " + name + "\n", 1)[1].split("\n## ", 1)[0]


class Brief(GoldenCase):
    def brief(self, root, proj, stage="plan", kind="feature"):
        return self.golden("brief", "--stage", stage, "--kind", kind, cwd=proj, root=root)

    def setup(self, practices=None, profile=None):
        root = self.fixture_root(practices=practices or {})
        proj = self.repo()
        write_profile(proj, *(profile,) if profile is not None else ())
        return root, proj

    def test_brief_shows_loaded_cost_and_models(self):
        """S10: the brief shows each loaded practice with its run cost, and the model plan."""
        root, proj = self.setup({"understand/a.md": practice("a", ["understand"])})
        r = self.brief(root, proj, "understand")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("- a · cheap ·", section(r.stdout, "Practices loaded"))
        models = section(r.stdout, "Models")
        self.assertIn("scout: haiku/low", models)
        self.assertIn("session: sonnet (recommended)", models)

    def test_brief_model_override(self):
        """S26: a profile model override is applied and labelled."""
        root, proj = self.setup(profile='[models.reviewer]\nmodel = "sonnet"\neffort = "medium"\n')
        r = self.brief(root, proj, "review")
        self.assertIn("reviewer: sonnet/medium (profile override)", section(r.stdout, "Models"))

    def test_local_practice_marked_local(self):
        """S21: a project practice loads and is marked local."""
        root, proj = self.setup()
        w(proj / ".golden/practices/plan/l.md", practice("l", ["plan"]))
        loaded = section(self.brief(root, proj).stdout, "Practices loaded")
        self.assertRegex(loaded, r"- l · cheap · \d+ tok · local")

    def test_malformed_local_skipped_with_reason(self):
        """S22: a broken local practice is skipped with its file and reason; the brief still renders."""
        root, proj = self.setup()
        w(proj / ".golden/practices/plan/bad.md", "junk\n")
        r = self.brief(root, proj)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("- .golden/practices/plan/bad.md: malformed: missing +++ frontmatter",
                      section(r.stdout, "Not loaded"))

    def test_clash_reported(self):
        """S23: a local practice with an upstream id is reported, and upstream stays loaded."""
        root, proj = self.setup({"plan/a.md": practice("a", ["plan"], body="UP")})
        w(proj / ".golden/practices/plan/a.md", practice("a", ["plan"], body="LOCAL"))
        out = self.brief(root, proj).stdout
        self.assertIn("- a: clash:", section(out, "Not loaded"))
        self.assertIn("UP", section(out, "Practices loaded"))
        self.assertNotIn("LOCAL", out)

    def test_overridden_marked_and_drift_warned(self):
        """S60 S61: an override is marked, and an upstream change warns by name."""
        rel = "practices/plan/a.md"
        root, proj = self.setup({"plan/a.md": practice("a", ["plan"], body="v1")})
        w(proj / ".golden/overrides" / rel, header(sha_of(root, rel)) + practice("a", ["plan"], body="mine"))
        out = self.brief(root, proj).stdout
        self.assertRegex(section(out, "Practices loaded"), r"- a · cheap · \d+ tok · overridden")
        self.assertNotIn("changed upstream", out)
        w(root / "core" / rel, practice("a", ["plan"], body="v2"))
        self.assertIn(rel + " changed upstream", section(self.brief(root, proj).stdout, "Warnings"))

    def test_swapped_stage_keeps_gates(self):
        """S27: replacing a stage's text never removes its gates."""
        root, proj = self.setup({"plan/g.md": practice("g", ["plan"], gate=True, evidence="plan reviewed")})
        w(proj / ".golden/overrides/stages/plan.md", header(sha_of(root, "stages/plan.md")) + "My own plan stage.\n")
        out = self.brief(root, proj).stdout
        stage = section(out, "Stage")
        self.assertIn("(overridden locally)", stage)
        self.assertIn("My own plan stage.", stage)
        self.assertNotIn("golden-override", stage)
        self.assertIn("- g: plan reviewed", section(out, "Gates"))
        w(root / "core/stages/plan.md", "Upstream rewrote the plan stage.\n")
        self.assertIn("stages/plan.md changed upstream", section(self.brief(root, proj).stdout, "Warnings"))

    def test_kinds_table(self):
        """T20 S8: every kind shows all six stages and loads only its own practices."""
        root, proj = self.setup({"understand/k-%s.md" % k: practice("k-" + k, ["understand"], kinds=[k])
                                 for k in KINDS})
        for kind in KINDS:
            with self.subTest(kind):
                r = self.brief(root, proj, "understand", kind)
                self.assertEqual(r.returncode, 0, r.stderr)
                stages = section(r.stdout, "Stages")
                self.assertIn(EMPHASIS[kind]["plan"], stages)
                for s in ("understand", "plan", "implement", "verify", "review", "ship"):
                    self.assertIn(s, stages)
                loaded = [l.split(" · ")[0][2:] for l in section(r.stdout, "Practices loaded").splitlines()
                          if l.startswith("- ")]
                self.assertEqual(loaded, ["k-" + kind])

    def test_brief_profile_error_names_file_and_field(self):
        """S6 R51: a bad profile stops the brief and names the file and field."""
        root, proj = self.setup(profile='[git]\nworktree = false\n')
        r = self.brief(root, proj)
        self.assertEqual(r.returncode, 1)
        self.assertIn("profile.toml: git.worktree: unknown key", r.stderr)

    def test_unknown_kind_refused(self):
        """S9: a kind outside kinds.toml is refused with the valid list, not a traceback."""
        root, proj = self.setup()
        r = self.brief(root, proj, kind="refactor")
        self.assertEqual(r.returncode, 2)
        self.assertIn("golden: unknown kind refactor (one of feature, fix, debug, perf, ux)", r.stderr)
