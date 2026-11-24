import json

from tests.helpers import DistiflowCase, practice, w, write_profile
from tests.test_profile import T9_ROWS, T16_ROWS


class Start(DistiflowCase):
    def setUp(self):
        super().setUp()
        self.root = self.fixture_root(practices={
            "understand/g.md": practice("g", ["understand"], gate=True, evidence="repro shown"),
            "verify/v.md": practice("v", ["verify"], gate=True)})
        self.proj = self.repo()

    def start(self, *args, session="s-1"):
        return self.distiflow("task", "start", *args, cwd=self.proj, root=self.root, session=session)

    def tasks(self):
        d = self.proj / ".distiflow/tasks"
        return sorted(d.iterdir()) if d.exists() else []

    def test_start_writes_state_claim_and_brief(self):
        """S31 I11: start claims the task, records run 1 with its gates and snapshots the brief."""
        write_profile(self.proj)
        r = self.start("fix", "login", "fails", "--link", "core#12")
        self.assertEqual(r.returncode, 0, r.stderr)
        [task] = self.tasks()
        self.assertRegex(task.name, r"^T-\d{8}-1$")
        st = json.loads((task / "state.json").read_text())
        self.assertEqual((st["kind"], st["desc"], st["stage"], st["links"]), ("fix", "login fails", "understand", ["core#12"]))
        self.assertEqual(st["runs"][0]["gates"], [{"id": "g", "evidence_wanted": "repro shown"}])
        self.assertEqual(json.loads((task / "claim").read_text())["session"], "s-1")
        brief = (task / "stage-1-brief.md").read_text()
        self.assertTrue(brief.startswith("# %s · fix · stage 1/6 understand" % task.name), brief[:80])
        self.assertEqual(r.stdout, brief)

    def test_kindless_start_creates_nothing(self):
        """T20 S9: a start without a known kind asks for one and creates nothing."""
        write_profile(self.proj)
        for args in (("fix login",), ("login", "fails"), ("fix",)):
            with self.subTest(args=args):
                r = self.start(*args)
                self.assertEqual(r.returncode, 2, r.stderr)
                if args != ("fix",):
                    self.assertIn("feature, fix, debug, perf, ux", r.stdout + r.stderr)
                self.assertEqual(self.tasks(), [])

    def test_no_session_writes_no_claim(self):
        """Review Focus 1 I3: no session id means exit 3 and nothing written; list still works."""
        write_profile(self.proj)
        r = self.start("fix", "x", session=None)
        self.assertEqual(r.returncode, 3)
        self.assertIn("no session id", r.stderr)
        self.assertEqual(self.tasks(), [])
        r = self.distiflow("task", "list", cwd=self.proj, root=self.root, session=None)
        self.assertEqual((r.returncode, r.stdout), (0, "no tasks\n"))

    def test_refuses_on_profile_errors(self):
        """S6 S28 S29: a malformed profile, a gate disabled without reason or from the personal profile stops start."""
        rows = [r for r in T16_ROWS if r[0] == "typo key"] + \
               [r[:3] + r[4:] for r in T9_ROWS if r[0] in ("gate no reason", "personal gates key")]
        for name, committed, local, code, msg in rows:
            with self.subTest(row=name):
                write_profile(self.proj, committed, local)
                r = self.start("fix", "x")
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn(msg, r.stderr)
                self.assertEqual(self.tasks(), [])
                (self.proj / ".distiflow/profile.local.toml").unlink(missing_ok=True)

    def test_no_profile_asks_init(self):
        """S7: without a profile, start asks for init and creates nothing."""
        r = self.start("fix", "x")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no distiflow profile; run /distiflow:init", r.stderr)
        self.assertFalse((self.proj / ".distiflow").exists())

    def test_heartbeat_hook_outside_distiflow_is_silent(self):
        """Review Focus 5: the heartbeat hook outside distiflow, or on a garbage claim, says and writes nothing."""
        plain = self.tmp / "plain"
        plain.mkdir()
        w(self.proj / ".distiflow/tasks/T-x/claim", "not json")
        before = sorted(p for p in self.tmp.rglob("*") if ".git" not in p.parts)
        for cwd, stdin in ((plain, {"session_id": "s-1", "cwd": str(plain)}),
                           (self.proj, {"session_id": "s-1", "cwd": str(self.proj)}),
                           (self.proj, "garbage")):
            with self.subTest(cwd=cwd.name, stdin=stdin):
                r = self.distiflow("hook", "heartbeat", cwd=cwd,
                                stdin=stdin if isinstance(stdin, str) else json.dumps(stdin))
                self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))
        self.assertEqual(sorted(p for p in self.tmp.rglob("*") if ".git" not in p.parts), before)
