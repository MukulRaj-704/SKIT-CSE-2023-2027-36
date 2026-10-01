"""
analyzer/config.py
==================
Every tunable number of the analyzer lives here (weights, limits, thresholds).
Values can be overridden from ``settings.py`` with an ``ANALYZER_`` prefix,
e.g. ``ANALYZER_MAX_UPLOAD_SIZE_MB = 10``; nothing has to be configured.
"""

from django.conf import settings


def _setting(name, default):
    return getattr(settings, f"ANALYZER_{name}", default)


# --- General ATS score (Mode 1): weights must describe 100% -----------------
ATS_WEIGHTS = _setting(
    "ATS_WEIGHTS",
    {
        "structure": 0.20,
        "skills": 0.20,
        "experience": 0.15,
        "projects": 0.15,
        "education": 0.10,
        "contact": 0.10,
        "formatting": 0.10,
    },
)

# --- Job match score (Mode 2). Components without data are skipped and the
# remaining weights are re-normalised, so a JD without an education requirement
# does not silently drag the score down. -------------------------------------
JOB_MATCH_WEIGHTS = _setting(
    "JOB_MATCH_WEIGHTS",
    {
        "skills": 0.35,
        "keywords": 0.20,
        "experience": 0.15,
        "projects": 0.10,
        "education": 0.10,
        "semantic": 0.10,
    },
)

# --- Upload limits ----------------------------------------------------------
MAX_UPLOAD_SIZE_MB = _setting("MAX_UPLOAD_SIZE_MB", 5)
ALLOWED_EXTENSIONS = (".pdf", ".docx")
MIN_RESUME_CHARS = _setting("MIN_RESUME_CHARS", 40)  # below: nothing to analyse
MAX_RESUME_CHARS = _setting("MAX_RESUME_CHARS", 60000)  # above: refuse (abuse guard)
SHORT_RESUME_WORDS = 150
LONG_RESUME_PAGES = 2
MIN_JD_CHARS = _setting("MIN_JD_CHARS", 30)
MAX_JD_CHARS = _setting("MAX_JD_CHARS", 20000)

# --- Semantic similarity ----------------------------------------------------
# Baseline is a pure-python TF-IDF + cosine similarity (explainable, no extra
# dependency). Set ANALYZER_USE_SBERT = True to use sentence-transformers when
# it is installed; the scorer falls back to TF-IDF automatically otherwise.
USE_SBERT = _setting("USE_SBERT", False)
SBERT_MODEL = _setting("SBERT_MODEL", "all-MiniLM-L6-v2")
# A cosine similarity at/above this value counts as a "full" semantic match.
SEMANTIC_FULL_MATCH = {"tfidf": 0.30, "sbert": 0.70}
# A JD requirement whose best resume evidence scores below this is a "gap".
SEMANTIC_GAP_THRESHOLD = {"tfidf": 0.08, "sbert": 0.35}


def normalised(weights: dict) -> dict:
    total = sum(weights.values()) or 1.0
    return {k: v / total for k, v in weights.items()}

# --- API ---------------------------------------------------------------------
THROTTLE_RATE = _setting("THROTTLE_RATE", "60/hour")  # per anonymous client
