import ipaddress
import re
import unicodedata
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from golden.worktree import git


@dataclass(frozen=True)
class Finding:
    rule: str
    match: str
    line: int


SECRETS = [re.compile(p) for p in (
    r"AKIA[0-9A-Z]{16}", r"gh[pousr]_[A-Za-z0-9]{36,}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"\bsk-[A-Za-z0-9-]{12,}", r"xox[abprs]-[A-Za-z0-9-]{10,}", r"AIza[0-9A-Za-z_-]{35}",
    r"(?i)\b(?:api[_-]?key|secret|token|passw(?:or)?d)\b\s*[:=]\s*[\"']?[^\s\"']{8,}")]
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Bare hosts need a known TLD, so code identifiers such as os.path never count as hosts.
TLDS = ("com net org io dev app cloud co ai gg me info biz xyz tech site online us uk de eu fr nl pl ua ru ca au "
        "in jp cn br es it ch se no internal local lan corp intra private").split()
HOST = re.compile(r"(?<![\w@.-])((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?:%s))(?![\w-]|\.\w)" % "|".join(TLDS), re.I)
ALLOWED_HOSTS = ("localhost", "example.com", "example.org", "example.net")
IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
IPV6 = re.compile(r"(?<![\w:])[0-9a-fA-F:]*:[0-9a-fA-F:]*:[0-9a-fA-F:]*(?![\w:])")
ALLOWED_IPS = ("127.0.0.1", "0.0.0.0", "::1")
HOSTILE = {
    "remote-exec": [r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba|z|da)?sh\b", r"\b(?:ba|z)?sh\s+<\(\s*(?:curl|wget)\b"],
    "credentials": [r"~/\.ssh\b", r"\bid_(?:rsa|ed25519|ecdsa)\b", r"\.aws/credentials", r"\.netrc\b",
                    r"\b(?:cat|print|show|dump|read|output|contents of)\b.*(?:^|[\s/])\.env\b"],
    "gate-bypass": [r"\bskip(?:ping)?\s+(?:the\s+|all\s+)?gates?\b", r"--no-verify\b",
                    r"\bmark\w*\s+(?:the\s+|a\s+)?gates?\s+(?:as\s+)?pass(?:ed)?\b", r"\bwithout\s+evidence\b"],
}
HOSTILE = {rule: [re.compile(p, re.I) for p in pats] for rule, pats in HOSTILE.items()}
# Cyrillic and Greek letters that look Latin.
HOMOGLYPHS = str.maketrans("аеорсухѕіјԁһԛԝαοριυκτενχ", "aeopcyxsijdhqwaopiuktevx")
_JOINERS = re.compile(r"[-_*`~.]")


def normalize(text: str) -> str:
    """Spellings of one term become one string; whitespace is kept so separate words never join."""
    s = unicodedata.normalize("NFKC", text)
    s = "".join(c for c in s if unicodedata.category(c) != "Cf").casefold().translate(HOMOGLYPHS)  # soft hyphen, zero-width
    return _JOINERS.sub("", urllib.parse.unquote(s))


def _allowed_host(h: str) -> bool:
    h = h.lower()
    return any(h == a or h.endswith("." + a) for a in ALLOWED_HOSTS)


def _ips(line: str) -> list[str]:
    out = []
    for m in IPV4.findall(line):
        if all(int(x) <= 255 for x in m.split(".")) and m not in ALLOWED_IPS:
            out.append(m)
    for m in IPV6.findall(line):
        try:
            ipaddress.IPv6Address(m)
        except ValueError:
            continue
        if m not in ALLOWED_IPS:
            out.append(m)
    return out


def scan_leaks(text: str, deny_terms: list[str]) -> list[Finding]:
    terms = [t for t in (" ".join(normalize(t).split()) for t in deny_terms) if len(t) >= 3]
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        found += [Finding("secret", m.group(0), n) for p in SECRETS for m in p.finditer(line)]
        found += [Finding("email", m, n) for m in EMAIL.findall(line)]
        found += [Finding("host", m, n) for m in HOST.findall(line) if not _allowed_host(m)]
        found += [Finding("ip", m, n) for m in _ips(line)]
        flat = " ".join(normalize(line).split())
        found += [Finding("deny-term", t, n) for t in terms if " " in t and t in flat]
        for token in line.split():
            if any(t in normalize(token) for t in terms):
                found.append(Finding("deny-term", token.strip(".,;:()[]\"'"), n))
    return found


def scan_hostile(text: str) -> list[Finding]:
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        for rule, pats in HOSTILE.items():
            found += [Finding(rule, m.group(0), n) for p in pats for m in p.finditer(line)]
    return found


def _remote_parts(url: str) -> list[str]:
    m = re.match(r"^[\w.-]+@([\w.-]+):(.+)$", url) or re.match(r"^\w+://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+)$", url)
    if not m:
        return []
    path = re.sub(r"\.git$", "", m.group(2).strip("/"))
    return [m.group(1)] + [p for p in path.split("/") if p]


def deny_terms_for(profile: dict, project: Path) -> list[str]:
    proj = profile.get("project", {})
    terms = list(proj.get("deny_terms", [])) + [t for t in (proj.get("name"), project.name) if t]
    for line in git("remote", "-v", cwd=project).stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            terms += _remote_parts(parts[1])
    for cmd in profile.get("commands", {}).values():
        terms += HOST.findall(cmd)
    return list(dict.fromkeys(terms))


def read_deny_file(path: Path) -> list[str]:
    return [t.strip() for t in path.read_text(encoding="utf-8").splitlines() if t.strip() and not t.strip().startswith("#")]


def scan_paths(paths: list[Path], deny_terms: list[str]) -> list[tuple[Path, Finding]]:
    out = []
    for p in paths:
        files = sorted(f for f in p.rglob("*") if f.is_file()) if p.is_dir() else [p]
        for f in files:
            text = f.read_text(encoding="utf-8", errors="replace")
            out += [(f, x) for x in scan_leaks(text, deny_terms) + scan_hostile(text)]
    return out
