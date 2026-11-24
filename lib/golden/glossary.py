import re

STOPLIST = {w.lower() for w in (
    "git CI API TOML JSON YAML CLI URL HTTP HTTPS SQL README CHANGELOG TODO PATH ENV UTF SSH GitHub Python "
    "Markdown Claude ASCII UUID CSV HTML CSS MCP LLM").split()}
_BACKTICK = re.compile(r"`([^`\n]+)`")
_CAPS = re.compile(r"\b(?:[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]*)+|[A-Z]{3,})\b")


def body_lines(text: str) -> list[str]:
    """Lines of text with a leading +++ frontmatter blanked, so line numbers stay true."""
    lines = text.splitlines()
    if lines and lines[0].strip() == "+++":
        end = next((i for i in range(1, len(lines)) if lines[i].strip() == "+++"), 0)
        lines[: end + 1] = [""] * (end + 1)
    return lines


def _word(w: str) -> re.Pattern:
    return re.compile(r"(?<![\w-])%s(?![\w-])" % re.escape(w), re.I)


def _known(glossary: dict) -> set[str]:
    terms = glossary.get("terms", {})
    return {t.lower() for t in terms} | {a.lower() for v in terms.values() for a in v.get("aliases", [])}


def alias_hits(text: str, glossary: dict) -> list[tuple[str, str, int]]:
    pats = [(a, term, _word(a)) for term, v in glossary.get("terms", {}).items() for a in v.get("aliases", [])]
    hits = [(a, term, n) for n, line in enumerate(body_lines(text), 1) for a, term, p in pats if p.search(line)]
    return sorted(hits, key=lambda h: (h[2], h[0]))


def unknown_terms(text: str, glossary: dict) -> list[str]:
    known, found = _known(glossary) | STOPLIST, set()
    for line in body_lines(text):
        found |= {m.strip() for m in _BACKTICK.findall(line)} | set(_CAPS.findall(line))
    return sorted(t for t in found if len(t) >= 3 and t.lower() not in known)


def rewrite(text: str, mapping: dict[str, str]) -> tuple[str, list[tuple[str, str, int]]]:
    """Whole-word, any case; the word boundary keeps a key from eating part of a longer one."""
    keys = list(mapping)
    if not keys:
        return text, []
    by_lower, counts = {k.lower(): k for k in keys}, dict.fromkeys(keys, 0)
    pat = re.compile(r"(?<![\w-])(%s)(?![\w-])" % "|".join(re.escape(k) for k in keys), re.I)

    def sub(m):
        key = by_lower[m.group(1).lower()]
        counts[key] += 1
        return mapping[key]

    out = pat.sub(sub, text)
    return out, [(k, mapping[k], c) for k, c in counts.items() if c]
