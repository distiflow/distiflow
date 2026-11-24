import json
import shutil
import subprocess
from pathlib import Path

from golden import fsutil, names


class GitError(Exception):
    pass


def git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def _last_line(r: subprocess.CompletedProcess) -> str:
    lines = (r.stderr.strip() or r.stdout.strip()).splitlines()
    return lines[-1] if lines else "git exited %d" % r.returncode


def must(*args: str, cwd: Path) -> str:
    r = git(*args, cwd=cwd)
    if r.returncode != 0:
        raise GitError(_last_line(r))
    return r.stdout


def gh(*args: str, cwd: Path) -> subprocess.CompletedProcess | None:
    """None when gh is not installed."""
    if shutil.which("gh") is None:
        return None
    return subprocess.run(["gh", *args], cwd=cwd, capture_output=True, text=True)


def path_for(project: Path, task_id: str) -> Path:
    return project.parent / ("%s.golden" % project.name) / task_id


def checkout_claim(project: Path) -> Path:
    return project / ".golden" / "tasks" / "checkout.claim"


def checkout_holder(project: Path) -> str | None:
    try:
        return json.loads(checkout_claim(project).read_text(encoding="utf-8")).get("task")
    except (OSError, ValueError, AttributeError):
        return None


def release_checkout(project: Path, task_id: str) -> None:
    if checkout_holder(project) == task_id:
        checkout_claim(project).unlink(missing_ok=True)


def _branch_exists(project: Path, branch: str) -> bool:
    return git("rev-parse", "--verify", "--quiet", "refs/heads/" + branch, cwd=project).returncode == 0


def enter_implement(project: Path, st: dict, git_conf: dict, session: str) -> str:
    """Give the task its working copy and set st branch/worktree. Raises GitError or ValueError; st unchanged then."""
    branch = st["branch"] or names.branch_name(git_conf["branch"], st["kind"], st["desc"], st["id"])
    if st["mode"] == "worktree":
        path = path_for(project, st["id"])
        if path.exists():
            # A worktree left by an advance whose state write failed is reused, anything else refused.
            if git("rev-parse", "--abbrev-ref", "HEAD", cwd=path).stdout.strip() != branch:
                raise GitError("%s exists and is not the working copy of branch %s" % (path, branch))
        elif _branch_exists(project, branch):
            must("worktree", "add", "--", str(path), branch, cwd=project)
        else:
            must("worktree", "add", "-b", branch, "--", str(path), git_conf["base"], cwd=project)
        st.update(branch=branch, worktree=str(path))
        return ""
    created = False
    try:
        fsutil.create_exclusive(checkout_claim(project), json.dumps({"task": st["id"], "session": session}))
        created = True
    except FileExistsError:
        other = checkout_holder(project)
        if other != st["id"]:
            raise GitError("the checkout is in use by task %s" % (other or "unknown (unreadable checkout.claim)"))
    try:
        must(*(("switch", branch) if _branch_exists(project, branch) else ("switch", "-c", branch)), cwd=project)
    except GitError:
        if created:
            checkout_claim(project).unlink(missing_ok=True)
        raise
    st.update(branch=branch, worktree=None)
    return "parallel implement is unavailable in this project (worktrees off)\n"


def is_merged(project: Path, branch: str, base: str, confirmed: bool) -> bool:
    r = gh("pr", "view", branch, "--json", "state", "-q", ".state", cwd=project)
    if r is not None and r.returncode == 0 and r.stdout.strip() == "MERGED":
        return True
    git("fetch", "-q", "origin", base, cwd=project)  # offline or no remote: fall back to the local base
    target = "origin/" + base
    if git("rev-parse", "--verify", "--quiet", target, cwd=project).returncode != 0:
        target = base
    if git("merge-base", "--is-ancestor", branch, target, cwd=project).returncode == 0:
        return True
    return confirmed


def porcelain(path: Path) -> str:
    return git("status", "--porcelain", cwd=path).stdout.rstrip() if path.exists() else ""


def remove(project: Path, path: Path, force: bool = False) -> None:
    if not path.exists():
        git("worktree", "prune", cwd=project)
        return
    must("worktree", "remove", *(["--force"] if force else []), "--", str(path), cwd=project)


def restore(project: Path, path: Path, branch: str) -> None:
    git("worktree", "prune", cwd=project)
    must("worktree", "add", "--", str(path), branch, cwd=project)


def push_and_request(project: Path, wc: Path, branch: str, base: str) -> str | None:
    """Push the branch and return the request URL; None when gh is missing or signed out."""
    must("push", "-q", "-u", "origin", branch, cwd=wc)
    r = gh("pr", "list", "--head", branch, "--json", "url", "-q", ".[0].url", cwd=project)
    if r is None or r.returncode != 0:
        return None
    if r.stdout.strip():
        return r.stdout.strip()
    r = gh("pr", "create", "--fill", "--head", branch, "--base", base, cwd=project)
    if r.returncode != 0:
        raise GitError("gh pr create failed: %s" % _last_line(r))
    return r.stdout.strip().splitlines()[-1]
