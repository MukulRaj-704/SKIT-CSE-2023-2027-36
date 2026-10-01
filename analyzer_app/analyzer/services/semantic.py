"""
analyzer/services/semantic.py
=============================
Explainable semantic similarity.

Baseline: TF-IDF (unigrams + bigrams, sub-linear tf) + cosine similarity, written
in pure Python so it needs no extra dependency. Spelling variants are first
mapped onto canonical skill tokens ("RESTful APIs" -> "rest_api"), which makes
the baseline recognise more than literal word overlap.

Optional: set ``ANALYZER_USE_SBERT = True`` to use sentence-transformers (falls
back to TF-IDF when it is not installed).
"""

from __future__ import annotations

import math
import re
from collections import Counter

from .. import config
from . import skills_taxonomy as tax

_TOKEN = re.compile(r"[a-z][a-z0-9_+#]{1,}")
_STOP = set("""the and for with you your our are will have this that from who job role team work years
 experience strong ability including such etc must should can into using use used able also any all
 their they them about more new""".split())
_sbert = None


def _slug(name: str) -> str:
    # "c++" -> "cplusplus", "node.js" -> "nodedotjs": unique, alphanumeric, never re-matched.
    for a, b in (("++", "plusplus"), ("#", "sharp"), (".", "dot"), ("/", "slash")):
        name = name.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _canonicalise(text: str) -> str:
    """Replace every taxonomy mention by one token so aliases compare equal."""
    from .skills_taxonomy import _PATTERNS

    out = text
    for pattern, name in _PATTERNS:
        out = pattern.sub(" skx" + _slug(name) + " ", out)
    return out


def _tokens(text: str) -> list:
    text = _canonicalise(text)
    words = [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9_+#]{1,}", text)]
    words = [w[:-1] if (w.endswith("s") and len(w) > 4 and not w.startswith("skx")) else w for w in words]
    words = [w for w in words if w not in _STOP]
    return words + [f"{a}_{b}" for a, b in zip(words, words[1:])]


def _tfidf_vectors(docs: list) -> list:
    toks = [Counter(_tokens(d)) for d in docs]
    n = len(docs)
    df = Counter(t for c in toks for t in c)
    idf = {t: math.log((1 + n) / (1 + d)) + 1 for t, d in df.items()}
    vecs = []
    for c in toks:
        v = {t: (1 + math.log(f)) * idf[t] for t, f in c.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs.append({t: x / norm for t, x in v.items()})
    return vecs


def _cos(a: dict, b: dict) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def _get_sbert():
    global _sbert
    if _sbert is None:
        from sentence_transformers import SentenceTransformer

        _sbert = SentenceTransformer(config.SBERT_MODEL)
    return _sbert


def similarity_matrix(left: list, right: list):
    """cosine[i][j] for every pair; returns (matrix, backend_name)."""
    if config.USE_SBERT:
        try:
            model = _get_sbert()
            a = model.encode(left, normalize_embeddings=True)
            b = model.encode(right, normalize_embeddings=True)
            return [[float(x @ y) for y in b] for x in a], "sbert"
        except Exception:
            pass
    vecs = _tfidf_vectors(left + right)
    lv, rv = vecs[: len(left)], vecs[len(left):]
    return [[_cos(x, y) for y in rv] for x in lv], "tfidf"


def chunk_resume(parsed: dict, raw_text: str) -> list:
    """Resume statements to compare against: bullets, summary, project/skill lines."""
    chunks = []
    if parsed.get("summary"):
        chunks.append(parsed["summary"])
    for e in (parsed.get("experience") or []) + (parsed.get("internships") or []):
        chunks.extend(e.get("bullets", []))
    for p in parsed.get("projects") or []:
        chunks.append(" ".join(filter(None, [p.get("name"), " ".join(p.get("technologies", [])), p.get("description")])))
        chunks.extend(p.get("bullets", []))
    if parsed.get("skills"):
        chunks.append(", ".join(s["name"] for s in parsed["skills"]))
    chunks = [c for c in chunks if c and len(c.split()) >= 3]
    return chunks or [ln.strip() for ln in raw_text.split("\n") if len(ln.split()) >= 4]


def semantic_match(parsed: dict, raw_text: str, jd_text: str, requirements: list) -> dict:
    """
    For each JD requirement, the best-matching resume statement; the score is the
    mean best similarity, scaled so a "full" match (config) equals 100.
    """
    chunks = chunk_resume(parsed, raw_text)
    reqs = [r for r in requirements if len(r.split()) >= 3]
    if not chunks or not reqs:
        doc, backend = similarity_matrix([jd_text], [raw_text])
        return {"score": None if not reqs else 0, "doc_similarity": round(doc[0][0], 3), "backend": backend, "strong": [], "gaps": []}

    sim, backend = similarity_matrix(reqs, chunks)
    full = config.SEMANTIC_FULL_MATCH[backend]
    gap_thr = config.SEMANTIC_GAP_THRESHOLD[backend]
    best = [max(row) for row in sim]
    strong, gaps = [], []
    for req, row, b in zip(reqs, sim, best):
        j = row.index(b)
        item = {"requirement": req, "resume_evidence": chunks[j], "similarity": round(b, 3)}
        (gaps if b < gap_thr else strong).append(item)
    score = round(100 * min(1.0, (sum(best) / len(best)) / full))
    doc, _ = similarity_matrix([jd_text], [raw_text])
    return {"score": score, "doc_similarity": round(doc[0][0], 3), "backend": backend, "strong": strong[:5], "gaps": gaps[:5]}
