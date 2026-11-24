import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BIN = REPO / "bin" / "golden"
# Every integration test runs under a path with a space and non-ASCII characters.
TMP_PARENT = Path(tempfile.gettempdir()).resolve() / "gw tmp ü"


class GoldenCase(unittest.TestCase):
    def setUp(self):
        TMP_PARENT.mkdir(exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(dir=TMP_PARENT)).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        (self.tmp / "bin").mkdir()
        self.home.mkdir()
        gitconfig = self.home / ".gitconfig"
        gitconfig.write_text(
            "[user]\n\tname = Golden Test\n\temail = test@example.invalid\n"
            "[init]\n\tdefaultBranch = main\n"
        )
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("GOLDEN_", "CLAUDE_", "GIT_"))}
        env.update(
            HOME=str(self.home),
            GIT_CONFIG_GLOBAL=str(gitconfig),
            GIT_CONFIG_NOSYSTEM="1",
            PATH=str(self.tmp / "bin") + os.pathsep + os.environ.get("PATH", ""),
            GOLDEN_SESSION_ID="s-1",
        )
        self.env = env

    def golden(self, *args, cwd, session="s-1", stdin=None, root=None, env=None):
        e = dict(self.env)
        e.pop("GOLDEN_SESSION_ID")
        if session is not None:
            e["GOLDEN_SESSION_ID"] = session
        if root is not None:
            e["GOLDEN_ROOT"] = str(root)
        e.update(env or {})
        return subprocess.run([sys.executable, str(BIN), *map(str, args)], cwd=cwd, env=e,
                              input=stdin, capture_output=True, text=True)

    def hook(self, name, payload, **kw):
        kw.setdefault("cwd", self.tmp)
        return self.golden("hook", name, stdin=json.dumps(payload), **kw)

    def git(self, *args, cwd):
        return subprocess.run(["git", *args], cwd=cwd, env=self.env, check=True,
                              capture_output=True, text=True).stdout

    def repo(self, name="proj"):
        r = self.tmp / name
        r.mkdir()
        self.git("init", "-q", "-b", "main", cwd=r)
        (r / "README.md").write_text("x\n")
        self.git("add", ".", cwd=r)
        self.git("commit", "-q", "-m", "init", cwd=r)
        return r
