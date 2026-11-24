from tests.helpers import DistiflowCase, header, practice, sha_of, w


class Override(DistiflowCase):
    def setUp(self):
        super().setUp()
        self.root = self.fixture_root(practices={"plan/a.md": practice("a", ["plan"], body="up")})
        self.proj = self.repo()

    def test_override_writes_header_and_listed(self):
        """S62 I10: an override starts from the upstream bytes and records which upstream it shadows."""
        rel = "practices/plan/a.md"
        r = self.distiflow("override", rel, cwd=self.proj, root=self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        text = (self.proj / ".distiflow/overrides" / rel).read_text()
        self.assertEqual(text, header(sha_of(self.root, rel)) + (self.root / "core" / rel).read_text())
        self.assertIn(rel + " ok", self.distiflow("override", "list", cwd=self.proj, root=self.root).stdout)
        w(self.root / "core" / rel, practice("a", ["plan"], body="changed"))
        self.assertIn(rel + " drift", self.distiflow("override", "list", cwd=self.proj, root=self.root).stdout)

    def test_override_refuses_escape_and_existing(self):
        """R16 R53: override never writes outside .distiflow/overrides and never replaces an existing one."""
        self.assertEqual(self.distiflow("override", "practices/plan/a.md", cwd=self.proj, root=self.root).returncode, 0)
        outside = w(self.tmp / "abs.md", "x")
        w(self.root / "escape.md", "x")
        before = sorted(self.tmp.rglob("*"))
        for rel in ("../x", "/etc/passwd", str(outside), "../escape.md", "practices/../../escape.md",
                    "practices/plan/zz.md", "practices/plan/a.md"):
            with self.subTest(rel):
                r = self.distiflow("override", rel, cwd=self.proj, root=self.root)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertTrue(r.stderr.startswith("distiflow: "), r.stderr)
        self.assertEqual(sorted(self.tmp.rglob("*")), before)
