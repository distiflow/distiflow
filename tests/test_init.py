import json
import tomllib

from distiflow import toml_write
from tests.helpers import DistiflowCase, w, write_profile


class Init(DistiflowCase):
    def setUp(self):
        super().setUp()
        self.root = self.fixture_root()
        self.proj = self.repo()
        w(self.proj / "tests/test_a.py", "")
        w(self.proj / "Dockerfile", "FROM scratch\n")  # root level: "**/" also matches zero directories
        w(self.proj / "package.json", json.dumps({"scripts": {"test": "jest", "lint": "eslint .", "dev": "vite"}}))
        self.git("add", ".", cwd=self.proj)
        self.git("commit", "-q", "-m", "app", cwd=self.proj)

    def g(self, *args, stdin=None):
        return self.distiflow("init", *args, cwd=self.proj, root=self.root, stdin=stdin)

    def files(self):
        return sorted(p.relative_to(self.proj).as_posix() for p in self.proj.rglob("*") if ".git" not in p.parts)

    def test_propose_writes_nothing(self):
        """S1 S7: a proposal is printed for confirmation and nothing is written; start still asks for init."""
        before = self.files()
        r = self.g("--propose")
        self.assertEqual(r.returncode, 0, r.stderr)
        prof = tomllib.loads(r.stdout)
        self.assertEqual(prof["project"]["name"], "proj")
        self.assertIn("has-tests", prof["project"]["signals"])
        self.assertIn("node", prof["project"]["signals"])
        self.assertIn("has-docker", prof["project"]["signals"])
        self.assertNotIn("has-ui", prof["project"]["signals"])
        self.assertEqual(prof["commands"], {"test": "npm run test", "lint": "npm run lint"})
        self.assertEqual(prof["git"], {"worktrees": True, "push": "allowed", "base": "main"})
        self.assertEqual((prof["project"]["deny_terms"], prof["glossary"]), ([], {}))
        self.assertEqual(self.files(), before)
        r = self.distiflow("task", "start", "fix", "x", cwd=self.proj, root=self.root)
        self.assertIn("run /distiflow:init", r.stderr)

    def test_pnpm_make_and_pyproject_commands(self):
        """S1: commands follow the project's own tools."""
        w(self.proj / "pnpm-lock.yaml", "")
        w(self.proj / "Makefile", "build:\n\tgo build\ntypecheck:\n\ttrue\n")
        prof = tomllib.loads(self.g("--propose").stdout)
        self.assertEqual(prof["commands"], {"test": "pnpm run test", "lint": "pnpm run lint",
                                            "build": "make build", "typecheck": "make typecheck"})
        other = self.repo("py")
        w(other / "pyproject.toml", "[project]\nname='x'\n")
        prof = tomllib.loads(self.distiflow("init", "--propose", cwd=other, root=self.root).stdout)
        self.assertEqual(prof["commands"], {"test": "python3 -m unittest"})

    def test_write_validates_and_creates(self):
        """S1: an invalid profile is refused with nothing written; a valid one is written with its ignore file."""
        r = self.g("--write", "-", stdin='[git]\nworktree = false\n')
        self.assertEqual(r.returncode, 1)
        self.assertIn("did you mean worktrees?", r.stderr)
        self.assertFalse((self.proj / ".distiflow").exists())
        proposal = self.g("--propose").stdout
        r = self.g("--write", "-", stdin=proposal)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.proj / ".distiflow/profile.toml").read_text(), proposal)
        self.assertEqual((self.proj / ".distiflow/.gitignore").read_text(), "tasks/\ncontrib/\nprofile.local.toml\n")
        self.assertIn("add .distiflow/ to .git/info/exclude", r.stdout)
        self.assertEqual(self.distiflow("profile", "check", cwd=self.proj, root=self.root).returncode, 0)

    def test_reinit_keeps_overrides(self):
        """S4: re-init shows the saved profile and the differences, and never drops a key silently."""
        saved = ('[project]\nname = "proj"\nsignals = ["has-tests"]\n\n[commands]\ntest = "jest --ci"\n\n'
                 '[[practices.disable]]\nid = "x"\nreason = "not here"\n')
        write_profile(self.proj, saved)
        r = self.g("--propose")
        self.assertTrue(r.stdout.startswith(saved), r.stdout[:200])
        diff = r.stdout.split("## Differences\n", 1)[1]
        self.assertIn("signal +node", diff)
        self.assertIn('command test: saved "jest --ci" detected "npm run test"', diff)
        self.assertIn("command lint: saved none detected \"npm run lint\"", diff)
        trimmed = '[project]\nname = "proj"\nsignals = ["has-tests", "node"]\n'
        r = self.g("--write", "-", stdin=trimmed)
        self.assertEqual(r.returncode, 1)
        self.assertIn("practices.disable", r.stderr)
        self.assertIn("commands.test", r.stderr)
        self.assertEqual((self.proj / ".distiflow/profile.toml").read_text(), saved)
        r = self.g("--write", "-", "--allow-removal", stdin=trimmed)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.proj / ".distiflow/profile.toml").read_text(), trimmed)

    def test_reinit_never_drops_deny_terms_silently(self):
        """S4 I2: shrinking a saved list such as deny_terms counts as a removal."""
        saved = '[project]\nname = "proj"\ndeny_terms = ["acme", "zentrix"]\n'
        write_profile(self.proj, saved)
        r = self.g("--write", "-", stdin='[project]\nname = "proj"\ndeny_terms = []\n')
        self.assertEqual(r.returncode, 1)
        self.assertIn("project.deny_terms", r.stderr)
        self.assertEqual((self.proj / ".distiflow/profile.toml").read_text(), saved)

    def test_detect_base_master(self):
        """S1: the base branch is the repo's own, not an assumed main."""
        r = self.repo("old")
        self.git("branch", "-m", "master", cwd=r)
        prof = tomllib.loads(self.distiflow("init", "--propose", cwd=r, root=self.root).stdout)
        self.assertEqual(prof["git"]["base"], "master")
        bare = self.tmp / "remote.git"
        self.git("clone", "-q", "--bare", str(r), str(bare), cwd=self.tmp)
        clone = self.tmp / "clone"
        self.git("clone", "-q", str(bare), str(clone), cwd=self.tmp)
        self.git("switch", "-q", "-c", "topic", cwd=clone)
        prof = tomllib.loads(self.distiflow("init", "--propose", cwd=clone, root=self.root).stdout)
        self.assertEqual(prof["git"]["base"], "master")

    def test_signal_drift_warned(self):
        """T19 S5: a signal that appeared since init is reported at start."""
        write_profile(self.proj, '[project]\nname = "proj"\nsignals = ["has-docker", "has-tests", "node", "python"]\n')
        r = self.distiflow("task", "start", "fix", "x", cwd=self.proj, root=self.root)
        self.assertNotIn("signals differ", r.stdout)
        w(self.proj / "db/migrations/001.sql", "")
        r = self.distiflow("task", "start", "fix", "y", cwd=self.proj, root=self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("signals differ from profile: +has-migrations; update with /distiflow:init", r.stdout)

    def test_toml_write_roundtrip(self):
        """S1: the writer emits exactly what TOML reads back, for every profile shape."""
        d = {"project": {"name": 'a "q" \\ b', "signals": ["x", "y"], "deny_terms": []},
             "commands": {"test": "npm run test", "odd key": "x"}, "glossary": {},
             "git": {"worktrees": False, "push": "allowed", "base": "main"},
             "cost": {"run_cap": "medium", "budget": {"plan": 4000}},
             "models": {"reviewer": {"model": "sonnet", "effort": "high"}},
             "practices": {"disable": [{"id": "a", "reason": "r"}, {"id": "b", "reason": "ü\nnew line"}]}}
        self.assertEqual(tomllib.loads(toml_write.dumps(d)), d)
