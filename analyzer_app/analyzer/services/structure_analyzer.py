"""analyzer/services/structure_analyzer.py - which resume sections exist."""

from __future__ import annotations

from .common import all_experience, issue

# Points per section (sum = 100). Experience counts internships too.
POINTS = {"summary": 15, "skills": 25, "education": 20, "experience": 20, "projects": 15, "certifications": 5}


def analyze(parsed: dict) -> dict:
    present = {
        "summary": bool(parsed.get("summary") or parsed.get("objective")),
        "skills": bool(parsed.get("skills")),
        "education": bool(parsed.get("education")),
        "experience": bool(all_experience(parsed)),
        "projects": bool(parsed.get("projects")),
        "certifications": bool(parsed.get("certifications")),
    }
    score = sum(POINTS[k] for k, ok in present.items() if ok)
    issues = []
    if not present["summary"]:
        issues.append(issue("high", "structure", "no_summary",
            "No professional summary was detected. A short 2-3 line summary of your real background "
            "and focus helps both ATS parsing and recruiters; write it only from facts about you."))
    if not present["skills"]:
        issues.append(issue("high", "structure", "no_skills_section",
            "No Skills section was detected. Add a clearly labelled \"Skills\" section listing the "
            "technologies you genuinely work with."))
    if not present["education"]:
        issues.append(issue("high", "structure", "no_education",
            "No Education section was detected. Add your degree, institution and graduation year under an \"Education\" heading."))
    if not present["experience"]:
        sev = "medium" if present["projects"] else "high"
        issues.append(issue(sev, "structure", "no_experience",
            "No work experience or internships were detected. If you have none, strong projects "
            "can carry the resume - do not invent roles; if you do have some (including internships "
            "or freelance work), put it under an \"Experience\" heading."))
    if not present["projects"]:
        issues.append(issue("medium", "structure", "no_projects",
            "No Projects section was detected. If you have built something (academic, personal or open-source), "
            "a \"Projects\" section with the tech stack and your contribution is valuable."))
    if not present["certifications"]:
        issues.append(issue("low", "structure", "no_certifications",
            "No certifications were detected. If you have completed relevant courses or certifications, list them under \"Certifications\"."))
    return {"score": score, "present": present, "issues": issues}
