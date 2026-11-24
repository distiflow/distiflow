from tests.test_worktree import WorktreeCase


class PushForbidden(WorktreeCase):
    push = "forbidden"

    def test_push_forbidden_ship_never_pushes(self):
        """T4 I14 S17: a no-push project gets a hand-off; nothing reaches the remote or GitHub."""
        tid = self.start()
        self.advance_to(tid, "ship")
        branch = self.st(tid)["branch"]
        self.commit_in(self.wt(tid))
        r = self.ok("ship", tid)
        self.assertIn("git push -u origin %s" % branch, r.stdout)
        self.assertEqual(self.git("ls-remote", "--heads", str(self.bare), branch, cwd=self.tmp), "")
        self.assertEqual(self.gh_state()["prs"], [])
        self.assertEqual(self.st(tid)["status"], "awaiting-merge")


class PushAllowed(WorktreeCase):
    push = "allowed"

    def test_push_allowed_ship_opens_one_request(self):
        """T4 control, I12: an allowed push lands the branch and one request; a rerun reuses it."""
        tid = self.start()
        self.advance_to(tid, "ship")
        branch = self.st(tid)["branch"]
        self.commit_in(self.wt(tid))
        r = self.ok("ship", tid)
        self.assertIn("https://example.invalid/pull/1", r.stdout)
        self.assertIn(branch, self.git("ls-remote", "--heads", str(self.bare), branch, cwd=self.tmp))
        self.ok("ship", tid)
        self.assertEqual([p["head"] for p in self.gh_state()["prs"]], [branch])

    def test_dirty_copy_blocks_push(self):
        """T4: uncommitted work stops ship before anything is pushed."""
        tid = self.start()
        self.advance_to(tid, "ship")
        self.commit_in(self.wt(tid))
        (self.wt(tid) / "dirty.txt").write_text("x")
        r = self.g("ship", tid)
        self.assertEqual(r.returncode, 1)
        self.assertIn("?? dirty.txt", r.stderr)
        self.assertEqual(self.gh_state()["prs"], [])
