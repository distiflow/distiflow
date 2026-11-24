import json
import shlex

from tests.helpers import GoldenCase, practice, w, write_profile

# (name, command sequence, expected last exit, expected substring) — T8 I5 S11 S12 S19 S37 R1-R3 R6
ROWS = [
    ("advance without evidence", ["advance"], 1, "failing gate: g-under (repro shown)"),
    ("advance with evidence", ["pass g-under ok", "advance"], 0, "stage 2/6 plan"),
    ("wrong-stage evidence", ["pass g-plan x"], 1, "gate g-plan is not a gate of stage understand"),
    ("unknown gate", ["pass zz x"], 1, "gate zz is not a gate of stage understand"),
    ("empty evidence", ["pass g-under '  '"], 2, "evidence is empty"),
    ("evidence from file", ["<write ev.txt>", "pass g-under @ev.txt", "show"], 0, "g-under: line one"),
    ("evidence file too big", ["<write big.txt>", "pass g-under @big.txt"], 1, "over 20000 characters"),
    ("advance past ship", ["<walk to ship>", "advance"], 1, "ship is the last stage; run golden ship"),
    ("reopen future stage", ["reopen verify"], 1, "stage verify is not reached yet"),
    ("reopen keeps evidence", ["pass g-under ok", "advance", "reopen understand", "show"], 0,
     "g-under: ok (carried from run 1)"),
    ("reopen --recheck", ["pass g-under ok", "advance", "reopen understand --recheck", "advance"], 1,
     "failing gate: g-under"),
    ("reopen sets the stage", ["pass g-under ok", "advance", "pass g-plan p", "reopen understand", "advance"], 0,
     "stage 2/6 plan"),
    ("re-entry by advance carries", ["pass g-under ok", "advance", "pass g-plan p", "reopen understand", "advance",
                                     "show"], 0, "g-plan: p (carried from run 1)"),
    ("snapshot not live", ["<add gate g-new>", "pass g-under ok", "advance"], 0, "stage 2/6 plan"),
    ("non-holder cannot pass", ["<as s-2> pass g-under ok"], 1, "you do not hold task"),
    ("new run belongs to the advancer", ["pass g-under ok", "advance", "<release>", "<as s-2> resume"], 0,
     "stage 2/6 plan (interrupted)"),
]


class Gates(GoldenCase):
    def setUp(self):
        super().setUp()
        self.root = self.fixture_root(practices={
            "understand/g-under.md": practice("g-under", ["understand"], gate=True, evidence="repro shown"),
            "plan/g-plan.md": practice("g-plan", ["plan"], gate=True, evidence="plan reviewed")})
        self.proj = self.repo()
        write_profile(self.proj, '[project]\nname = "proj"\n[git]\nworktrees = false\n')
        r = self.g("task", "start", "fix", "login")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.task = next((self.proj / ".golden/tasks").glob("T-*"))
        self.id = self.task.name

    def g(self, *args, session="s-1"):
        return self.golden(*args, cwd=self.proj, root=self.root, session=session)

    def run_step(self, step):
        session = "s-1"
        if step.startswith("<as s-2> "):
            session, step = "s-2", step[len("<as s-2> "):]
        if step == "<walk to ship>":
            for s in ("pass g-under ok", "advance", "pass g-plan ok", "advance", "advance", "advance", "advance"):
                r = self.run_step(s)
                self.assertEqual(r.returncode, 0, (s, r.stdout, r.stderr))
            self.assertIn("ship", json.loads((self.task / "state.json").read_text())["stage"])
            return r
        if step == "<add gate g-new>":
            w(self.root / "core/practices/understand/g-new.md", practice("g-new", ["understand"], gate=True))
            return None
        if step == "<release>":
            (self.task / "claim").unlink()
            return None
        if step.startswith("<write "):
            name = step[len("<write "):-1]
            w(self.proj / name, "line one\nline two\n" if name == "ev.txt" else "x" * 20001)
            return None
        verb, *rest = shlex.split(step)
        if verb == "pass":
            return self.g("gate", "pass", self.id, rest[0], "--evidence", *rest[1:], session=session)
        argv = {"advance": ["advance", self.id],
                "reopen": ["stage", "reopen", self.id, *rest],
                "show": ["task", "show", self.id],
                "resume": ["task", "resume", self.id]}[verb]
        return self.g(*argv, session=session)

    def test_gate_state_machine(self):
        """T8 I5 S11 S12 S19 S37 R1-R3 R6: stages advance only on evidence from the stage's own snapshot."""
        for name, steps, code, text in ROWS:
            with self.subTest(row=name):
                self.setUp()
                r = None
                for step in steps:
                    r = self.run_step(step) or r
                self.assertEqual(r.returncode, code, (r.stdout, r.stderr))
                self.assertIn(text, r.stdout + r.stderr)
                self.doCleanups()

    def test_failed_advance_changes_nothing(self):
        """I5 R57: a refused advance leaves state and snapshots as they were."""
        before = (self.task / "state.json").read_bytes()
        self.assertEqual(self.g("advance", self.id).returncode, 1)
        self.assertEqual((self.task / "state.json").read_bytes(), before)
        self.assertFalse((self.task / "stage-2-brief.md").exists())

    def test_advance_records_evidence_and_snapshot(self):
        """S12 S40: passed gates keep evidence with who and when; the next stage gets its own brief snapshot."""
        self.g("gate", "pass", self.id, "g-under", "--evidence", "repro: test_login fails")
        r = self.g("advance", self.id)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("start a fresh session: /golden:task resume %s" % self.id, r.stdout)
        st = json.loads((self.task / "state.json").read_text())
        ev = st["runs"][0]["evidence"]["g-under"]
        self.assertEqual((ev["text"], ev["session"], st["stage"]), ("repro: test_login fails", "s-1", "plan"))
        self.assertIsNotNone(st["runs"][0]["ended"])
        self.assertEqual(st["runs"][1]["gates"], [{"id": "g-plan", "evidence_wanted": "plan reviewed"}])
        snap = (self.task / "stage-2-brief.md").read_text()
        self.assertTrue(snap.startswith("# %s · fix · stage 2/6 plan" % self.id))
        self.assertIn(snap, r.stdout)
