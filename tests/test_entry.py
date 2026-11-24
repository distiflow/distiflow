import ast
import subprocess
import sys

from tests.helpers import BIN, DistiflowCase


class Entry(DistiflowCase):
    def test_whoami_reads_env(self):
        """T31: the CLI sees the session id the SessionStart hook exported."""
        r = self.distiflow("whoami", cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("session=s-1 source=env", r.stdout)

    def test_session_flag_any_position(self):
        """T31 fallback B: the PreToolUse rewrite appends --session at the end."""
        r = self.distiflow("whoami", "--session", "abc-1", cwd=self.tmp, session=None)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("session=abc-1 source=flag", r.stdout)

    def test_missing_or_invalid_session_exits_3(self):
        """Review Focus 1 / I3: no usable session id is an environment error, never a shared id."""
        for sid in (None, "", "../x", "a b"):
            with self.subTest(sid=sid):
                r = self.distiflow("whoami", cwd=self.tmp, session=sid)
                self.assertEqual(r.returncode, 3)
                self.assertIn("no session id", r.stderr)

    def test_session_start_hook_writes_env_file(self):
        """T31 mechanism A: the hook exports the id through CLAUDE_ENV_FILE."""
        f = self.tmp / "envfile"
        r = self.hook("session-start", {"session_id": "s-9", "cwd": str(self.tmp)},
                      env={"CLAUDE_ENV_FILE": str(f)})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(f.read_text(), "export DISTIFLOW_SESSION_ID=s-9\n")

    def test_session_start_hook_rejects_unsafe_id(self):
        """T31: CLAUDE_ENV_FILE is sourced by a shell, so an unsafe id is never written."""
        f = self.tmp / "envfile"
        r = self.hook("session-start", {"session_id": "x$(touch pwned)"},
                      env={"CLAUDE_ENV_FILE": str(f)})
        self.assertEqual((r.returncode, f.exists()), (0, False))

    def test_session_start_hook_without_env_file_is_silent(self):
        """Review Focus 5: a hook never blocks or chatters when it has nothing to do."""
        for stdin in ('{"session_id": "s-9"}', "not json"):
            with self.subTest(stdin=stdin):
                r = self.distiflow("hook", "session-start", cwd=self.tmp, stdin=stdin)
                self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "", ""))

    def test_python_below_311_prints_install_steps(self):
        """R32: an old interpreter gets install steps and exit 3."""
        code = ("import sys; sys.version_info=(3,10,0); sys.argv=['distiflow','whoami']; "
                "exec(open(%r).read())" % str(BIN))
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(r.returncode, 3)
        self.assertIn("Python 3.11", r.stderr)

    def test_entry_parses_on_old_python(self):
        """R32: a 3.10 user sees the message, not a SyntaxError from the entry file."""
        ast.parse(BIN.read_text(), feature_version=(3, 6))
