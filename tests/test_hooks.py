import json

from tests.helpers import GoldenCase, w

# (name, setup, target, tool, expected) — T7 I4 S35 R33; each row builds files directly, then runs the hook.
GUARD_ROWS = [
    ("lost, edit in worktree",         "lost", "worktree/file.py", "Write", "deny"),
    ("lost, notebook in worktree",     "lost", "worktree/n.ipynb", "NotebookEdit", "deny"),
    ("lost, bash cwd in worktree sub", "lost", "worktree/sub", "Bash", "deny"),
    ("lost, main checkout held",       "lost+checkout", "repo/a.py", "Edit", "deny"),
    ("lost, bash in held checkout",    "lost+checkout", "repo", "Bash", "deny"),
    ("lost, another task corrupt",     "lost+corrupt-other", "worktree/file.py", "Write", "deny"),
    ("lost, main checkout not held",   "lost", "repo/a.py", "Edit", "allow"),
    ("lost, unrelated file",           "lost", "elsewhere/x.py", "Write", "allow"),
    ("holder edits worktree",          "holder", "worktree/file.py", "Write", "allow"),
    ("never held",                     "none", "worktree/file.py", "Write", "allow"),
    ("corrupt claim",                  "corrupt", "worktree/file.py", "Write", "allow"),
    ("corrupt state",                  "corrupt-state", "worktree/file.py", "Write", "allow"),
    ("no golden project",              "nogolden", "elsewhere/x.py", "Write", "allow"),   # Review Focus 5
    ("not a git dir",                  "nogit", "plain", "Bash", "allow"),
]
LOST_MSG = "you no longer hold task T-1; resume it with /golden:task resume T-1"


def state(stage="implement", runs=1, worktree=None):
    return {"schema": 1, "id": "T-1", "kind": "feature", "stage": stage, "worktree": worktree,
            "runs": [{"stage": stage, "n": n + 1, "version": "0.1.0", "session": "s-1", "started": "t",
                      "ended": None, "gates": [], "evidence": {}} for n in range(runs)]}


class Hooks(GoldenCase):
    def setUp(self):
        super().setUp()
        self.proj = self.repo()  # under the "gw tmp ü" parent: Review Focus 4
        self.wt = self.tmp / "proj.golden" / "T-1"
        (self.wt / "sub").mkdir(parents=True)
        w(self.wt / ".golden" / "profile.toml", "")  # the committed profile is checked out in every worktree
        self.task = self.proj / ".golden" / "tasks" / "T-1"

    def claim(self, session):
        w(self.task / "claim", json.dumps({"session": session, "nonce": "n2", "since": "t"}))

    def build(self, setup):
        if setup in ("nogolden", "nogit"):
            (self.tmp / "plain").mkdir()
            return
        w(self.task / "state.json", "{" if setup == "corrupt-state" else json.dumps(state(worktree=str(self.wt))))
        if setup == "holder":
            self.claim("s-1")
        elif setup == "corrupt":
            w(self.task / "claim", "garbage")
        else:
            self.claim("s-2")
        if setup == "lost+corrupt-other":
            w(self.task.with_name("T-0") / "state.json", "{")
        if setup in ("lost", "lost+checkout", "lost+corrupt-other", "corrupt", "corrupt-state"):
            w(self.task / "claim.lost.s-1.n1", "{}")
        if setup == "lost+checkout":
            w(self.proj / ".golden" / "tasks" / "checkout.claim", json.dumps({"task": "T-1", "session": "s-2"}))

    def path(self, target):
        head, _, rest = target.partition("/")
        base = {"worktree": self.wt, "repo": self.proj}.get(head, self.tmp / head)
        return base / rest if rest else base

    def guard(self, tool, target, session="s-1"):
        p = self.path(target)
        if tool == "Bash":
            payload = {"cwd": str(p), "tool_input": {"command": "echo hi > x"}}
        else:
            key = "notebook_path" if tool == "NotebookEdit" else "file_path"
            payload = {"cwd": str(self.proj), "tool_input": {key: str(p)}}
        payload.update(session_id=session, tool_name=tool, hook_event_name="PreToolUse")
        return self.hook("guard", payload, session=session)

    def assert_decision(self, r, expected, msg=None):
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        if expected == "allow":
            self.assertEqual(r.stdout, "")
            return
        out = json.loads(r.stdout)["hookSpecificOutput"]
        self.assertEqual((out["hookEventName"], out["permissionDecision"]), ("PreToolUse", "deny"))
        self.assertIn(msg, out["permissionDecisionReason"])

    def test_guard_table(self):
        """T7 I4 S35 R33: a lost session cannot write its old task's worktree or held checkout; all else passes."""
        for name, setup, target, tool, expected in GUARD_ROWS:
            with self.subTest(row=name):
                self.setUp()
                self.build(setup)
                self.assert_decision(self.guard(tool, target), expected, LOST_MSG)
                self.doCleanups()

    def test_guard_sees_through_symlinked_paths(self):
        """T7 I4: a target reached through a symlink (macOS /var → /private/var) is still the worktree."""
        self.build("lost")
        alias = self.tmp.parent / ("alias-" + self.tmp.name)
        alias.symlink_to(self.tmp)
        self.addCleanup(alias.unlink)
        p = alias / "proj.golden" / "T-1" / "file.py"
        r = self.hook("guard", {"session_id": "s-1", "cwd": str(alias / "proj"), "tool_name": "Write",
                                "tool_input": {"file_path": str(p)}})
        self.assert_decision(r, "deny", LOST_MSG)

    def test_heartbeat_from_worktree(self):
        """T6 I12 C1: a session working in its task worktree keeps its claim fresh."""
        w(self.task / "state.json", json.dumps(state(worktree=str(self.wt))))
        self.claim("s-1")
        t = __import__("time").time() - 1000
        __import__("os").utime(self.task / "claim", (t, t))
        r = self.hook("heartbeat", {"session_id": "s-1", "cwd": str(self.wt / "sub")})
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        self.assertLess(__import__("time").time() - (self.task / "claim").stat().st_mtime, 100)

    def test_guard_survives_garbage_stdin(self):
        """R33 Review Focus 5: a hook never blocks on input it cannot read."""
        r = self.golden("hook", "guard", cwd=self.proj, stdin="not json")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def spawn(self, session="s-1", prompt="look around"):
        return self.hook("agent-cap", {"session_id": session, "cwd": str(self.proj), "tool_name": "Agent",
                                       "tool_input": {"prompt": prompt}}, session=session)

    def test_agent_cap(self):
        """T24 S30: the fourth sub-agent in one stage run is denied; approval or a new run lets more through."""
        w(self.task / "state.json", json.dumps(state()))
        self.claim("s-1")
        for _ in range(3):
            self.assert_decision(self.spawn(), "allow")
        self.assert_decision(self.spawn(), "deny", "sub-agent cap reached for stage implement (3)")
        self.assert_decision(self.spawn(prompt="go\nbudget-approved: yes, two more"), "allow")
        self.assert_decision(self.spawn(session="s-9"), "allow")
        w(self.task / "state.json", json.dumps(state(runs=2)))
        for _ in range(3):
            self.assert_decision(self.spawn(), "allow")
        self.assert_decision(self.spawn(), "deny", "budget-approved:")

    def test_agent_cap_outside_golden_allows(self):
        """Review Focus 5: no project, or a corrupt task, never blocks a spawn."""
        w(self.task / "state.json", "{")
        self.claim("s-1")
        for cwd in (self.tmp, self.proj):
            with self.subTest(cwd=cwd.name):
                r = self.hook("agent-cap", {"session_id": "s-1", "cwd": str(cwd), "tool_input": {"prompt": "x"}})
                self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_hooks_json_routes_guard_and_cap(self):
        """T7 T24: the plugin registers both PreToolUse hooks on the tools they guard."""
        hooks = json.loads((__import__("tests.helpers").helpers.REPO / "hooks/hooks.json").read_text())["hooks"]
        routes = {h["matcher"]: h["hooks"][0]["command"].rsplit(" ", 1)[1] for h in hooks["PreToolUse"]}
        self.assertEqual(routes, {"Write|Edit|MultiEdit|NotebookEdit|Bash": "guard", "Agent|Task": "agent-cap"})
