import difflib
import hashlib
import json
import math
import re
import shutil
import tomllib
from pathlib import Path

from golden import fsutil, glossary, names, overlay, profile, scan, similar
from golden.practices import _check, kinds, split_frontmatter

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
    d = project / ".golden" / "contrib" / slug
    if must_exist and not d.is_dir():
        raise ContribError("no contribution %s; start one with golden contrib new <idea>" % slug)
    return d


def new(project: Path, idea: str) -> str:
    slug = names.slug(idea)
    d = folder(project, slug, must_exist=False)
    if d.is_dir():
        return "draft exists: %s; continue it or golden contrib discard %s --confirm\n" % (d, slug)
    d.mkdir(parents=True)
    fsutil.atomic_write(d / "idea.txt", idea + "\n")
    return "write the practice draft to %s, then run golden contrib check %s\n" % (d / "draft.md", slug)


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
        raise ContribError("not checked; run golden contrib check %s" % slug) from None
    if not chk.get("passed"):
        raise ContribError("the last check failed; fix the draft and run golden contrib check %s" % slug)
    if chk.get("sha256") != sha256(d / "sanitized.md"):
        raise ContribError("sanitized.md changed after check; run golden contrib check %s again" % slug)
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
