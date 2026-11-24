import json
import shutil

from tests.helpers import GoldenCase, practice, w, write_profile

PROFILE = '[project]\nname = "proj"\n[git]\npush = "%s"\nworktrees = %s\n'


class WorktreeCase(GoldenCase):
    """A repo with a committed profile, ignored task state, a bare remote and the gh stub."""
    practices = {}
    push, worktrees = "forbidden", "true"

    def setUp(self):
        super().setUp()
        self.gh_stub()
        self.root = self.fixture_root(practices=self.practices)
        self.proj = self.repo()
        write_profile(self.proj, PROFILE % (self.push, self.worktrees))
        w(self.proj / ".gitignore", ".golden/tasks/\n.golden/profile.local.toml\n")
        self.git("add", ".", cwd=self.proj)
        self.git("commit", "-q", "-m", "golden profile", cwd=self.proj)
        self.bare = self.tmp / "remote.git"
        self.git("init", "-q", "--bare", str(self.bare), cwd=self.tmp)
        self.git("remote", "add", "origin", str(self.bare), cwd=self.proj)
        self.git("push", "-q", "-u", "origin", "main", cwd=self.proj)

    def g(self, *args, session="s-1", cwd=None):
        return self.golden(*args, cwd=cwd or self.proj, root=self.root, session=session)

    def ok(self, *args, **kw):
        r = self.g(*args, **kw)
        self.assertEqual(r.returncode, 0, (args, r.stdout, r.stderr))
        return r

    def start(self, desc="add login", session="s-1"):
        before = set((self.proj / ".golden/tasks").glob("T-*"))
        self.ok("task", "start", "feature", *desc.split(), session=session)
        return (set((self.proj / ".golden/tasks").glob("T-*")) - before).pop().name

    def advance_to(self, tid, stage, session="s-1"):
        while self.st(tid)["stage"] != stage:
            r = self.g("advance", tid, session=session)
            if r.returncode:
                return r
        return r

    def st(self, tid):
        return json.loads((self.proj / ".golden/tasks" / tid / "state.json").read_text())

    def wt(self, tid):
        return self.tmp / "proj.golden" / tid

    def head(self, cwd):
        return self.git("rev-parse", "HEAD", cwd=cwd).strip()

    def commit_in(self, cwd, name="feature.txt"):
        w(cwd / name, "work\n")
        self.git("add", name, cwd=cwd)
        self.git("commit", "-q", "-m", "work", cwd=cwd)


class Worktree(WorktreeCase):
    practices = {"implement/g-impl.md": practice("g-impl", ["implement"], gate=True, evidence="tests pass")}

    def test_implement_gets_own_working_copy(self):
        """T10 S13: implement gets a worktree on the task branch; the main checkout is untouched."""
        tid = self.start()
        head = self.head(self.proj)
        r = self.advance_to(tid, "implement")
        self.assertEqual(r.returncode, 0, r.stderr)
        st = self.st(tid)
        self.assertEqual((st["worktree"], st["branch"]), (str(self.wt(tid)), "feat/add-login_%s" % tid))
        self.assertEqual(self.git("branch", "--show-current", cwd=self.wt(tid)).strip(), st["branch"])
        self.assertEqual((self.git("status", "--porcelain", cwd=self.proj), self.head(self.proj)), ("", head))
        self.assertEqual(self.git("branch", "--show-current", cwd=self.proj).strip(), "main")

    def test_existing_worktree_reused(self):
        """T10 R29: a worktree made before a failed state write is reused on the next advance."""
        tid = self.start()
        self.advance_to(tid, "plan")
        self.git("worktree", "add", "-q", "-b", "feat/add-login_%s" % tid, str(self.wt(tid)), "main", cwd=self.proj)
        self.ok("advance", tid)
        self.assertEqual(self.st(tid)["worktree"], str(self.wt(tid)))

    def test_worktree_add_failure_changes_nothing(self):
        """T10 R29: when git cannot add the worktree, the stage stays where it was."""
        tid = self.start()
        self.advance_to(tid, "plan")
        w(self.wt(tid) / "junk.txt", "x")  # a plain directory in the way
        r = self.g("advance", tid)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.st(tid)["stage"], "plan")

    def test_ship_lifecycle(self):
        """T10 I12 I15 S15 S16 R4 R34: ship waits for a merge, cleans up after it, and is safe to repeat."""
        tid = self.start()
        self.advance_to(tid, "implement")
        r = self.g("ship", tid)
        self.assertEqual(r.returncode, 1)
        self.assertIn("ship comes after review", r.stderr)
        self.ok("gate", "pass", tid, "g-impl", "--evidence", "ok")
        self.advance_to(tid, "ship")
        branch = self.st(tid)["branch"]
        self.commit_in(self.wt(tid))
        r = self.ok("ship", tid)
        self.assertEqual(self.st(tid)["status"], "awaiting-merge")
        self.assertTrue(self.wt(tid).exists())
        self.assertIn("gh pr create --head %s --base main" % branch, r.stdout)
        # squash merge: the change lands on main with no ancestry to the branch
        self.git("cherry-pick", "--no-commit", branch, cwd=self.proj)
        self.git("commit", "-q", "-m", "squash", cwd=self.proj)
        self.git("push", "-q", "origin", "main", cwd=self.proj)
        self.ok("ship", tid)
        self.assertEqual(self.st(tid)["status"], "awaiting-merge")
        self.env["GH_STUB_MERGED"] = branch
        r = self.ok("ship", tid)
        self.assertEqual(self.st(tid)["status"], "done")
        self.assertFalse(self.wt(tid).exists())
        self.assertFalse((self.proj / ".golden/tasks" / tid / "claim").exists())
        r = self.ok("ship", tid)
        self.assertIn("task %s is already done" % tid, r.stdout)

    def test_ship_merged_flag_without_gh(self):
        """T10 F2 R34: with gh signed out and no ancestry, the developer's --merged confirms the merge."""
        self.env["GH_STUB_AUTH"] = "missing"
        tid = self.start()
        self.advance_to(tid, "implement")
        self.ok("gate", "pass", tid, "g-impl", "--evidence", "ok")
        self.advance_to(tid, "ship")
        self.commit_in(self.wt(tid))
        self.ok("ship", tid)
        self.assertEqual(self.st(tid)["status"], "awaiting-merge")
        self.ok("ship", tid, "--merged")
        self.assertEqual((self.st(tid)["status"], self.wt(tid).exists()), ("done", False))

    def test_locked_worktree_cleanup_pending(self):
        """T10 S18: a failed cleanup is visible and a rerun finishes it."""
        tid = self.start()
        self.advance_to(tid, "implement")
        self.ok("gate", "pass", tid, "g-impl", "--evidence", "ok")
        self.advance_to(tid, "ship")
        self.git("worktree", "lock", str(self.wt(tid)), cwd=self.proj)
        r = self.g("ship", tid)
        self.assertEqual(r.returncode, 1)
        self.assertIn("cleanup pending:", r.stderr)
        self.assertIn("retry with golden ship %s" % tid, r.stderr)
        self.assertEqual(self.st(tid)["status"], "cleanup-pending")
        self.git("worktree", "unlock", str(self.wt(tid)), cwd=self.proj)
        self.ok("ship", tid)
        self.assertEqual((self.st(tid)["status"], self.wt(tid).exists()), ("done", False))

    def test_cleanup_pending_remembers_merge(self):
        """T10 S18 I12: a confirmed merge stays confirmed when cleanup is retried and gh no longer sees it."""
        tid = self.start()
        self.advance_to(tid, "implement")
        self.ok("gate", "pass", tid, "g-impl", "--evidence", "ok")
        self.advance_to(tid, "ship")
        self.commit_in(self.wt(tid))
        self.env["GH_STUB_MERGED"] = self.st(tid)["branch"]
        self.git("worktree", "lock", str(self.wt(tid)), cwd=self.proj)
        self.assertEqual(self.g("ship", tid).returncode, 1)
        self.env["GH_STUB_MERGED"] = ""
        self.git("worktree", "unlock", str(self.wt(tid)), cwd=self.proj)
        self.ok("ship", tid)
        self.assertEqual((self.st(tid)["status"], self.wt(tid).exists()), ("done", False))

    def test_deleted_worktree_detected_and_restored(self):
        """T10 S38: resume warns about a deleted working copy; restore brings it back from the branch."""
        tid = self.start()
        self.advance_to(tid, "implement")
        self.commit_in(self.wt(tid))
        shutil.rmtree(self.wt(tid))
        (self.proj / ".golden/tasks" / tid / "claim").unlink()
        r = self.ok("task", "resume", tid)
        self.assertIn("working copy missing: %s; restore with golden worktree restore %s" % (self.wt(tid), tid), r.stdout)
        r = self.ok("worktree", "restore", tid)
        self.assertIn("uncommitted work in the old copy is gone", r.stdout)
        self.assertTrue((self.wt(tid) / "feature.txt").exists())
        self.assertEqual(self.g("worktree", "restore", tid).returncode, 1)

    def test_abandon_shows_then_removes(self):
        """T10 I15 S39: abandon lists uncommitted work and removes nothing until confirmed."""
        tid = self.start()
        self.advance_to(tid, "implement")
        w(self.wt(tid) / "dirty.txt", "unsaved")
        r = self.g("task", "abandon", tid)
        self.assertEqual(r.returncode, 2)
        self.assertIn("?? dirty.txt", r.stdout + r.stderr)
        self.assertIn("nothing removed", r.stdout + r.stderr)
        self.assertTrue((self.wt(tid) / "dirty.txt").exists())
        self.ok("task", "abandon", tid, "--confirm")
        self.assertEqual((self.st(tid)["status"], self.wt(tid).exists()), ("abandoned", False))
        self.assertFalse((self.proj / ".golden/tasks" / tid / "claim").exists())

    def test_golden_from_worktree_cwd(self):
        """Review Focus 2: golden run inside the worktree writes state in the main checkout, nothing in the worktree."""
        tid = self.start()
        self.advance_to(tid, "implement")
        sub = self.wt(tid) / "sub"
        sub.mkdir()
        self.ok("gate", "pass", tid, "g-impl", "--evidence", "ok", cwd=sub)
        self.assertIn("g-impl", self.st(tid)["runs"][-1]["evidence"])
        self.assertEqual(self.git("status", "--porcelain", "--ignored", cwd=self.wt(tid)), "")
