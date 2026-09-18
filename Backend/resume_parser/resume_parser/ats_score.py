"""
ATS Resume Score Checker (Python version)
-------------------------------------------
Compares a resume against a job description and produces:
  - Skills/keyword match %
  - Experience-terms match %
  - Overall ATS score
  - Matched / missing keywords

Usage:
    python ats_score.py

Or import and use programmatically:
    from ats_score import calculate_ats_score
    result = calculate_ats_score(jd_text, resume_text)
"""

import re
from collections import Counter

STOPWORDS = set("""
a an the and or but is are was were be been being to of in on for with as by at
from that this these those it its we you your our will shall can could should would
may might must have has had do does did not no so if than then also into about across
per etc including include years year experience experienced strong good excellent
ability skills skill knowledge understanding work working team role job candidate
responsibilities requirements preferred plus using use used
""".split())

EXP_TERMS = [
    "years", "year", "senior", "junior", "lead", "manager", "internship", "intern",
    "experience", "fresher", "entry-level", "mid-level",
    "5+", "3+", "2+", "10+", "7+", "4+", "1+"
]


def tokenize(text: str):
    """Lowercase, extract word-like tokens, strip stopwords/pure numbers."""
    words = re.findall(r"[a-zA-Z0-9\+\#\.\-]{2,}", text.lower())
    cleaned = []
    for w in words:
        w = w.strip(".-")
        if w and w not in STOPWORDS and not w.isdigit():
            cleaned.append(w)
    return cleaned


def key_phrases(text: str) -> Counter:
    """Frequency count of unigrams + bigrams (skipping stopword bigrams)."""
    words = tokenize(text)
    freq = Counter(words)
    for i in range(len(words) - 1):
        if words[i] not in STOPWORDS and words[i + 1] not in STOPWORDS:
            freq[f"{words[i]} {words[i + 1]}"] += 1
    return freq


def calculate_ats_score(jd_text: str, resume_text: str, top_n: int = 40) -> dict:
    """Return a dict with scores and matched/missing keyword lists."""
    jd_freq = key_phrases(jd_text)

    # Top JD keywords: higher frequency first, then longer phrases first
    jd_keywords = sorted(
        jd_freq.keys(),
        key=lambda k: (-jd_freq[k], -len(k))
    )[:top_n]

    resume_lower = resume_text.lower()
    matched = [k for k in jd_keywords if k in resume_lower]
    missing = [k for k in jd_keywords if k not in resume_lower]

    skills_pct = round((len(matched) / len(jd_keywords)) * 100) if jd_keywords else 0

    jd_lower = jd_text.lower()
    jd_exp_hits = [t for t in EXP_TERMS if t in jd_lower]
    resume_exp_hits = [t for t in jd_exp_hits if t in resume_lower]
    exp_pct = round((len(resume_exp_hits) / len(jd_exp_hits)) * 100) if jd_exp_hits else 100

    overall_pct = round(skills_pct * 0.65 + exp_pct * 0.35)

    if overall_pct >= 75:
        verdict = "Strong match — resume aligns well with this job description."
    elif overall_pct >= 50:
        verdict = "Moderate match — add missing keywords below to improve ATS ranking."
    else:
        verdict = "Weak match — resume likely needs significant keyword/skill additions."

    return {
        "overall_score": overall_pct,
        "skills_match_pct": skills_pct,
        "experience_match_pct": exp_pct,
        "matched_keywords": matched,
        "missing_keywords": missing,
        "verdict": verdict,
    }


def print_report(result: dict):
    print("\n===== ATS SCORE REPORT =====")
    print(f"Overall Score        : {result['overall_score']}%")
    print(f"Skills Match         : {result['skills_match_pct']}%")
    print(f"Experience Match     : {result['experience_match_pct']}%")
    print(f"Verdict              : {result['verdict']}")
    print(f"\nMatched Keywords ({len(result['matched_keywords'])}):")
    print(", ".join(result['matched_keywords']) or "None")
    print(f"\nMissing Keywords ({len(result['missing_keywords'])}):")
    print(", ".join(result['missing_keywords']) or "None — great coverage!")
    print("=============================\n")


if __name__ == "__main__":
    jd_text = """
    We are looking for a Data Scientist / Machine Learning Engineer with 2+ years of experience.
    Build and deploy machine learning models for production use. Work with large datasets using
    Python, Pandas, and NumPy. Develop ensemble learning models (Random Forest, XGBoost).
    Design ML pipelines. Collaborate using Django REST Framework and React.js.
    Deploy models using Docker and cloud platforms (AWS/GCP). Work with SQL databases.
    Strong knowledge of Python, Scikit-learn, TensorFlow or PyTorch required.
    """

    resume_text = """
    Data Science Intern, Celebal Technologies. Built machine learning models using Python,
    Scikit-learn and Pandas. Worked on ensemble learning techniques including Random Forest.
    Full-Stack Intern: Developed REST APIs using Django REST Framework, built frontend with React.js.
    Skills: Python, Pandas, NumPy, Scikit-learn, SQL, Django REST Framework, React.js, Git.
    """

    result = calculate_ats_score(jd_text, resume_text)
    print_report(result)
