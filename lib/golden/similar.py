import math
import re
from collections import Counter

from golden.glossary import body_lines

STOPWORDS = set("a an and are as at be before by for from if in into is it its of on one only or so such that the "
                "then this to when with".split())


def _tokens(text: str) -> Counter:
    words = re.findall(r"[a-z0-9]+", "\n".join(body_lines(text)).lower())
    return Counter(w for w in words if w not in STOPWORDS)


def shortlist(text: str, corpus: dict[str, str], k: int = 5) -> list[tuple[str, float]]:
    """TF-IDF cosine of text against each corpus entry; order (-score, id)."""
    docs = {pid: _tokens(body) for pid, body in corpus.items()}
    query = _tokens(text)
    n = len(docs) + 1
    df = Counter(w for d in list(docs.values()) + [query] for w in d)
    idf = {w: math.log((n + 1) / (c + 1)) + 1 for w, c in df.items()}

    def vec(c: Counter) -> dict:
        return {w: tf * idf[w] for w, tf in c.items()}

    def norm(v: dict) -> float:
        return math.sqrt(sum(x * x for x in v.values()))

    q = vec(query)
    scores = []
    for pid, d in docs.items():
        v = vec(d)
        denom = norm(q) * norm(v)
        dot = sum(x * v.get(w, 0.0) for w, x in q.items())
        scores.append((pid, round(dot / denom, 3) if denom else 0.0))
    return sorted(scores, key=lambda s: (-s[1], s[0]))[:k]
