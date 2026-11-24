import json
import os
import shutil

from tests.helpers import w, write_profile
from tests.test_contrib_check import NEAR, PROFILE, ContribCase

REPO_URL = "https://github.com/o/golden-workflow"
OTHER = "Split the plan into small steps that can each be checked on its own, one at a time, in order."


class SendCase(ContribCase):
    """A bare upstream holding the fixture core, reached through the plugin's repository URL."""

    def setUp(self):
        super().setUp()
        self.gh_stub()
        meta = self.root / ".claude-plugin/plugin.json"
        meta.write_text(json.dumps({**json.loads(meta.read_text()), "repository": REPO_URL}))
        self.bare = self.tmp / "upstream.git"
        seed = self.tmp / "seed"
        self.git("init", "-q", "-b", "main", str(seed), cwd=self.tmp)
        shutil.copytree(self.root / "core", seed / "core")
        self.git("add", ".", cwd=seed)
        self.git("commit", "-q", "-m", "upstream", cwd=seed)
        self.git("clone", "-q", "--bare", str(seed), str(self.bare), cwd=self.tmp)
        with open(self.home / ".gitconfig", "a") as f:
            f.write('[url "%s"]\n\tinsteadOf = %s\n' % (self.bare, REPO_URL))
        self.clone = self.home / ".golden" / "upstream"

    def ready(self, slug="test-first-fix", body=NEAR, verdict="new"):
        self.draft(body=body, slug=slug, pid=slug)
        r = self.c("check", slug)
        self.assertEqual(r.returncode, 0, r.stdout)
        r = self.c("confirm", slug, "--verdict", verdict)
        self.assertEqual(r.returncode, 0, r.stderr)
        return self.proj / ".golden/contrib" / slug

    def contrib_refs(self):
        return self.git("ls-remote", str(self.bare), "refs/heads/contrib/*", cwd=self.tmp).splitlines()

    def pushed(self, branch):
        names = self.git("diff", "--name-only", "main..%s" % branch, cwd=self.bare).split()
        return names, self.git("diff", "main..%s" % branch, cwd=self.bare)


class Send(SendCase):  # T1 I1 S52 R37-R39
    def test_sends_exactly_confirmed_bytes(self):
        """T1 I1 S52: the pushed branch changes exactly the target, with the confirmed bytes, and no profile facts."""
        d = self.ready()
        r = self.c("send", "test-first-fix")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("https://example.invalid/pull/1", r.stdout)
        names, diff = self.pushed("contrib/test-first-fix")
        self.assertEqual(names, ["core/practices/plan/test-first-fix.md"])
        blob = self.git("show", "contrib/test-first-fix:core/practices/plan/test-first-fix.md", cwd=self.bare)
        self.assertEqual(blob, (d / "sanitized.md").read_text())
        for fact in ("Zentrix", "zentrix", "quokka", "deploy.zentrix.dev", "tenant"):
            self.assertNotIn(fact, diff)
        self.assertEqual([p["head"] for p in self.gh_state()["prs"]], ["contrib/test-first-fix"])
        self.assertTrue((d / "sent.json").exists())

    def test_edit_after_confirm_refused(self):
        """I1 R37: bytes changed after confirm are never sent."""
        d = self.ready()
        (d / "sanitized.md").write_text((d / "sanitized.md").read_text() + "\nlate edit\n")
        r = self.c("send", "test-first-fix")
        self.assertEqual(r.returncode, 1)
        self.assertIn("changed after confirm", r.stderr)
        self.assertEqual(self.contrib_refs(), [])

    def test_stray_files_and_old_branch_left_behind(self):
        """T1 R38 R39: junk, local edits and an old local branch in the work clone never ride along."""
        self.git("clone", "-q", REPO_URL, str(self.clone), cwd=self.tmp)
        self.git("switch", "-q", "-c", "contrib/test-first-fix", cwd=self.clone)
        w(self.clone / "core/practices/plan/extra.md", "old commit")
        self.git("add", ".", cwd=self.clone)
        self.git("commit", "-q", "-m", "old", cwd=self.clone)
        w(self.clone / "junk.md", "stray")
        w(self.clone / "core/kinds.toml", "# edited\n")
        self.ready()
        r = self.c("send", "test-first-fix")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.pushed("contrib/test-first-fix")[0], ["core/practices/plan/test-first-fix.md"])
        self.assertEqual(self.git("status", "--porcelain", "--ignored", cwd=self.clone), "")


class Rescan(SendCase):  # T3 I2 S45
    def test_term_added_after_confirm_blocks_send(self):
        """T3 I2 S45: a deny term added after confirm is found in the final bytes and blocks the send."""
        self.ready(body=NEAR + " The zebra case too.")
        write_profile(self.proj, PROFILE.replace('deny_terms = ["quokka"]', 'deny_terms = ["quokka", "zebra"]'))
        r = self.c("send", "test-first-fix")
        self.assertEqual(r.returncode, 1)
        self.assertIn("zebra", r.stderr)
        self.assertEqual((self.contrib_refs(), self.gh_state()["prs"]), ([], []))


class Idempotent(SendCase):  # T21 I12 S46 S48 R23
    def test_same_slug_twice_one_pr(self):
        """T21 I12: sending the same contribution again updates the one request."""
        self.ready()
        self.assertEqual(self.c("send", "test-first-fix").returncode, 0)
        r = self.c("send", "test-first-fix")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("updated https://example.invalid/pull/1", r.stdout)
        self.assertEqual(len(self.gh_state()["prs"]), 1)

    def test_near_identical_other_slug_offers_update(self):
        """T21 S46 R23: a near-identical idea under another slug is pointed at the open request."""
        self.ready()
        self.assertEqual(self.c("send", "test-first-fix").returncode, 0)
        self.ready(slug="fail-first", body=NEAR.replace("Before fixing", "First of all"))
        r = self.c("send", "fail-first")
        self.assertEqual(r.returncode, 2)
        self.assertIn("similar open contribution contrib/test-first-fix", r.stderr)
        self.assertIn("--update contrib/test-first-fix", r.stderr)
        r = self.c("send", "fail-first", "--update", "contrib/test-first-fix")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.gh_state()["prs"]), 1)
        self.assertEqual(len(self.contrib_refs()), 1)
        self.ready(slug="small-steps-two", body=OTHER)
        self.assertEqual(self.c("send", "small-steps-two").returncode, 0)

    def test_update_takes_only_contrib_branches(self):
        """R16: --update names an open contrib/<slug> branch, never an option or another branch."""
        self.ready()
        for bad in ("--update=--upload-pack=touch pwned", "--update=main", "--update=contrib/../main"):
            with self.subTest(arg=bad):
                r = self.c("send", "test-first-fix", bad)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn("not a contribution branch", r.stderr)
        self.assertEqual(self.contrib_refs(), [])

    def test_half_sent_completes(self):
        """T21 S48: a send that pushed but failed to open the request finishes on rerun, with one branch and one request."""
        self.env["GH_STUB_FAIL"] = "pr-create-once"
        self.ready()
        r = self.c("send", "test-first-fix")
        self.assertEqual(r.returncode, 1)
        self.assertIn("rerun golden contrib send test-first-fix", r.stderr)
        self.assertEqual(self.c("send", "test-first-fix").returncode, 0)
        self.assertEqual((len(self.gh_state()["prs"]), len(self.contrib_refs())), (1, 1))


class Failures(SendCase):  # T22 S47 S50 S51
    ROWS = [("gh missing", {"PATH_NO_GH": True}, 3, "gh auth login"),
            ("signed out", {"GH_STUB_AUTH": "missing"}, 3, "gh auth login"),
            ("no write", {"GH_STUB_PUSH": "false"}, 2, "--issue"),
            ("unconfirmed", {"SKIP_CONFIRM": True}, 2, "not confirmed")]

    def no_gh_path(self):
        d = self.tmp / "nogh"
        d.mkdir(exist_ok=True)
        if not (d / "git").exists():
            (d / "git").symlink_to(shutil.which("git"))
        return str(d) + os.pathsep + "/usr/bin:/bin"

    def test_failure_table(self):
        """T22 S47 S50 S51: each failure sends nothing and keeps the draft; a fixed environment then sends."""
        for name, mode, code, text in self.ROWS:
            with self.subTest(row=name):
                self.setUp()
                env = {k: v for k, v in mode.items() if k.startswith("GH_")}
                if mode.get("PATH_NO_GH"):
                    env["PATH"] = self.no_gh_path()
                if mode.get("SKIP_CONFIRM"):
                    self.draft()
                    self.c("check", "test-first-fix")
                else:
                    self.ready()
                r = self.c("send", "test-first-fix", env=env)
                self.assertEqual(r.returncode, code, r.stdout + r.stderr)
                self.assertIn(text, r.stderr)
                self.assertEqual((self.contrib_refs(), self.gh_state()["prs"]), ([], []))
                self.assertTrue((self.proj / ".golden/contrib/test-first-fix/sanitized.md").exists())
                if name == "gh missing":
                    self.assertEqual(self.c("send", "test-first-fix").returncode, 0)
                self.doCleanups()

    def test_issue_fallback(self):
        """S51: without write access, --issue opens an issue whose body is the confirmed bytes."""
        self.env["GH_STUB_PUSH"] = "false"
        d = self.ready()
        r = self.c("send", "test-first-fix", "--issue")
        self.assertEqual(r.returncode, 0, r.stderr)
        [issue] = self.gh_state()["issues"]
        self.assertEqual((issue["body"], issue["repo"]), ((d / "sanitized.md").read_text(), "o/golden-workflow"))
        self.assertEqual(self.contrib_refs(), [])


class Extends(SendCase):  # T23 S42 S43
    def test_extends_edits_existing_file_only(self):
        """S42 S43: an extending contribution changes the existing upstream file and nothing else."""
        self.ready(verdict="extends:tests-first")
        r = self.c("send", "test-first-fix")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("https://example.invalid/pull/", r.stdout)
        self.assertEqual(self.pushed("contrib/test-first-fix")[0], ["core/practices/plan/tests-first.md"])
        self.assertEqual(self.gh_state()["prs"][0]["title"], "docs(practices): extend tests-first")
