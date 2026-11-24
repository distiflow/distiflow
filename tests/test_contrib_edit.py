from tests.helpers import skill, w
from tests.test_contrib_send import SendCase

STAGE = "core/stages/review.md"
LINE = "6. For a change to the UI, look at it in the running app; Claude in Chrome first."


class EditCase(SendCase):
    SKILLS = {"tests-first": skill("tests-first")}

    def start(self, path=STAGE):
        r = self.c("new", "--edit", path)
        self.assertEqual(r.returncode, 0, r.stderr)
        name = path.split("/")[-2] if path.startswith("skills/") else path.split("/")[-1].removesuffix(".md")
        return self.proj / ".distiflow/contrib" / ("edit-" + name)

    def add_line(self, d, after="### Roles"):
        text = (d / "draft.md").read_text()
        (d / "draft.md").write_text(text.replace("\n" + after, "\n" + LINE + "\n\n" + after, 1))


class Edit(EditCase):  # DF-3
    def test_stage_edit_sent_as_one_file(self):
        """DF-3: an edit to a stage goes upstream as that one file, with the change shown before confirm."""
        d = self.start()
        self.assertEqual((d / "draft.md").read_text(), (self.root / STAGE).read_text())
        self.add_line(d)
        r = self.c("check", "edit-review")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        change = r.stdout.split("## Change against upstream\n", 1)[1]
        self.assertIn("+" + LINE, change)
        self.assertEqual(self.c("confirm", "edit-review", "--verdict", "edit").returncode, 0)
        r = self.c("send", "edit-review")
        self.assertEqual(r.returncode, 0, r.stderr)
        names, _ = self.pushed("contrib/edit-review")
        self.assertEqual(names, [STAGE])
        self.assertEqual(self.git("show", "contrib/edit-review:" + STAGE, cwd=self.bare), (d / "sanitized.md").read_text())
        log = self.git("log", "-1", "--format=%s", "contrib/edit-review", cwd=self.bare)
        self.assertEqual(log.strip(), "docs(stages): edit review")

    def test_starts_from_override_body(self):
        """DF-3: a project that already bent the stage proposes its override, without the override header."""
        self.assertEqual(self.distiflow("override", "stages/review.md", cwd=self.proj, root=self.root).returncode, 0)
        o = self.proj / ".distiflow/overrides/stages/review.md"
        o.write_text(o.read_text().replace("### Roles", LINE + "\n\n### Roles", 1))
        d = self.start()
        draft = (d / "draft.md").read_text()
        self.assertIn(LINE, draft)
        self.assertNotIn("distiflow-override", draft)

    def test_upstream_moved_refused(self):
        """DF-3: a whole-file send built on an old base would revert someone else's change; refuse it."""
        d = self.start()
        self.add_line(d)
        self.assertEqual(self.c("check", "edit-review").returncode, 0)
        self.assertEqual(self.c("confirm", "edit-review", "--verdict", "edit").returncode, 0)
        other = self.tmp / "other"
        self.git("clone", "-q", str(self.bare), str(other), cwd=self.tmp)
        w(other / STAGE, (other / STAGE).read_text() + "\nSomeone else's line.\n")
        self.git("commit", "-q", "-am", "other", cwd=other)
        self.git("push", "-q", "origin", "main", cwd=other)
        r = self.c("send", "edit-review")
        self.assertEqual(r.returncode, 1)
        self.assertIn("changed upstream", r.stderr)
        self.assertEqual(self.contrib_refs(), [])

    def test_bad_drafts_fail_check(self):
        """DF-3: an unchanged draft or a stage without its parts fails the format check."""
        d = self.start()
        r = self.c("check", "edit-review")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no change against upstream", r.stdout)
        (d / "draft.md").write_text((d / "draft.md").read_text().split("### Exit", 1)[0])
        r = self.c("check", "edit-review")
        self.assertEqual(r.returncode, 1)
        self.assertIn("### Exit", r.stdout)

    def test_skill_edit(self):
        """DF-3: a shared skill edit keeps its name and goes to skills/<name>/SKILL.md."""
        d = self.start("skills/tests-first/SKILL.md")
        (d / "draft.md").write_text((d / "draft.md").read_text() + "\nThen run it.\n")
        self.assertEqual(self.c("check", "edit-tests-first").returncode, 0)
        self.assertEqual(self.c("confirm", "edit-tests-first", "--verdict", "edit").returncode, 0)
        self.assertEqual(self.c("send", "edit-tests-first").returncode, 0)
        self.assertEqual(self.pushed("contrib/edit-tests-first")[0], ["skills/tests-first/SKILL.md"])

    def test_bad_paths_refused(self):
        """DF-3: only stages, practices and shared skills can be edited; nothing outside the plugin."""
        for path in ("core/kinds.toml", "core/stages/../kinds.toml", "skills/task/SKILL.md", "/etc/passwd",
                     "core/stages/nope.md"):
            with self.subTest(path=path):
                r = self.c("new", "--edit", path)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn(path, r.stderr)
                self.assertEqual(list(self.proj.glob(".distiflow/contrib/edit-*")), [])

    def test_extends_upstream_moved_refused(self):
        """DF-3: the base guard also covers extends:, which sends a whole practice file too."""
        self.ready(verdict="extends:tests-first")
        other = self.tmp / "other"
        self.git("clone", "-q", str(self.bare), str(other), cwd=self.tmp)
        f = other / "core/practices/plan/tests-first.md"
        w(f, f.read_text() + "\nSomeone else's line.\n")
        self.git("commit", "-q", "-am", "other", cwd=other)
        self.git("push", "-q", "origin", "main", cwd=other)
        r = self.c("send", "test-first-fix")
        self.assertEqual(r.returncode, 1)
        self.assertIn("changed upstream", r.stderr)
