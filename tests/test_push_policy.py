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

    def test_push_with_deleted_worktree(self):
        """T4 S38: a deleted working copy does not break the push; the branch is pushed from the main checkout."""
        tid = self.start()
        self.advance_to(tid, "ship")
        branch = self.st(tid)["branch"]
        self.commit_in(self.wt(tid))
        __import__("shutil").rmtree(self.wt(tid))
        r = self.g("ship", tid)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(branch, self.git("ls-remote", "--heads", str(self.bare), branch, cwd=self.tmp))

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
        self.assertEqual(self.git("ls-remote", "--heads", str(self.bare), cwd=self.tmp).count("refs/heads/"), 1)


from tests.test_contrib_send import SendCase  # noqa: E402


class ContribPushForbidden(SendCase):
    def test_push_forbidden_contribute_never_pushes(self):
        """T4 I14 S63: in a no-push project the contribution stops at a local branch and a hand-off."""
        from tests.test_contrib_check import PROFILE
        from tests.helpers import write_profile
        write_profile(self.proj, PROFILE + '[git]\npush = "forbidden"\n')
        self.ready()
        r = self.c("send", "test-first-fix")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("push -u origin contrib/test-first-fix", r.stdout)
        self.assertIn("gh pr create", r.stdout)
        self.assertEqual((self.contrib_refs(), self.gh_state()["prs"]), ([], []))
        log = self.git("log", "--oneline", "origin/main..contrib/test-first-fix", cwd=self.clone)
        self.assertIn("feat(practices): add test-first-fix", log)
