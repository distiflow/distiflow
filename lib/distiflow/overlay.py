import hashlib
import posixpath
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from distiflow import fsutil
from distiflow.paths import version
from distiflow.practices import Issue, Malformed, Practice, kinds, parse_practice

_HEADER = re.compile(r"(?:<!--|#) distiflow-override upstream=(\S+) version=(\S+)(?: -->)?$")


@dataclass
class Resolved:
    path: Path
    source: str  # upstream | overridden
    issues: list = field(default_factory=list)


def override_dir(project: Path) -> Path:
    return project / ".distiflow" / "overrides"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def override_status(rel: str, root: Path, project: Path) -> tuple[str, Issue | None]:
    """ok | drift | orphan for an existing override file."""
    upstream = root / "core" / rel
    if not upstream.is_file():
        return "orphan", Issue("orphan", rel, "override of %s: upstream file is gone" % rel)
    first = (override_dir(project) / rel).read_text(encoding="utf-8").partition("\n")[0]
    m = _HEADER.match(first)
    if not m or m.group(1) != sha256(upstream):
        return "drift", Issue("drift", rel, "%s changed upstream since it was overridden" % rel)
    return "ok", None


def resolve(rel: str, root: Path, project: Path | None) -> Resolved:
    if project is not None and (override_dir(project) / rel).is_file():
        _, issue = override_status(rel, root, project)
        return Resolved(override_dir(project) / rel, "overridden", [issue] if issue else [])
    return Resolved(root / "core" / rel, "upstream")


def _merge(base: dict, over: dict, rel: str, prefix: str, issues: list) -> dict:
    out = dict(base)
    for k, v in over.items():
        dotted = prefix + k
        if k not in base:
            issues.append(Issue("stale-key", "%s:%s" % (rel, dotted), "key %s is not upstream; ignored" % dotted))
        elif isinstance(v, dict) and isinstance(base[k], dict):
            out[k] = _merge(base[k], v, rel, dotted + ".", issues)
        else:
            out[k] = v
    return out


def load_toml(rel: str, root: Path, project: Path | None) -> tuple[dict, list[Issue]]:
    upstream = root / "core" / rel
    base = tomllib.loads(upstream.read_text(encoding="utf-8")) if upstream.is_file() else {}
    r = resolve(rel, root, project)
    if r.source == "upstream":
        return base, []
    issues = list(r.issues)
    over = tomllib.loads(r.path.read_text(encoding="utf-8"))
    if not upstream.is_file():
        return over, issues
    return _merge(base, over, rel, "", issues), issues


def _rels(base: Path) -> list[str]:
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*.md")) if base.is_dir() else []


def load_practices(root: Path, project: Path | None) -> tuple[list[Practice], list[Issue]]:
    known = kinds(root)
    out, issues, upstream_ids = [], [], set()
    for rel in ("practices/" + r for r in _rels(root / "core" / "practices")):
        r = resolve(rel, root, project)
        issues += r.issues
        upstream_ids.add(Path(rel).stem)
        try:
            out.append(parse_practice(r.path, r.source, known))
        except Malformed as e:
            issues.append(Issue("malformed", rel, e.reason))
    if project is None:
        return out, issues
    for rel in ("practices/" + r for r in _rels(override_dir(project) / "practices")):
        if not (root / "core" / rel).is_file():
            issues.append(override_status(rel, root, project)[1])
    for rel in _rels(project / ".distiflow" / "practices"):
        path = project / ".distiflow" / "practices" / rel
        if path.stem in upstream_ids:
            issues.append(Issue("clash", path.stem, ".distiflow/practices/%s has the id of an upstream practice; "
                                                    "use distiflow override to change it" % rel))
            continue
        try:
            out.append(parse_practice(path, "local", known))
        except Malformed as e:
            issues.append(Issue("malformed", ".distiflow/practices/" + rel, e.reason))
    return out, issues


class OverrideError(Exception):
    pass


def make_override(rel: str, root: Path, project: Path) -> Path:
    core = (root / "core").resolve()
    if (not rel or rel.startswith("/") or posixpath.normpath(rel) != rel or ".." in rel.split("/")
            or not (core / rel).resolve().is_relative_to(core)):
        raise OverrideError("%s: not a path under core/" % rel)
    upstream = core / rel
    if not upstream.is_file():
        raise OverrideError("%s: no such upstream file" % rel)
    if upstream.suffix not in (".md", ".toml"):
        raise OverrideError("%s: only .md and .toml files can be overridden" % rel)
    meta = "distiflow-override upstream=%s version=%s" % (sha256(upstream), version(root))
    line = "<!-- %s -->" % meta if upstream.suffix == ".md" else "# " + meta
    target = override_dir(project) / rel
    try:
        fsutil.create_exclusive(target, line + "\n" + upstream.read_text(encoding="utf-8"))
    except FileExistsError:
        raise OverrideError("%s: override already exists at %s" % (rel, target)) from None
    return target


def list_overrides(root: Path, project: Path) -> list[tuple[str, str]]:
    base = override_dir(project)
    rels = sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()) if base.is_dir() else []
    return [(rel, override_status(rel, root, project)[0]) for rel in rels]
