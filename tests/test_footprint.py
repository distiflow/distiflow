from tests.helpers import practice
from tests.test_worktree import WorktreeCase


class Footprint(WorktreeCase):
    practices = {"understand/g.md": practice("g", ["understand"], gate=True)}

    def snapshot(self):
        return {p: "dir" if p.is_dir() else (p.stat().st_size, p.stat().st_mtime_ns) for p in self.tmp.rglob("*")}

    def stray(self, before, after):
        changed = {p for p in after if before.get(p) != after[p]} | (set(before) - set(after))
        allowed = (self.proj / ".golden", self.tmp / "proj.golden", self.proj / ".git", self.bare, self.gh_dir)
        return sorted(str(p.relative_to(self.tmp)) for p in changed if not any(p.is_relative_to(a) for a in allowed))

    def test_footprint_full_lifecycle(self):
        """T29 R53: a whole task writes only in .golden/, the worktree dir, git's own dirs, the remote and gh."""
        before = self.snapshot()
        tid = self.start()
        self.ok("gate", "pass", tid, "g", "--evidence", "ok")
        self.advance_to(tid, "verify")
        self.assertEqual(self.stray(before, self.snapshot()), [])  # mid-task: the working copy exists
        self.advance_to(tid, "ship")
        self.ok("ship", tid)
        self.assertEqual(self.st(tid)["status"], "done")
        self.assertEqual(self.stray(before, self.snapshot()), [])
