import json
import os
import tomllib
from pathlib import Path

from golden import fsutil, glossary, scan, similar
from golden.practices import STAGES, Malformed, kinds, parse_practice
from golden.worktree import git


def _limit(core: Path) -> int:
    try:
        return tomllib.loads((core / "limits.toml").read_text(encoding="utf-8"))["practice"]["max_tokens"]
    except (OSError, ValueError, KeyError):
        return 1500


def _md(base: Path) -> list[Path]:
    return sorted(base.rglob("*.md")) if base.is_dir() else []


def _practices(files: list[Path], rel, known, limit: int, errs: list) -> list:
    out, seen = [], {}
    for f in files:
        try:
            p = parse_practice(f, "upstream", known)
        except Malformed as e:
            errs.append("%s: %s" % (rel(f), e.reason))
            continue
        if p.id in seen:
            errs.append("%s: duplicate id %s (also %s)" % (rel(f), p.id, seen[p.id]))
        seen.setdefault(p.id, rel(f))
        if p.tokens > limit:
            errs.append("%s: size %d > limit %d" % (rel(f), p.tokens, limit))
        out.append(p)
    return out


def _hostile(files: list[Path], rel, errs: list) -> None:
    for f in files:
        errs += ["%s:%d: %s: %s" % (rel(f), x.line, x.rule, x.match) for x in scan.scan_hostile(f.read_text(encoding="utf-8"))]


def _known_kinds(root: Path) -> tuple:
    try:
        return kinds(root)
    except (OSError, ValueError, KeyError):
        return ()


def check_core(root: Path) -> tuple[list[str], list]:
    core, errs = root / "core", []
    rel = lambda f: f.relative_to(root).as_posix()
    errs += ["core/stages/%s.md: missing" % s for s in STAGES if not (core / "stages" / ("%s.md" % s)).is_file()]
    for f in sorted(core.glob("*.toml")):
        try:
            tomllib.loads(f.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            errs.append("%s: invalid TOML: %s" % (rel(f), e))
    practices = _practices(_md(core / "practices"), rel, _known_kinds(root), _limit(core), errs)
    _hostile(_md(core), rel, errs)
    return errs, practices


def _changed(root: Path, base: str | None, practices: list) -> list:
    if base is None and git("rev-parse", "--verify", "--quiet", "origin/main", cwd=root).returncode == 0:
        base = "origin/main"
    if base is None:
        return practices
    diff = git("diff", "--name-only", base, "--", "core/practices", cwd=root)
    if diff.returncode != 0:
        return practices
    new = git("ls-files", "--others", "--exclude-standard", "--", "core/practices", cwd=root).stdout
    names = {Path(n).stem for n in (diff.stdout + new).split()}
    return [p for p in practices if p.id in names]


def check_ci(root: Path, base: str | None) -> tuple[list[str], list[str], str]:
    errs, practices = check_core(root)
    warns, rel = [], lambda f: f.relative_to(root).as_posix()
    try:
        terms = tomllib.loads((root / "core" / "glossary.toml").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        terms = {}
    for f in _md(root / "core"):
        text = f.read_text(encoding="utf-8")
        errs += ["%s:%d: %s: %s" % (rel(f), x.line, x.rule, x.match) for x in scan.scan_leaks(text, [])]
        errs += ['%s:%d: alias "%s": use "%s"' % (rel(f), n, a, t) for a, t, n in glossary.alias_hits(text, terms)]
        warns += ["warning: %s: unknown term %s" % (rel(f), t) for t in glossary.unknown_terms(text, terms)]
    corpus = {p.id: p.path.read_text(encoding="utf-8") for p in practices}
    lines = []
    for p in sorted(_changed(root, base, practices), key=lambda p: p.id):
        others = {k: v for k, v in corpus.items() if k != p.id}
        top = similar.shortlist(corpus[p.id], others)
        if top:
            lines.append("%s: %s" % (p.id, ", ".join("%s %.3f" % s for s in top)))
    return errs, warns, "## Similar practices\n" + ("\n".join(lines) or "- none") + "\n"


def check_local(root: Path, project: Path) -> list[str]:
    """Format checks for a project's own overrides and practices; leak and alias checks guard upstream only."""
    golden, errs = project / ".golden", []
    rel = lambda f: f.relative_to(project).as_posix()
    files = _md(golden / "overrides" / "practices") + _md(golden / "practices")
    _practices(files, rel, _known_kinds(root), _limit(root / "core"), errs)
    _hostile(files + _md(golden / "overrides" / "stages"), rel, errs)
    for f in sorted((golden / "overrides").glob("*.toml")):
        try:
            tomllib.loads(f.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            errs.append("%s: invalid TOML: %s" % (rel(f), e))
    return errs


def check_release(root: Path, tag: str) -> list[str]:
    version = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    market = json.loads((root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    errs = []
    if tag != "v" + version:
        errs.append("tag %s does not match plugin.json version %s" % (tag, version))
    mv = (market.get("plugins") or [{}])[0].get("version")
    if mv != version:
        errs.append("marketplace.json version %s does not match plugin.json version %s" % (mv, version))
    try:
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        changelog = ""
    if "## [%s]" % version not in changelog:
        errs.append("CHANGELOG.md has no ## [%s]" % version)
    return errs


def summary(report: str) -> None:
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        fsutil.append_text(Path(os.environ["GITHUB_STEP_SUMMARY"]), report)
