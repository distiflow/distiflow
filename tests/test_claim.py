import json
import os
from unittest import mock
import threading
import time

from tests.helpers import GoldenCase, practice, write_profile

N = 8
STALE = 1800


class ClaimCase(GoldenCase):
    def setUp(self):
        super().setUp()
        self.root = self.fixture_root(practices={"understand/g.md": practice("g", ["understand"], gate=True)})
        self.proj = self.repo()
        write_profile(self.proj)

    def run_all(self, argvs):
        """Start every golden process at the same instant; threads only launch, the racers are processes."""
        barrier, out = threading.Barrier(len(argvs)), [None] * len(argvs)

        def go(i, session, args):
            barrier.wait()
            out[i] = self.golden(*args, cwd=self.proj, root=self.root, session=session)

        ts = [threading.Thread(target=go, args=(i, s, a)) for i, (s, a) in enumerate(argvs)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        return out

    def start(self, session="s-1"):
        r = self.golden("task", "start", "feature", "add", "login", cwd=self.proj, root=self.root, session=session)
        self.assertEqual(r.returncode, 0, r.stderr)
        return sorted((self.proj / ".golden/tasks").iterdir())[-1]

    def holder(self, task):
        return json.loads((task / "claim").read_text())["session"]

    def age(self, task, seconds):
        t = time.time() - seconds
        os.utime(task / "claim", (t, t))


class ClaimRace(ClaimCase):
    def test_parallel_starts_unique_ids_and_one_holder(self):
        """T5 I3 S31 R18: parallel starts get distinct ids, each claimed by its own starter."""
        for rnd in range(5):
            with self.subTest(round=rnd):
                before = set((self.proj / ".golden/tasks").glob("T-*")) if rnd else set()
                rs = self.run_all([("s-%d" % i, ("task", "start", "feature", "x")) for i in range(N)])
                self.assertEqual([r.returncode for r in rs], [0] * N, [r.stderr for r in rs])
                new = set((self.proj / ".golden/tasks").glob("T-*")) - before
                self.assertEqual(len(new), N)
                self.assertEqual(sorted(self.holder(t) for t in new), sorted("s-%d" % i for i in range(N)))

    def test_parallel_resume_one_holder(self):
        """T5 I3 S33: a free task resumed by many sessions at once gets exactly one holder."""
        task = self.start()
        for rnd in range(5):
            with self.subTest(round=rnd):
                (task / "claim").unlink()
                rs = self.run_all([("r%d-%d" % (rnd, i), ("task", "resume", task.name)) for i in range(N)])
                winners = [i for i, r in enumerate(rs) if r.returncode == 0]
                self.assertEqual(len(winners), 1, [(r.returncode, r.stderr) for r in rs])
                won = "r%d-%d" % (rnd, winners[0])
                self.assertEqual(self.holder(task), won)
                for r in rs:
                    if r.returncode != 0:
                        self.assertEqual(r.returncode, 1)
                        self.assertIn("is held by %s" % won, r.stderr)

    def test_stale_takeover_race_one_winner(self):
        """T6 I3 I12 S34 R19: many takers of one stale claim, exactly one wins and keeps it."""
        task = self.start()
        for rnd in range(5):
            with self.subTest(round=rnd):
                self.age(task, STALE + 1)
                rs = self.run_all([("t%d-%d" % (rnd, i), ("task", "takeover", task.name, "--confirm"))
                                   for i in range(N)])
                winners = [i for i, r in enumerate(rs) if r.returncode == 0]
                self.assertEqual(len(winners), 1, [(r.returncode, r.stderr) for r in rs])
                self.assertEqual(self.holder(task), "t%d-%d" % (rnd, winners[0]))
                self.assertEqual({r.returncode for r in rs}, {0, 1})
        self.assertEqual(len(list(task.glob("claim.lost.*"))), 5)

    def test_old_heartbeat_cannot_steal_back(self):
        """T6 R20: the old holder's heartbeat never takes the claim back or rewrites it."""
        task = self.start("s-1")
        self.age(task, STALE + 1)
        r = self.golden("task", "takeover", task.name, "--confirm", cwd=self.proj, root=self.root, session="s-2")
        self.assertEqual(r.returncode, 0, r.stderr)
        before = (task / "claim").read_text()
        self.age(task, 100)
        for _ in range(50):
            self.hook("heartbeat", {"session_id": "s-1", "cwd": str(self.proj)}, session="s-1")
        self.assertEqual((task / "claim").read_text(), before)
        self.assertGreater(time.time() - (task / "claim").stat().st_mtime, 99)
        self.hook("heartbeat", {"session_id": "s-2", "cwd": str(self.proj / "sub")}, session="s-2")
        self.assertLess(time.time() - (task / "claim").stat().st_mtime, 50)

    def test_staleness_boundary(self):
        """T6 R24: a claim exactly at the limit is held; one second past it is stale."""
        task = self.start("s-1")
        self.age(task, STALE)
        r = self.golden("task", "resume", task.name, cwd=self.proj, root=self.root, session="s-2")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("is held by s-1", r.stderr)
        self.age(task, STALE + 1)
        r = self.golden("task", "resume", task.name, cwd=self.proj, root=self.root, session="s-2")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("take over with: golden task takeover %s --confirm" % task.name, r.stderr)
        self.assertEqual(self.holder(task), "s-1")

    def test_takeover_without_confirm_or_fresh_refused(self):
        """S34: takeover needs --confirm and a stale claim."""
        task = self.start("s-1")
        r = self.golden("task", "takeover", task.name, cwd=self.proj, root=self.root, session="s-2")
        self.assertEqual(r.returncode, 2)
        r = self.golden("task", "takeover", task.name, "--confirm", cwd=self.proj, root=self.root, session="s-2")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not stale", r.stderr)
        self.assertEqual((self.holder(task), list(task.glob("claim.lost.*"))), ("s-1", []))

    def test_list_shows_holder_and_stale(self):
        """S31: two tasks side by side, each with its holder; a silent one is marked stale."""
        a, b = self.start("s-1"), self.start("s-2")
        self.age(b, STALE + 1)
        r = self.golden("task", "list", cwd=self.proj, root=self.root, session=None)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        self.assertRegex(lines[0], r"^%s  understand  active  held by s-1 since \S+$" % a.name)
        self.assertRegex(lines[1], r"^%s  understand  active  held by s-2 since \S+ \(stale\)$" % b.name)


class TakeoverWindow(ClaimCase):
    def test_takeover_never_steals_a_fresh_claim(self):
        """T6 I3 I2: a claim renewed between the stale check and the link is not taken."""
        from golden import claim
        task = self.start("s-1")
        self.age(task, STALE + 1)
        real = claim.is_stale

        def stale_then_renewed(d, limit):
            out = real(d, limit)
            claim.release(d, "s-1")  # the old holder lets go and a third session claims, inside the window
            claim.claim(d, "s-3")
            return out

        with mock.patch.object(claim, "is_stale", side_effect=stale_then_renewed):
            with self.assertRaises(claim.LostRace):
                claim.takeover(task, "s-2", STALE)
        self.assertEqual((self.holder(task), list(task.glob("claim.lost.*"))), ("s-3", []))

    def test_newer_state_resume_refused_cleanly(self):
        """T13 I11 R48 I3: resume and takeover of newer state exit 1 with the update message and claim nothing."""
        task = self.start("s-1")
        st = json.loads((task / "state.json").read_text())
        (task / "state.json").write_text(json.dumps({**st, "schema": 2}))
        (task / "claim").unlink()
        for cmd in (("resume", task.name), ("takeover", task.name, "--confirm")):
            with self.subTest(cmd=cmd[0]):
                r = self.golden("task", *cmd, cwd=self.proj, root=self.root, session="s-2")
                self.assertEqual(r.returncode, 1)
                self.assertIn("update golden", r.stderr)
                self.assertNotIn("Traceback", r.stderr)
                self.assertFalse((task / "claim").exists())
