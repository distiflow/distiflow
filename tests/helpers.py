import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BIN = REPO / "bin" / "distiflow"
# Every integration test runs under a path with a space and non-ASCII characters.
TMP_PARENT = Path(tempfile.gettempdir()).resolve() / "gw tmp ü"
KINDS = ("feature", "fix", "debug", "perf", "ux")


def w(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def header(sha, version="0.1.0"):
    return "<!-- distiflow-override upstream=%s version=%s -->\n" % (sha, version)


def sha_of(root, rel):
    return hashlib.sha256((Path(root) / "core" / rel).read_bytes()).hexdigest()


def _toml_list(xs):
    return "[" + ", ".join('"%s"' % x for x in xs) + "]"


def practice(id, stages, kinds=None, signals=None, run_cost="cheap", gate=False, evidence="",
             priority=50, body="text"):
    if gate and not evidence:
        evidence = "e"
    lines = ["+++", 'id = "%s"' % id, "stages = " + _toml_list(stages)]
    if kinds is not None:
        lines.append("kinds = " + _toml_list(kinds))
    if signals is not None:
        lines.append("signals = " + _toml_list(signals))
    lines += ['run_cost = "%s"' % run_cost, "gate = " + ("true" if gate else "false"),
              'evidence = "%s"' % evidence, "priority = %d" % priority, "+++", body, ""]
    return "\n".join(lines)


def write_profile(repo, committed='[project]\nname = "proj"\n[git]\npush = "forbidden"\n', local=None):
    w(Path(repo) / ".distiflow" / "profile.toml", committed)
    if local is not None:
        w(Path(repo) / ".distiflow" / "profile.local.toml", local)


class DistiflowCase(unittest.TestCase):
    def setUp(self):
        TMP_PARENT.mkdir(exist_ok=True)
        self.tmp = Path(tempfile.mkdtemp(dir=TMP_PARENT)).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        (self.tmp / "bin").mkdir()
        self.home.mkdir()
        gitconfig = self.home / ".gitconfig"
        gitconfig.write_text(
            "[user]\n\tname = Distiflow Test\n\temail = test@example.invalid\n"
            "[init]\n\tdefaultBranch = main\n"
        )
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("DISTIFLOW_", "CLAUDE_", "GIT_"))}
        env.update(
            HOME=str(self.home),
            GIT_CONFIG_GLOBAL=str(gitconfig),
            GIT_CONFIG_NOSYSTEM="1",
            PATH=str(self.tmp / "bin") + os.pathsep + os.environ.get("PATH", ""),
            DISTIFLOW_SESSION_ID="s-1",
        )
        self.env = env

    def distiflow(self, *args, cwd, session="s-1", stdin=None, root=None, env=None):
        e = dict(self.env)
        e.pop("DISTIFLOW_SESSION_ID")
        if session is not None:
            e["DISTIFLOW_SESSION_ID"] = session
        if root is not None:
            e["DISTIFLOW_ROOT"] = str(root)
        e.update(env or {})
        return subprocess.run([sys.executable, str(BIN), *map(str, args)], cwd=cwd, env=e,
                              input=stdin, capture_output=True, text=True)

    def hook(self, name, payload, **kw):
        kw.setdefault("cwd", self.tmp)
        return self.distiflow("hook", name, stdin=json.dumps(payload), **kw)

    def git(self, *args, cwd):
        return subprocess.run(["git", *args], cwd=cwd, env=self.env, check=True,
                              capture_output=True, text=True).stdout

    def fixture_root(self, version="0.1.0", practices={}, stages={}, changelog=None):
        root = Path(tempfile.mkdtemp(dir=self.tmp, prefix="root"))
        (root / "core").mkdir()
        for f in (REPO / "core").glob("*.toml"):
            shutil.copy(f, root / "core" / f.name)
        if (REPO / "core" / "stages").is_dir():
            shutil.copytree(REPO / "core" / "stages", root / "core" / "stages")
        shutil.copytree(REPO / ".claude-plugin", root / ".claude-plugin")
        meta = root / ".claude-plugin" / "plugin.json"
        meta.write_text(json.dumps({**json.loads(meta.read_text()), "version": version}))
        for rel, text in practices.items():
            w(root / "core" / "practices" / rel, text)
        for name, text in stages.items():
            w(root / "core" / "stages" / name, text)
        if changelog is not None:
            w(root / "CHANGELOG.md", changelog)
        return root

    def gh_stub(self, auth="ok", push="true", merged="", fail=""):
        """Put a recording GitHub CLI stand-in first on PATH; a real gh is never reached."""
        stub = self.tmp / "bin" / "gh"
        stub.write_text("#!%s\nexec(open(%r).read())\n" % (sys.executable, str(REPO / "tests/fixtures/gh_stub.py")))
        stub.chmod(0o755)
        self.gh_dir = self.tmp / "gh"
        self.env.update(GH_STUB_DIR=str(self.gh_dir), GH_STUB_AUTH=auth, GH_STUB_PUSH=push,
                        GH_STUB_MERGED=merged, GH_STUB_FAIL=fail)

    def gh_state(self):
        f = self.gh_dir / "state.json"
        return json.loads(f.read_text()) if f.exists() else {"prs": [], "issues": []}

    def repo(self, name="proj"):
        r = self.tmp / name
        r.mkdir()
        self.git("init", "-q", "-b", "main", cwd=r)
        (r / "README.md").write_text("x\n")
        self.git("add", ".", cwd=r)
        self.git("commit", "-q", "-m", "init", cwd=r)
        return r
