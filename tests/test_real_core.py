import re

from distiflow.practices import STAGES
from tests.helpers import KINDS, REPO, DistiflowCase, write_profile

SECTIONS = ("## Stages", "## Stage", "## Practices loaded", "## Not loaded", "## Gates", "## Models", "## Warnings")
STAGE_PARTS = ("### Purpose", "### Do", "### Roles", "### Record", "### Exit")


class RealCore(DistiflowCase):
    def test_stage_text_shape(self):
        """S10 S27: every stage file has its five parts in order, fits 120 lines, and ends with the exit commands."""
        for stage in STAGES:
            with self.subTest(stage=stage):
                text = (REPO / ("core/stages/%s.md" % stage)).read_text()
                lines = text.splitlines()
                self.assertLessEqual(len(lines), 120)
                found = [p for p in STAGE_PARTS if p in lines]
                self.assertEqual(found, list(STAGE_PARTS))
                self.assertEqual([i for i in sorted(lines.index(p) for p in STAGE_PARTS)],
                                 [lines.index(p) for p in STAGE_PARTS])
                self.assertIsNone(re.search(r"^## ", text, re.M), "## would split the brief's sections")
                exit_part = text.split("### Exit", 1)[1]
                if stage == "ship":
                    self.assertIn("distiflow ship", exit_part)
                else:
                    self.assertIn("distiflow gate pass", exit_part)
                    self.assertIn("distiflow advance", exit_part)

    def test_ship_never_pushes_against_profile_or_merges(self):
        """I14: the ship text tells the session never to push when the profile forbids it, and never to merge."""
        text = (REPO / "core/stages/ship.md").read_text().lower()
        self.assertIn("never push when the profile forbids", text)
        self.assertIn("never merge", text)

    def test_real_core_briefs(self):
        """S8 S10: all 30 kind × stage briefs of the real core build, with every section."""
        proj = self.repo()
        write_profile(proj)
        for kind in KINDS:
            for stage in STAGES:
                with self.subTest(kind=kind, stage=stage):
                    r = self.distiflow("brief", "--stage", stage, "--kind", kind, cwd=proj)
                    self.assertEqual(r.returncode, 0, r.stderr)
                    self.assertTrue(r.stdout.startswith("# ad-hoc · %s · stage" % kind))
                    for s in SECTIONS:
                        self.assertIn("\n%s\n" % s, r.stdout)
        r = self.distiflow("check", "--ci", cwd=REPO)
        self.assertEqual(r.returncode, 0, r.stdout)


def section(out, name):
    return out.split("\n## %s\n" % name, 1)[1].split("\n## ", 1)[0]


# (kind, stage, gates that must be in ## Gates, practices that must be loaded) — T20 S8 on the real core
KIND_ROWS = [
    ("feature", "understand", ["behaviour-before-architecture"], []),
    ("fix", "understand", ["reproduce-before-fixing"], []),
    ("fix", "verify", ["regression-test-for-fix"], []),
    ("debug", "understand", ["reproduce-before-fixing"], []),
    ("perf", "understand", ["perf-baseline-first"], []),
    ("perf", "verify", ["perf-before-after"], []),
    ("ux", "understand", [], ["ux-journeys-first"]),
    ("ux", "verify", ["ux-running-app-check"], []),
]


class RealCoreKinds(DistiflowCase):
    def test_real_core_kind_gates(self):
        """T20 S8: each kind gets its own gates from the seed practices; nothing drops for token budget."""
        proj = self.repo()
        write_profile(proj)
        brief = lambda k, s: self.distiflow("brief", "--stage", s, "--kind", k, cwd=proj).stdout
        for kind, stage, gates, loaded in KIND_ROWS:
            with self.subTest(kind=kind, stage=stage):
                out = brief(kind, stage)
                for g in gates:
                    self.assertIn("- %s:" % g, section(out, "Gates"))
                for p in loaded:
                    self.assertIn("- %s ·" % p, section(out, "Practices loaded"))
        self.assertEqual(section(brief("debug", "plan"), "Gates").strip(), "- none")
        for kind in KINDS:
            for stage in STAGES:
                with self.subTest(kind=kind, stage=stage, check="budget"):
                    self.assertNotIn("over token budget", section(brief(kind, stage), "Not loaded"))
