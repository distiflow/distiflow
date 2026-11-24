import difflib
import hashlib
import json
import math
import re
import shutil
import tomllib
from pathlib import Path

from distiflow import fsutil, glossary, names, overlay, profile, scan, similar, skills, worktree
from distiflow.practices import _check, kinds, split_frontmatter, stage_problems

SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
# Upstream files a contribution may edit; the alphabet keeps "..", absolute paths and TOML out.
EDITABLE = re.compile(r"core/stages/[a-z]+\.md|core/practices/[a-z]+/[a-z0-9][a-z0-9-]*\.md"
                      r"|skills/[a-z0-9][a-z0-9-]*/SKILL\.md")
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


def new(project: Path, idea: str, skill: Path | None = None) -> str:
    text = None
    if skill is not None:
        src = skill / "SKILL.md"
        if not src.is_file():
            raise ContribError("no SKILL.md in %s" % skill)
        # shortcut: SKILL.md only, since scripts in a shared skill run for every installer; widen when a skill needs files.
        extra = sorted(f.relative_to(skill).as_posix() for f in skill.rglob("*")
                       if f.is_file() and f != src and f.name != ".DS_Store")
        if extra:
            raise ContribError("shared skills hold only SKILL.md; remove or inline: %s" % ", ".join(extra))
        text = src.read_text(encoding="utf-8")
        try:
            idea = skills.parse(text)["name"]
        except ValueError as e:
            raise ContribError("%s: %s" % (src, e)) from None
    slug = names.slug(idea)
    d = folder(project, slug, must_exist=False)
    if d.is_dir():
        return "draft exists: %s; continue it or distiflow contrib discard %s --confirm\n" % (d, slug)
    d.mkdir(parents=True)
    fsutil.atomic_write(d / "idea.txt", idea + "\n")
    if text is None:
        return "write the practice draft to %s, then run distiflow contrib check %s\n" % (d / "draft.md", slug)
    fsutil.atomic_write(d / "kind", "skill\n")
    fsutil.atomic_write(d / "draft.md", text)
    return "skill copied to %s; edit it if needed, then run distiflow contrib check %s\n" % (d / "draft.md", slug)


def _edit_id(rel: str) -> str:
    return rel.split("/")[1] if rel.startswith("skills/") else Path(rel).stem


def _edit_kind(rel: str) -> str:
    return "skill" if rel.startswith("skills/") else "stage" if rel.startswith("core/stages/") else "practice"


def new_edit(root: Path, project: Path, rel: str) -> str:
    """Start an edit of one upstream file, from the project's override body when there is one."""
    if not EDITABLE.fullmatch(rel) or (rel.startswith("skills/") and _edit_id(rel) not in skills.shared(root)):
        raise ContribError("%s: only core/stages/<stage>.md, core/practices/<stage>/<id>.md or "
                           "skills/<shared skill>/SKILL.md can be edited" % rel, 2)
    f = root / rel
    if not f.is_file():
        raise ContribError("%s: no such upstream file" % rel)
    slug = "edit-" + _edit_id(rel)
    d = folder(project, slug, must_exist=False)
    if d.is_dir():
        return "draft exists: %s; continue it or distiflow contrib discard %s --confirm\n" % (d, slug)
    text, base = f.read_text(encoding="utf-8"), sha256(f)
    o = overlay.override_dir(project) / rel.removeprefix("core/")
    if rel.startswith("core/") and o.is_file():
        first, _, body = o.read_text(encoding="utf-8").partition("\n")
        m = overlay._HEADER.match(first)
        if m:
            text, base = body, m.group(1)
    d.mkdir(parents=True)
    fsutil.atomic_write(d / "edit.json", json.dumps({"target": rel, "base": base}))
    fsutil.atomic_write(d / "draft.md", text)
    return "%s copied to %s; edit it, then run distiflow contrib check %s\n" % (rel, d / "draft.md", slug)


def _edit(d: Path) -> dict | None:
    try:
        return json.loads((d / "edit.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _is_skill(d: Path) -> bool:
    return (d / "kind").is_file() and (d / "kind").read_text(encoding="utf-8").strip() == "skill"


def upstream_practices(root: Path) -> dict[str, Path]:
    return {p.stem: p for p in sorted((root / "core" / "practices").rglob("*.md"))}


def _limits(root: Path, project: Path) -> dict:
    return overlay.load_toml("limits.toml", root, project)[0]


def _format(text: str, root: Path, project: Path, kind: str, name: str | None) -> tuple[list, dict]:
    """Format and size problems of a practice, skill or stage draft; name pins the id an edit keeps."""
    limits, meta, found = _limits(root, project), {}, []
    tokens = math.ceil(len(text) / 4)
    if kind == "skill":
        found = skills.problems(text, name, limits.get("skill", {}).get("max_tokens", 5000))
        try:
            meta = skills.parse(text)
            meta["id"] = meta["name"]
        except ValueError:
            pass
        return found, meta
    if kind == "stage":
        found, meta, limit = stage_problems(text), {"id": name}, limits.get("stage", {}).get("max_tokens", 2000)
    else:
        try:
            front, _ = split_frontmatter(text)
            meta = tomllib.loads(front)
            _check(meta, Path("%s.md" % meta.get("id", "")), kinds(root))
        except (ValueError, tomllib.TOMLDecodeError) as e:
            found.append(str(e))
        if name is not None and meta.get("id") != name:
            found.append("id %s: an edit keeps the id %s" % (meta.get("id"), name))
        limit = limits["practice"]["max_tokens"]
    if tokens > limit:
        found.append("size %d > limit %d" % (tokens, limit))
    return found, meta


def _checks(text: str, root: Path, project: Path, prof: dict, kind: str = "practice",
            name: str | None = None) -> tuple[dict, dict]:
    """Every check runs and reports, also after an earlier one failed (S49)."""
    results = {}
    found, meta = _format(text, root, project, kind, name)
    results["format"] = "; ".join(p for p in found if not p.startswith("size "))
    results["size"] = "; ".join(p for p in found if p.startswith("size "))
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
    edit, skill = _edit(d), _is_skill(d)
    kind = _edit_kind(edit["target"]) if edit else "skill" if skill else "practice"
    results, meta = _checks(text, root, project, prof, kind, _edit_id(edit["target"]) if edit else None)
    upstream_text = (root / edit["target"]).read_text(encoding="utf-8") if edit else ""
    if edit and text == upstream_text:
        results["format"] = "; ".join(filter(None, [results["format"], "no change against upstream"]))
    passed = not any(results.values())
    keys = (() if kind == "stage" else ("name", "description") if kind == "skill"
            else ("stages", "kinds", "signals", "run_cost", "gate"))
    cls = (["target: %s" % edit["target"]] if edit else []) + [
        "%s: %s" % (k, ", ".join(meta[k]) if isinstance(meta.get(k), list) else meta.get(k, "-")) for k in keys]
    diff = difflib.unified_diff((d / "original.md").read_text(encoding="utf-8").splitlines(), text.splitlines(),
                                "original.md", "sanitized.md", lineterm="")
    out = ["## Classification", *cls,
           "## Checks", *("%s: %s" % (c, "pass" if not results[c] else "FAIL " + results[c]) for c in CHECKS),
           "## Replaced terms", *(["%s → %s ×%d" % r for r in replaced] or ["- none"]),
           "## Diff", *(list(diff) or ["- no changes"])]
    if edit:
        change = difflib.unified_diff(upstream_text.splitlines(), text.splitlines(), edit["target"], "sanitized.md",
                                      lineterm="")
        out += ["## Change against upstream", *(list(change) or ["- no changes"])]
    else:
        upstream = skills.shared(root) if skill else upstream_practices(root)
        corpus = {pid: p.read_text(encoding="utf-8") for pid, p in upstream.items() if p.is_file()}
        top = similar.shortlist(text, corpus, _limits(root, project)["contribute"]["shortlist"])
        out += ["## Similar upstream %s" % ("skills" if skill else "practices"),
                *(["%s %.3f" % s for s in top] or ["- none"])]
    fsutil.atomic_write(d / "check.json", json.dumps({"passed": passed, "sha256": sha256(d / "sanitized.md"),
                                                      "id": meta.get("id"), "stages": meta.get("stages"),
                                                      "skill": skill, "edit": edit}))
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
    edit = chk.get("edit")
    if edit and verdict != "edit":
        raise ContribError("an edit is confirmed with --verdict edit (got %s)" % verdict)
    if not edit and kind == "edit":
        raise ContribError("verdict edit is only for drafts started with --edit")
    if kind == "duplicate":
        raise ContribError("duplicate of %s; nothing to send" % pid)
    shared = skills.shared(root)
    if edit:
        target = edit["target"]
    elif chk.get("skill") and kind == "new" and not pid:
        if chk["id"] in shared:
            raise ContribError("skill %s already exists upstream; confirm with --verdict extends:%s"
                               % (chk["id"], chk["id"]))
        target = "skills/%s/SKILL.md" % chk["id"]
    elif chk.get("skill") and kind == "extends" and pid in shared:
        target = "skills/%s/SKILL.md" % pid
    elif chk.get("skill"):
        raise ContribError("verdict must be new, extends:<upstream skill> or duplicate:<skill> (got %s)" % verdict)
    elif kind == "new" and not pid:
        target = "core/practices/%s/%s.md" % (chk["stages"][0], chk["id"])
    elif kind == "extends" and pid in upstream_practices(root):
        target = upstream_practices(root)[pid].relative_to(root).as_posix()
    else:
        raise ContribError("verdict must be new, extends:<upstream id> or duplicate:<id> (got %s)" % verdict)
    # The upstream bytes this draft replaces; send refuses when upstream moved past them.
    base = edit["base"] if edit else sha256(root / target) if kind == "extends" else None
    fsutil.atomic_write(d / "confirmed.json", json.dumps({"sha256": chk["sha256"], "verdict": kind, "target": target,
                                                         "base": base}))
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


def _similar_open(wc: Path, branch: str, text: str, threshold: float, area: str) -> tuple[str, float] | None:
    refs = worktree.git("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin/contrib/", cwd=wc).stdout.split()
    best = None
    for ref in refs:
        other = ref[len("origin/"):]
        if other == branch:
            continue
        files = worktree.git("diff", "--name-only", "origin/main..." + ref, "--", area, cwd=wc).stdout.split()
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
    target = conf["target"]
    area = "/".join(target.split("/")[:1 if target.startswith("skills/") else 2])
    pid = _edit_id(target)
    noun = Path(area).name
    msg = {"new": "feat(%s): add %s", "edit": "docs(%s): edit %s"}.get(conf["verdict"], "docs(%s): extend %s") % (noun, pid)
    # --update is user input that reaches git: only an existing contribution branch name is accepted.
    if update is not None and not (update.startswith("contrib/") and SLUG.fullmatch(update[len("contrib/"):])):
        raise ContribError("not a contribution branch: %r (expected contrib/<slug>)" % update, 2)
    # The branch is public: name it from the checked practice id, never from the raw idea text.
    if not SLUG.fullmatch(pid):
        raise ContribError("id %r cannot name a branch; use lower-case words and hyphens" % pid)
    branch = update or "contrib/%s%s" % ("edit-" if conf["verdict"] == "edit" else "", pid)
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
        base = conf.get("base")
        if base and start == "origin/main" and (not (wc / target).is_file() or sha256(wc / target) != base):
            raise ContribError("%s changed upstream since this draft started; update distiflow, discard the draft "
                               "and start again" % target)
        if not update and not force_new and conf["verdict"] != "edit":
            limit = _limits(root, project)["contribute"]["similar_threshold"]
            near = _similar_open(wc, branch, text, limit, area)
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
            r = worktree.gh("issue", "create", "--repo", repo, "--title", "%s idea: %s" % (noun[:-1].capitalize(), pid),
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
