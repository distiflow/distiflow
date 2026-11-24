import threading

from tests.helpers import w
from tests.test_worktree import WorktreeCase


class WorktreesOff(WorktreeCase):
    worktrees = "false"

    def branch(self):
        return self.git("branch", "--show-current", cwd=self.proj).strip()

    def test_shared_checkout(self):
        """T11 S14 S36 R5 R22: one task holds the checkout; a second cannot switch it; abandon deletes nothing."""
        a = self.start("task a", session="s-1")
        b = self.start("task b", session="s-2")
        r = self.advance_to(a, "implement", session="s-1")
        self.assertIn("parallel implement is unavailable in this project (worktrees off)", r.stdout)
        self.assertEqual(self.branch(), "feat/task-a_%s" % a)
        r = self.advance_to(b, "implement", session="s-2")
        self.assertEqual(r.returncode, 1)
        self.assertIn("the checkout is in use by task %s" % a, r.stderr)
        self.assertEqual((self.branch(), self.st(b)["stage"]), ("feat/task-a_%s" % a, "plan"))
        w(self.proj / "dirty.txt", "unsaved")
        r = self.ok("task", "abandon", a, "--confirm", session="s-1")
        self.assertIn("changes left in the main checkout on feat/task-a_%s" % a, r.stdout)
        self.assertTrue((self.proj / "dirty.txt").exists())
        self.assertFalse((self.proj / ".distiflow/tasks/checkout.claim").exists())
        self.assertEqual(self.st(a)["status"], "abandoned")

    def test_failed_switch_releases_checkout(self):
        """T11 R29: when git cannot switch, the checkout is not left claimed and the stage stays."""
        self.git("branch", "feat", cwd=self.proj)  # refs/heads/feat blocks creating feat/<slug>
        tid = self.start()
        r = self.advance_to(tid, "implement")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.st(tid)["stage"], "plan")
        self.assertFalse((self.proj / ".distiflow/tasks/checkout.claim").exists())

    def test_ship_releases_checkout(self):
        """T11 S15: a shipped task gives the shared checkout back to the next task."""
        a, b = self.start("task a", session="s-1"), self.start("task b", session="s-2")
        self.advance_to(a, "ship", session="s-1")
        self.ok("ship", a, session="s-1")
        self.assertEqual(self.st(a)["status"], "done")
        self.assertEqual(self.advance_to(b, "implement", session="s-2").returncode, 0)

    def test_task_branch_starts_at_base(self):
        """T11 R5: a task branch starts at base, not at whatever the shared checkout has on it."""
        self.git("switch", "-q", "-c", "other", cwd=self.proj)
        self.commit_in(self.proj, "other.txt")
        tid = self.start()
        self.assertEqual(self.advance_to(tid, "implement").returncode, 0)
        self.assertEqual(self.head(self.proj), self.git("rev-parse", "main", cwd=self.proj).strip())

    def test_dirty_checkout_never_ships_as_done(self):
        """T10 I15 R5: uncommitted work stops ship even when the branch has no commits of its own."""
        tid = self.start()
        self.advance_to(tid, "ship")
        (self.proj / "work.txt").write_text("unsaved")
        r = self.g("ship", tid)
        self.assertEqual(r.returncode, 1)
        self.assertIn("?? work.txt", r.stderr)
        self.assertEqual(self.st(tid)["status"], "active")
        self.assertTrue((self.proj / ".distiflow/tasks/checkout.claim").exists())

    def test_parallel_enter_one_wins(self):
        """T11 R22: two tasks entering implement at once, exactly one gets the checkout."""
        ids = [self.start("t%d" % i, session="s-%d" % i) for i in range(2)]
        for i, tid in enumerate(ids):
            self.advance_to(tid, "plan", session="s-%d" % i)
        barrier, out = threading.Barrier(2), [None, None]

        def go(i):
            barrier.wait()
            out[i] = self.g("advance", ids[i], session="s-%d" % i)

        ts = [threading.Thread(target=go, args=(i,)) for i in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(sorted(r.returncode for r in out), [0, 1], [r.stderr for r in out])
        self.assertEqual(sorted(self.st(t)["stage"] for t in ids), ["implement", "plan"])
