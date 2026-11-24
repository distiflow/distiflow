from tests.helpers import GoldenCase, w


class Layering(GoldenCase):
    def test_committed_and_personal_layering(self):
        """T18 S2 S3: a committed profile works for a teammate without init; a personal override stays personal."""
        root = self.fixture_root()
        bare = self.tmp / "remote.git"
        self.git("init", "-q", "--bare", str(bare), cwd=self.tmp)
        a = self.tmp / "a"
        self.git("clone", "-q", str(bare), str(a), cwd=self.tmp)
        w(a / "README.md", "x\n")
        proposal = self.golden("init", "--propose", cwd=a, root=root).stdout
        r = self.golden("init", "--write", "-", cwd=a, root=root, stdin=proposal)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.git("add", ".", cwd=a)
        self.git("commit", "-q", "-m", "golden", cwd=a)
        self.git("push", "-q", "origin", "HEAD", cwd=a)
        b = self.tmp / "b"
        self.git("clone", "-q", str(bare), str(b), cwd=self.tmp)
        w(a / ".golden/profile.local.toml", '[models.reviewer]\nmodel = "sonnet"\n')
        ra = self.golden("brief", "--stage", "review", "--kind", "fix", cwd=a, root=root)
        rb = self.golden("brief", "--stage", "review", "--kind", "fix", cwd=b, root=root)
        self.assertEqual((ra.returncode, rb.returncode), (0, 0), (ra.stderr, rb.stderr))
        self.assertIn("reviewer: sonnet/", ra.stdout)
        self.assertIn("(profile override)", ra.stdout)
        self.assertNotIn("(profile override)", rb.stdout)
        self.assertEqual(self.git("status", "--porcelain", cwd=a), "")
        self.assertEqual(self.git("status", "--porcelain", cwd=b), "")
