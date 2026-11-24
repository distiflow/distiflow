import re

from golden.practices import STAGES
from tests.helpers import KINDS, REPO, GoldenCase, write_profile

SECTIONS = ("## Stages", "## Stage", "## Practices loaded", "## Not loaded", "## Gates", "## Models", "## Warnings")
STAGE_PARTS = ("### Purpose", "### Do", "### Roles", "### Record", "### Exit")


class RealCore(GoldenCase):
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
                    self.assertIn("golden ship", exit_part)
                else:
                    self.assertIn("golden gate pass", exit_part)
                    self.assertIn("golden advance", exit_part)

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
                    r = self.golden("brief", "--stage", stage, "--kind", kind, cwd=proj)
                    self.assertEqual(r.returncode, 0, r.stderr)
                    self.assertTrue(r.stdout.startswith("# ad-hoc · %s · stage" % kind))
                    for s in SECTIONS:
                        self.assertIn("\n%s\n" % s, r.stdout)
        r = self.golden("check", "--ci", cwd=REPO)
        self.assertEqual(r.returncode, 0, r.stdout)
