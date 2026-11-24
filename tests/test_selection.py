import random
import unittest
from pathlib import Path

from golden.practices import STAGES, Issue, Practice
from golden.selection import select


def P(id, stages=("plan",), pr=50, cost="cheap", gate=False, tokens=10, kinds=None, signals=None):
    return Practice(id=id, stages=tuple(stages), kinds=kinds and tuple(kinds), signals=signals and tuple(signals),
                    run_cost=cost, gate=gate, evidence="e" if gate else "", priority=pr, body="",
                    path=Path(id + ".md"), source="upstream", tokens=tokens)


def DIS(id, reason): return {"practices": {"disable": [{"id": id, "reason": reason}]}}
def GDIS(id, reason): return {"gates": {"disable": [{"id": id, "reason": reason}]}}
def CAP(cap): return {"cost": {"run_cap": cap}}
def BUD(n): return {"cost": {"budget": {"plan": n}}}


LIMITS = {"budget": {s: 6000 for s in STAGES}}
# (name, practices, profile, stage, kept ids, {dropped id: reason substring}, gate ids)
ROWS = [
    ("zero matches", [P("a", ["plan"])], {}, "verify", [], {}, []),  # R7
    ("order priority,id", [P("b", pr=50), P("a", pr=50), P("c", pr=90)], {}, "plan", ["c", "a", "b"], {}, []),
    ("disabled", [P("a")], DIS("a", "noisy"), "plan", [], {"a": "disabled by profile: noisy"}, []),  # S20
    ("cost cap", [P("a", cost="expensive")], CAP("medium"), "plan", [], {"a": "excluded by cost cap medium"}, []),  # S25
    ("gate over cap kept", [P("g", gate=True, cost="expensive")], CAP("cheap"), "plan", ["g"], {}, ["g"]),
    ("budget exact kept", [P("a", tokens=100), P("b", tokens=100)], BUD(200), "plan", ["a", "b"], {}, []),  # R9
    ("budget overflow", [P("a", pr=90, tokens=150), P("b", tokens=100)], BUD(200), "plan", ["a"],
     {"b": "over token budget"}, []),  # S24
    ("gate tokens count first", [P("g", gate=True, tokens=150), P("a", tokens=100)], BUD(200), "plan", ["g"],
     {"a": "over token budget (150/200)"}, ["g"]),  # R8
    ("lowest-ranked dropped", [P("a", pr=90, tokens=150), P("b", pr=50, tokens=100), P("c", pr=10, tokens=40)],
     BUD(200), "plan", ["a"], {"b": "over token budget", "c": "over token budget"}, []),  # SP22
    ("gates exceed budget", [P("g", gate=True, tokens=500)], BUD(100), "plan", ["g"], {}, ["g"]),  # R8
    ("signal missing", [P("a", signals=["has-ui"])], {}, "plan", [], {}, []),
    ("signal present", [P("a", signals=["has-ui"])], {"project": {"signals": ["has-ui"]}}, "plan", ["a"], {}, []),
    ("kind filter", [P("a", kinds=["debug"])], {}, "plan", [], {}, []),
    ("gate disabled", [P("g", gate=True)], GDIS("g", "no ui"), "plan", [], {"g": "gate disabled by profile: no ui"}, []),
]


class Selection(unittest.TestCase):
    def test_selector_table(self):
        """I7 I8 I9 S20-S25 R7-R9: what loads, what is dropped and why, and gates survive cap and budget."""
        for name, practices, profile, stage, kept, dropped, gates in ROWS:
            with self.subTest(name):
                s = select(stage, "feature", profile, practices, [], LIMITS)
                self.assertEqual([p.id for p, _ in s.kept], kept)
                self.assertEqual({i for i, _ in s.dropped}, set(dropped))
                for pid, reason in s.dropped:
                    self.assertIn(dropped[pid], reason)
                self.assertEqual([p.id for p in s.gates], gates)

    def test_gate_over_cap_is_marked(self):
        """F3: a gate kept despite the cost cap says so in the brief."""
        s = select("plan", "feature", CAP("cheap"), [P("g", gate=True, cost="expensive")], [], LIMITS)
        self.assertEqual(s.kept[0][1], "over cost cap, kept: gate")

    def test_issues_reported_as_dropped(self):
        """S22 S23: a malformed or clashing local practice is named with its reason, not silently lost."""
        issues = [Issue("malformed", ".golden/practices/plan/x.md", "missing +++ frontmatter"),
                  Issue("clash", "a", "same id as upstream"), Issue("drift", "practices/plan/b.md", "changed")]
        s = select("plan", "feature", {}, [], issues, LIMITS)
        self.assertEqual(dict(s.dropped), {".golden/practices/plan/x.md": "malformed: missing +++ frontmatter",
                                           "a": "clash: same id as upstream"})

    def test_same_inputs_same_output(self):
        """I7: selection does not depend on file order."""
        ps = [P(c, pr=random.Random(i).choice([10, 50, 90]), tokens=60) for i, c in enumerate("abcdefghij")]
        ps.append(P("g", gate=True, tokens=60))
        first = select("plan", "feature", BUD(300), ps, [], LIMITS)
        for seed in range(20):
            shuffled = ps[:]
            random.Random(seed).shuffle(shuffled)
            self.assertEqual(select("plan", "feature", BUD(300), shuffled, [], LIMITS), first)
