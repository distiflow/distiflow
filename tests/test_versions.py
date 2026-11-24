import json

from tests.helpers import GoldenCase, practice, write_profile

CHANGELOG = "# Changelog\n\n## [1.4.0]\n- later\n\n## [1.3.0]\n- new gate rule\n\n## [1.2.0]\n- old\n"


class Versions(GoldenCase):
    def test_stage_keeps_its_version_and_next_shows_delta(self):
        """T25 S40: an update mid-stage leaves the running stage alone; the next stage records and explains it."""
        gate = {"understand/g.md": practice("g", ["understand"], gate=True)}
        old = self.fixture_root(version="1.2.0", practices=gate)
        new = self.fixture_root(version="1.3.0", practices=gate, changelog=CHANGELOG)
        proj = self.repo()
        write_profile(proj, '[project]\nname = "proj"\n[git]\nworktrees = false\n')
        r = self.golden("task", "start", "fix", "x", cwd=proj, root=old)
        self.assertEqual(r.returncode, 0, r.stderr)
        task = next((proj / ".golden/tasks").glob("T-*"))
        r = self.golden("task", "resume", task.name, cwd=proj, root=new)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("· golden 1.2.0\n", (task / "stage-1-brief.md").read_text())
        self.golden("gate", "pass", task.name, "g", "--evidence", "ok", cwd=proj, root=new)
        r = self.golden("advance", task.name, cwd=proj, root=new)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("golden 1.2.0 → 1.3.0", r.stdout)
        self.assertIn("- new gate rule", r.stdout)
        self.assertNotIn("- later", r.stdout)
        self.assertNotIn("- old", r.stdout)
        st = json.loads((task / "state.json").read_text())
        self.assertEqual([x["version"] for x in st["runs"]], ["1.2.0", "1.3.0"])
        show = self.golden("task", "show", task.name, cwd=proj, root=new, session=None).stdout
        self.assertIn("run understand 1 · golden 1.2.0", show)
        self.assertIn("run plan 1 · golden 1.3.0", show)

    def test_same_version_prints_no_delta(self):
        """S40: no version line when nothing changed."""
        root = self.fixture_root(version="1.2.0", changelog=CHANGELOG)
        proj = self.repo()
        write_profile(proj, '[project]\nname = "proj"\n[git]\nworktrees = false\n')
        self.golden("task", "start", "fix", "x", cwd=proj, root=root)
        task = next((proj / ".golden/tasks").glob("T-*"))
        r = self.golden("advance", task.name, cwd=proj, root=root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(" → ", r.stdout)
