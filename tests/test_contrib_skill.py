import json

from tests.helpers import skill, w
from tests.test_contrib_send import SendCase
from tests.test_glossary_similar import CORPUS

BODY = "Before fixing, write a test that fails. Each tenant gets its own run."


class SkillCase(SendCase):
    # Upstream already shares skills built from the practice corpus, plus a launcher.
    SKILLS = {**{k: skill(k, body=v) for k, v in CORPUS.items()},
              "task": skill("task", "Start a task.", "Run distiflow task start.")}

    def src(self, name="test-first", text=None, extra=()):
        d = self.tmp / "my-skills" / name
        w(d / "SKILL.md", text if text is not None else skill(name, body=BODY))
        for f in extra:
            w(d / f, "x\n")
        return d

    def new(self, d):
        return self.c("new", "--skill", str(d))


class SkillContrib(SkillCase):  # DF-2
    def test_new_check_confirm_send(self):
        """DF-2: a skill folder goes upstream as exactly skills/<name>/SKILL.md, sanitized, as its own PR."""
        r = self.new(self.src())
        self.assertEqual(r.returncode, 0, r.stderr)
        d = self.proj / ".distiflow/contrib/test-first"
        self.assertEqual((d / "kind").read_text().strip(), "skill")
        r = self.c("check", "test-first")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("name: test-first", r.stdout)
        self.assertIn("tenant → workspace ×1", r.stdout)
        similar = r.stdout.split("## Similar upstream skills\n", 1)[1].strip().splitlines()
        self.assertTrue(similar[0].startswith("tests-first "), similar)
        self.assertNotIn("task ", "\n".join(similar))
        r = self.c("confirm", "test-first", "--verdict", "new")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("skills/test-first/SKILL.md", r.stdout)
        r = self.c("send", "test-first")
        self.assertEqual(r.returncode, 0, r.stderr)
        names, diff = self.pushed("contrib/test-first")
        self.assertEqual(names, ["skills/test-first/SKILL.md"])
        self.assertNotIn("tenant", diff)
        log = self.git("log", "-1", "--format=%s", "contrib/test-first", cwd=self.bare)
        self.assertEqual(log.strip(), "feat(skills): add test-first")

    def test_extends_existing_skill(self):
        """DF-2: extends:<name> replaces that shared skill's SKILL.md."""
        self.new(self.src("tests-first", skill("tests-first", body=BODY)))
        self.assertEqual(self.c("check", "tests-first").returncode, 0)
        r = self.c("confirm", "tests-first", "--verdict", "new")
        self.assertEqual(r.returncode, 1)
        self.assertIn("extends:tests-first", r.stderr)
        r = self.c("confirm", "tests-first", "--verdict", "extends:tests-first")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads((self.proj / ".distiflow/contrib/tests-first/confirmed.json").read_text())["target"],
                         "skills/tests-first/SKILL.md")
        self.assertEqual(self.c("send", "tests-first").returncode, 0)
        log = self.git("log", "-1", "--format=%s", "contrib/tests-first", cwd=self.bare)
        self.assertEqual(log.strip(), "docs(skills): extend tests-first")

    def test_extra_files_refused(self):
        """DF-2: scripts in a shared skill would run on every installer's machine; v1 takes SKILL.md only."""
        r = self.new(self.src(extra=("run.sh",)))
        self.assertEqual(r.returncode, 1)
        self.assertIn("run.sh", r.stderr)
        self.assertFalse((self.proj / ".distiflow/contrib/test-first").exists())

    def test_bad_skill_fails_format(self):
        """DF-2: a launcher name, a missing description or no frontmatter fails the format check."""
        rows = [("task", skill("task", body=BODY), "reserved"),
                ("nodesc", "---\nname: nodesc\n---\nbody\n", "description"),
                ("nofront", "just text\n", "frontmatter")]
        for name, text, expected in rows:
            with self.subTest(row=name):
                d = self.proj / ".distiflow/contrib" / name
                w(d / "kind", "skill\n")
                w(d / "draft.md", text)
                r = self.c("check", name)
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn("format: FAIL", r.stdout)
                self.assertIn(expected, r.stdout)

    def test_skill_without_frontmatter_name_refused_at_new(self):
        """DF-2: the slug comes from the skill's own name; without one there is nothing to name the draft."""
        r = self.new(self.src(text="no frontmatter\n"))
        self.assertEqual(r.returncode, 1)
        self.assertIn("frontmatter", r.stderr)
