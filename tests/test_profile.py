from tests.helpers import DistiflowCase, header, practice, sha_of, w, write_profile

# (name, committed, local, expected exit, expected substring)
T16_ROWS = [  # S6 R51
    ("typo key", '[git]\nworktree = false\n', None, 1,
     "profile.toml: git.worktree: unknown key (did you mean worktrees?)"),
    ("wrong type", '[git]\nworktrees = "no"\n', None, 1, "git.worktrees: expected boolean"),
    ("bad enum", '[git]\npush = "sometimes"\n', None, 1, "git.push: expected one of allowed, forbidden"),
    ("bad role", '[models.wizard]\nmodel = "opus"\n', None, 1, "models.wizard: unknown role"),
    ("bad effort", '[models.scout]\neffort = "huge"\n', None, 1, "models.scout.effort: expected one of"),
    ("bad budget", '[cost.budget]\nplan = 0\n', None, 1, "cost.budget.plan: expected integer > 0"),
    ("option base", '[git]\nbase = "--upload-pack=touch pwned"\n', None, 1, "git.base: expected a branch name"),
    ("bad toml", '[git\n', None, 1, "profile.toml: invalid TOML"),
    ("local typo", '', '[cost]\nrun_capp = "cheap"\n', 1, "profile.local.toml: cost.run_capp: unknown key"),
    ("unknown disable id", '[[practices.disable]]\nid = "zz"\n', None, 0, "practices.disable: zz: unknown practice"),
    ("valid", '[project]\nname = "p"\n[git]\nworktrees = false\n', None, 0, "profile ok"),
]
# (name, committed, local, override files, expected exit, expected substring)
T9_ROWS = [  # I6 I16 S28 S29 R41 — fixture core has gate practice "g" and non-gate "n"
    ("gate no reason", '[[gates.disable]]\nid = "g"\n', None, {}, 1, "gates.disable: g: reason required"),
    ("gate empty reason", '[[gates.disable]]\nid = "g"\nreason = " "\n', None, {}, 1, "reason required"),
    ("gate with reason", '[[gates.disable]]\nid = "g"\nreason = "no UI"\n', None, {}, 0, "profile ok"),
    ("personal gates key", '', '[[gates.disable]]\nid = "g"\nreason = "x"\n', {}, 1,
     "gates change only in the committed profile"),
    ("personal practice=gate", '', '[[practices.disable]]\nid = "g"\nreason = "x"\n', {}, 1,
     "gates change only in the committed profile"),
    ("practices.disable gate", '[[practices.disable]]\nid = "g"\n', None, {}, 1, "g is a gate: reason required"),
    ("override gate=false", '', None, {"practices/verify/g.md": "gate=false"}, 1,
     "override turns gate g off: add [[gates.disable]] with a reason"),
    ("override gate=false ok", '[[gates.disable]]\nid = "g"\nreason = "r"\n', None,
     {"practices/verify/g.md": "gate=false"}, 0, "profile ok"),
    ("non-gate no reason", '[[practices.disable]]\nid = "n"\n', None, {}, 0, "profile ok"),
]


class Profile(DistiflowCase):
    def setUp(self):
        super().setUp()
        self.root = self.fixture_root(practices={
            "verify/g.md": practice("g", ["verify"], gate=True),
            "plan/n.md": practice("n", ["plan"])})

    def check(self, committed, local, overrides=None):
        proj = self.repo("p%d" % len(list(self.tmp.iterdir())))
        write_profile(proj, committed, local)
        for rel in overrides or {}:
            w(proj / ".distiflow/overrides" / rel,
              header(sha_of(self.root, rel)) + practice("g", ["verify"], gate=False))
        r = self.distiflow("profile", "check", cwd=proj, root=self.root)
        return r.returncode, r.stdout + r.stderr

    def test_profile_validation_table(self):
        """T16 S6 R51: a bad profile key or value is an error naming file and key, never ignored."""
        for name, committed, local, code, text in T16_ROWS:
            with self.subTest(name):
                got, out = self.check(committed, local)
                self.assertEqual(got, code, out)
                self.assertIn(text, out)

    def test_gate_disable_routes_table(self):
        """T9 I6 I16 S28 S29 R41: a gate is disabled only in the committed profile, with a reason."""
        for name, committed, local, overrides, code, text in T9_ROWS:
            with self.subTest(name):
                got, out = self.check(committed, local, overrides)
                self.assertEqual(got, code, out)
                self.assertIn(text, out)
