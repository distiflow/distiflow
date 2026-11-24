import difflib
import hashlib
import json
import math
import re
import shutil
import tomllib
from pathlib import Path

from distiflow import fsutil, glossary, names, overlay, profile, scan, similar, worktree
from distiflow.practices import _check, kinds, split_frontmatter

SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
CHECKS = ("format", "size", "leaks", "hostile", "glossary-alias")


class ContribError(Exception):
    def __init__(self, msg: str, code: int = 1):
        super().__init__(msg)
        self.code = code


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def folder(project: Path, slug: str, must_exist: bool = True) -> Path:
    # The slug becomes a path: only the slug alphabet may reach the filesystem.
    if not SLUG.fullmatch(slug):
        raise ContribError("not a contribution slug: %r" % slug, 2)
    d = project / ".distiflow" / "contrib" / slug
    if must_exist and not d.is_dir():
        raise ContribError("no contribution %s; start one with distiflow contrib new <idea>" % slug)
    return d


def new(project: Path, idea: str) -> str:
    slug = names.slug(idea)
    d = folder(project, slug, must_exist=False)
    if d.is_dir():
        return "draft exists: %s; continue it or distiflow contrib discard %s --confirm\n" % (d, slug)
    d.mkdir(parents=True)
    fsutil.atomic_write(d / "idea.txt", idea + "\n")
    return "write the practice draft to %s, then run distiflow contrib check %s\n" % (d / "draft.md", slug)


def upstream_practices(root: Path) -> dict[str, Path]:
    return {p.stem: p for p in sorted((root / "core" / "practices").rglob("*.md"))}


def _limits(root: Path, project: Path) -> dict:
    return overlay.load_toml("limits.toml", root, project)[0]


def _checks(text: str, root: Path, project: Path, prof: dict) -> tuple[dict, dict]:
    """Every check runs and reports, also after an earlier one failed (S49)."""
    results, meta = {}, {}
    try:
        front, _ = split_frontmatter(text)
        meta = tomllib.loads(front)
        _check(meta, Path("%s.md" % meta.get("id", "")), kinds(root))
        results["format"] = ""
    except (ValueError, tomllib.TOMLDecodeError) as e:
        results["format"] = str(e)
    tokens, limit = math.ceil(len(text) / 4), _limits(root, project)["practice"]["max_tokens"]
    results["size"] = "" if tokens <= limit else "size %d > limit %d" % (tokens, limit)
    leaks = scan.scan_leaks(text, scan.deny_terms_for(prof, project))
    results["leaks"] = "; ".join("line %d %s: %s" % (f.line, f.rule, f.match) for f in leaks)
    hostile = scan.scan_hostile(text)
    results["hostile"] = "; ".join("line %d %s: %s" % (f.line, f.rule, f.match) for f in hostile)
    terms = tomllib.loads((root / "core" / "glossary.toml").read_text(encoding="utf-8"))
    hits = glossary.alias_hits(text, terms)
    results["glossary-alias"] = "; ".join('line %d alias "%s": use "%s"' % (n, a, t) for a, t, n in hits)
    return results, meta


def check(root: Path, project: Path, slug: str) -> tuple[str, bool]:
    d = folder(project, slug)
    if not (d / "draft.md").is_file():
        raise ContribError("no draft.md in %s; write the draft first" % d)
    draft = (d / "draft.md").read_text(encoding="utf-8")
    if not (d / "original.md").exists():
        fsutil.atomic_write(d / "original.md", draft)
    prof = profile.load_for(root, project, overlay.load_practices(root, project)[0])[0]
    text, replaced = glossary.rewrite(draft, prof.get("glossary", {}))
    fsutil.atomic_write(d / "sanitized.md", text)
    results, meta = _checks(text, root, project, prof)
    passed = not any(results.values())
    cls = ["%s: %s" % (k, ", ".join(meta[k]) if isinstance(meta.get(k), list) else meta.get(k, "-"))
           for k in ("stages", "kinds", "signals", "run_cost", "gate")]
    diff = difflib.unified_diff((d / "original.md").read_text(encoding="utf-8").splitlines(), text.splitlines(),
                                "original.md", "sanitized.md", lineterm="")
    corpus = {pid: p.read_text(encoding="utf-8") for pid, p in upstream_practices(root).items()}
    top = similar.shortlist(text, corpus, _limits(root, project)["contribute"]["shortlist"])
    out = ["## Classification", *cls,
           "## Checks", *("%s: %s" % (c, "pass" if not results[c] else "FAIL " + results[c]) for c in CHECKS),
           "## Replaced terms", *(["%s → %s ×%d" % r for r in replaced] or ["- none"]),
           "## Diff", *(list(diff) or ["- no changes"]),
           "## Similar upstream practices", *(["%s %.3f" % s for s in top] or ["- none"])]
    fsutil.atomic_write(d / "check.json", json.dumps({"passed": passed, "sha256": sha256(d / "sanitized.md"),
                                                      "id": meta.get("id"), "stages": meta.get("stages")}))
    return "\n".join(out) + "\n", passed


def confirm(root: Path, project: Path, slug: str, verdict: str) -> str:
    d = folder(project, slug)
    try:
        chk = json.loads((d / "check.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ContribError("not checked; run distiflow contrib check %s" % slug) from None
    if not chk.get("passed"):
        raise ContribError("the last check failed; fix the draft and run distiflow contrib check %s" % slug)
    if chk.get("sha256") != sha256(d / "sanitized.md"):
        raise ContribError("sanitized.md changed after check; run distiflow contrib check %s again" % slug)
    kind, _, pid = verdict.partition(":")
    if kind == "duplicate":
        raise ContribError("duplicate of %s; nothing to send" % pid)
    if kind == "new" and not pid:
        target = "core/practices/%s/%s.md" % (chk["stages"][0], chk["id"])
    elif kind == "extends" and pid in upstream_practices(root):
        target = upstream_practices(root)[pid].relative_to(root).as_posix()
    else:
        raise ContribError("verdict must be new, extends:<upstream id> or duplicate:<id> (got %s)" % verdict)
    fsutil.atomic_write(d / "confirmed.json", json.dumps({"sha256": chk["sha256"], "verdict": kind, "target": target}))
    return "confirmed %s as %s → %s\n" % (slug, verdict, target)


def discard(project: Path, slug: str, confirmed: bool) -> str:
    d = folder(project, slug)
    if not confirmed:
        raise ContribError("this deletes %s; rerun with --confirm" % d, 2)
    shutil.rmtree(d)
    return "discarded %s\n" % slug


def _upstream(root: Path) -> tuple[str, str]:
    url = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")).get("repository", "")
    m = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if not m:
        raise ContribError("plugin.json has no GitHub repository URL; cannot send", 3)
    return url, "%s/%s" % m.groups()


def _similar_open(wc: Path, branch: str, text: str, threshold: float) -> tuple[str, float] | None:
    refs = worktree.git("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin/contrib/", cwd=wc).stdout.split()
    best = None
    for ref in refs:
        other = ref[len("origin/"):]
        if other == branch:
            continue
        files = worktree.git("diff", "--name-only", "origin/main..." + ref, "--", "core/practices", cwd=wc).stdout.split()
        corpus = {f: worktree.git("show", "%s:%s" % (ref, f), cwd=wc).stdout for f in files}
        top = similar.shortlist(text, corpus, k=1)
        if top and top[0][1] >= threshold and (best is None or top[0][1] > best[1]):
            best = (other, top[0][1])
    return best


def _sent_branch(d: Path) -> str | None:
    try:
        return json.loads((d / "sent.json").read_text(encoding="utf-8")).get("branch")
    except (OSError, ValueError, AttributeError):
        return None


def send(root: Path, project: Path, slug: str, issue: bool = False, update: str | None = None,
         force_new: bool = False) -> str:
    """Send exactly the confirmed bytes; every refusal leaves the draft and the confirm in place."""
    d = folder(project, slug)
    try:
        conf = json.loads((d / "confirmed.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ContribError("not confirmed; run distiflow contrib confirm %s --verdict new|extends:<id>" % slug, 2) from None
    data = (d / "sanitized.md").read_bytes()
    if hashlib.sha256(data).hexdigest() != conf["sha256"]:
        raise ContribError("sanitized.md changed after confirm; check and confirm again")
    prof = profile.load_for(root, project, overlay.load_practices(root, project)[0])[0]
    text = data.decode("utf-8")
    hits = scan.scan_leaks(text, scan.deny_terms_for(prof, project)) + scan.scan_hostile(text)
    if hits:
        raise ContribError("blocked by the final scan: %s" % "; ".join("%s: %s" % (f.rule, f.match) for f in hits))
    push = prof["git"]["push"] == "allowed"
    if push:
        auth = worktree.gh("auth", "status", cwd=project)
        if auth is None or auth.returncode != 0:
            raise ContribError("GitHub sign-in missing: install gh and run gh auth login, then rerun "
                               "distiflow contrib send %s" % slug, 3)
    url, repo = _upstream(root)
    wc = Path.home() / ".distiflow" / "upstream"
    target, pid = conf["target"], Path(conf["target"]).stem
    msg = ("feat(practices): add %s" if conf["verdict"] == "new" else "docs(practices): extend %s") % pid
    # --update is user input that reaches git: only an existing contribution branch name is accepted.
    if update is not None and not (update.startswith("contrib/") and SLUG.fullmatch(update[len("contrib/"):])):
        raise ContribError("not a contribution branch: %r (expected contrib/<slug>)" % update, 2)
    # The branch is public: name it from the checked practice id, never from the raw idea text.
    if not SLUG.fullmatch(pid):
        raise ContribError("practice id %r cannot name a branch; use lower-case words and hyphens" % pid)
    branch = update or "contrib/%s" % pid
    try:
        if not (wc / ".git").is_dir():
            wc.parent.mkdir(parents=True, exist_ok=True)
            worktree.must("clone", "-q", "--", url, str(wc), cwd=wc.parent)
        # The work clone is scratch: anything left from earlier runs is dropped before the commit (R38).
        worktree.must("fetch", "-q", "--prune", "origin", cwd=wc)
        worktree.must("reset", "-q", "--hard", cwd=wc)
        worktree.must("clean", "-q", "-ffdx", cwd=wc)
        start = "origin/" + branch
        if worktree.git("rev-parse", "--verify", "--quiet", start, cwd=wc).returncode != 0:
            start = "origin/main"
        elif not update and _sent_branch(d) != branch:
            raise ContribError("contribution branch %s already exists upstream and was not sent from this draft: "
                               "rerun with --update %s or change the practice id" % (branch, branch), 2)
        worktree.must("checkout", "-q", "-B", branch, start, cwd=wc)
        if not update and not force_new:
            limit = _limits(root, project)["contribute"]["similar_threshold"]
            near = _similar_open(wc, branch, text, limit)
            if near:
                raise ContribError("similar open contribution %s (%.3f): rerun with --update %s or --new"
                                   % (near[0], near[1], near[0]), 2)
        (wc / target).parent.mkdir(parents=True, exist_ok=True)
        fsutil.atomic_write(wc / target, data)
        worktree.must("add", "--", target, cwd=wc)
        if worktree.git("diff", "--cached", "--quiet", cwd=wc).returncode != 0:
            worktree.must("commit", "-q", "-m", msg, cwd=wc)
        changed = worktree.must("diff", "--name-only", start + "...HEAD", cwd=wc).split()
        blob = worktree.git("show", "HEAD:" + target, cwd=wc)
        if not set(changed) <= {target} or blob.returncode != 0 or blob.stdout.encode("utf-8") != data:
            raise ContribError("the work clone holds more than the confirmed change; nothing pushed")
        if not push:
            return ("this project does not let distiflow push; hand off with:\n"
                    "git -C %s push -u origin %s\ngh pr create --repo %s --head %s --base main --title \"%s\"\n"
                    % (wc, branch, repo, branch, msg))
        perm = worktree.gh("api", "repos/" + repo, "--jq", ".permissions.push", cwd=wc)
        if perm.stdout.strip() != "true":
            if not issue:
                raise ContribError("no write access to %s: rerun with --issue to open an issue with the same "
                                   "content" % repo, 2)
            r = worktree.gh("issue", "create", "--repo", repo, "--title", "Practice idea: %s" % pid,
                            "--body-file", str(d / "sanitized.md"), cwd=wc)
            if r.returncode != 0:
                raise ContribError("gh issue create failed; rerun distiflow contrib send %s --issue" % slug)
            link = r.stdout.strip().splitlines()[-1]
            fsutil.atomic_write(d / "sent.json", json.dumps({"issue": link, "sha256": conf["sha256"]}))
            return link + "\n"
        # Recorded before the push, so a rerun after a half-sent push knows the branch is its own.
        fsutil.atomic_write(d / "sent.json", json.dumps({"link": None, "branch": branch, "sha256": conf["sha256"]}))
        worktree.must("push", "-q", "-u", "origin", branch, cwd=wc)
        r = worktree.gh("pr", "list", "--repo", repo, "--head", branch, "--state", "open", "--json", "url",
                        "-q", ".[0].url", cwd=wc)
        if r.returncode == 0 and r.stdout.strip():
            out = "updated %s\n" % r.stdout.strip()
        else:
            fsutil.atomic_write(d / "pr-body.md", "%s\n\nSent with distiflow contrib.\n" % msg)
            r = worktree.gh("pr", "create", "--repo", repo, "--head", branch, "--base", "main", "--title", msg,
                            "--body-file", str(d / "pr-body.md"), cwd=wc)
            if r.returncode != 0:
                raise ContribError("branch pushed, but gh pr create failed; rerun distiflow contrib send %s" % slug)
            out = r.stdout.strip().splitlines()[-1] + "\n"
    except worktree.GitError as e:
        raise ContribError("git: %s" % e) from None
    fsutil.atomic_write(d / "sent.json", json.dumps({"link": out.split()[-1], "branch": branch, "sha256": conf["sha256"]}))
    return out
