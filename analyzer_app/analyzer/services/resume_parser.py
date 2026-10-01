"""
analyzer/services/resume_parser.py
==================================
Resume text -> structured data.

Reuses the existing ``resume_parser`` engine (``Backend/resume_parser``) for the
well-behaved parts - contact regexes, skill splitting, degree/GPA regexes and
certification splitting - and extends it where real resumes break it:

* section headings: "Professional Summary", "Achievements", "Languages",
  "Internships" ... (the engine only knows six canonical sections);
* entries: the engine splits experience/projects on blank lines, so a resume
  with blank lines between bullets produces one "job" per bullet. Here an entry
  is a header line plus its bullets (wrapped bullet lines are re-joined);
* hyperlinks: LinkedIn/GitHub are often only anchor text in the PDF, so the
  real URLs come from the document's link annotations.

Output is plain JSON-serialisable data (see ``parse_resume_text``).
"""

from __future__ import annotations

import re

from ..exceptions import EngineUnavailable
from . import skills_taxonomy as tax

_BULLET_RE = re.compile(r"^\s*([-•*\u2022\u25aa\u25cf\u2013\u2014\u00b7▪►➢✓]|\d+[.)])\s+")
_ICON_RE = re.compile(r"[\u0080-\u009f\ue000-\uf8ff\uf000-\uf0ff§¨Ð#ï]")
_SPACES_RE = re.compile(r"[ \t]{3,}")
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE = rf"(?:\d{{1,2}}\s*[/.-]\s*(?:19|20)\d{{2}}|{_MONTH}\s*,?\s*(?:19|20)\d{{2}}|(?:19|20)\d{{2}})"
DATE_RANGE_RE = re.compile(
    rf"(?P<start>{_DATE})\s*(?:-|–|—|to|\|)\s*(?P<end>{_DATE}|present|current|ongoing|now|till date)",
    re.I,
)
_LINK_WORDS = re.compile(r"\b(github|live|demo|link|website|code)\b", re.I)
_URL_RE = re.compile(r"https?://[^\s,)|]+|(?:www\.)[^\s,)|]+", re.I)

# canonical section -> headings seen on real resumes
SECTION_ALIASES = {
    "summary": ["summary", "professional summary", "career summary", "profile", "profile summary", "about me", "about"],
    "objective": ["objective", "career objective", "professional objective"],
    "skills": ["skills", "technical skills", "key skills", "core competencies", "skill set", "technologies", "tech stack", "technical proficiency", "areas of expertise"],
    "education": ["education", "academic background", "academics", "qualification", "qualifications", "academic qualifications", "educational qualification"],
    "experience": ["experience", "work experience", "professional experience", "employment history", "employment", "work history", "relevant experience"],
    "internships": ["internships", "internship", "internship experience", "training"],
    "projects": ["projects", "academic projects", "personal projects", "key projects", "project work", "selected projects"],
    "certifications": ["certifications", "certificates", "licenses & certifications", "courses & certifications", "courses", "licenses and certifications", "certification"],
    "achievements": ["achievements", "awards", "honors", "honours", "accomplishments", "awards & achievements", "awards and achievements", "achievements & awards", "extracurricular", "extracurricular activities", "positions of responsibility"],
    "languages": ["languages", "language proficiency", "spoken languages", "languages known"],
}
STANDARD_HEADINGS = {a for v in SECTION_ALIASES.values() for a in v}
_ALIAS_TO_SECTION = {a: s for s, v in SECTION_ALIASES.items() for a in v}


def _engine():
    """The engine's extractor module (reused, never copied)."""
    try:
        from resume_parser.parser import extractors

        return extractors
    except Exception as exc:  # pragma: no cover - environment dependent
        raise EngineUnavailable(
            "The resume_parser engine is not importable. Add Backend/resume_parser/resume_parser "
            "to PYTHONPATH or install it (`pip install -e`)."
        ) from exc


def clean_text(text: str) -> str:
    """Remove icon glyphs, normalise wide gaps (PDF columns) into ' | '."""
    text = _ICON_RE.sub("", text)
    text = text.replace("\u00a0", " ").replace("\u2019", "'")
    lines = [_SPACES_RE.sub("  |  ", ln.strip()) for ln in text.split("\n")]
    return "\n".join(lines)


def _norm_heading(line: str) -> str:
    return re.sub(r"[^a-z& ]", "", line.lower().replace(":", " ")).strip()


def detect_sections(text: str) -> dict:
    """{section: body}; text before the first heading is the ``header``."""
    lines = text.split("\n")
    marks = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or len(s) > 45 or "|" in s:
            continue
        sec = _ALIAS_TO_SECTION.get(_norm_heading(s).replace("  ", " "))
        if sec:
            marks.append((i, sec))
    if not marks:
        return {"header": text.strip()}
    sections = {"header": "\n".join(lines[: marks[0][0]]).strip()}
    for k, (i, sec) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else len(lines)
        body = "\n".join(lines[i + 1 : end]).strip()
        sections[sec] = f"{sections[sec]}\n{body}" if sec in sections else body
    return sections


def unknown_headings(text: str) -> list:
    """Short ALL-CAPS standalone lines that are not a recognised heading."""
    out = []
    for line in text.split("\n"):
        s = line.strip()
        if 3 <= len(s) <= 35 and s.isupper() and not re.search(r"[\d@|/:+#()]", s) and len(s.split()) <= 4:
            if _norm_heading(s) not in STANDARD_HEADINGS:
                out.append(s.title())
    return out


# ---------------------------------------------------------------------------
# Entry segmentation (experience / projects / internships)
# ---------------------------------------------------------------------------


def _is_bullet(line: str) -> bool:
    return bool(_BULLET_RE.match(line))


def _unpipe(text: str) -> str:
    """Wide PDF gaps became '  |  ' in clean_text; inside prose they mean a space."""
    return text.replace("  |  ", " ").strip()


def _strip_bullet(line: str) -> str:
    return _unpipe(_BULLET_RE.sub("", line, count=1))


def _group_entries(body: str) -> list:
    """Split a section body into [{'header': [lines], 'bullets': [str]}]."""
    entries, cur, last_bullet = [], None, False
    for raw in body.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if _is_bullet(line):
            if cur is None:
                cur = {"header": [], "bullets": []}
                entries.append(cur)
            cur["bullets"].append(_strip_bullet(line))
            last_bullet = True
            continue
        has_date = bool(DATE_RANGE_RE.search(line))
        # A wrapped bullet: follows a bullet and does not look like a new header.
        if cur and last_bullet and not has_date and (line[:1].islower() or not _looks_like_header(line)):
            cur["bullets"][-1] += " " + _unpipe(line)
            continue
        if cur is None or cur["bullets"] or (has_date and any(DATE_RANGE_RE.search(h) for h in cur["header"])):
            cur = {"header": [], "bullets": []}
            entries.append(cur)
        cur["header"].append(line)
        last_bullet = False
    return entries


def _looks_like_header(line: str) -> bool:
    words = line.split()
    if len(words) > 14 or line.endswith("."):
        return False
    return bool(DATE_RANGE_RE.search(line)) or line[:1].isupper()


def _clean_name(text: str) -> str:
    text = DATE_RANGE_RE.sub("", text)
    text = _LINK_WORDS.sub("", text)
    text = _URL_RE.sub("", text)
    text = re.sub(r"\(\s*[|,/\s]*\)|\[\s*[|,/\s]*\]", "", text)  # "()" left behind by a removed link word
    return re.sub(r"\s*[|•]\s*", " ", text).strip(" |-–—,:·")


def _date_parts(lines: list) -> tuple:
    for ln in lines:
        m = DATE_RANGE_RE.search(ln)
        if m:
            return m.group("start"), m.group("end")
    return None, None


def _parse_experience(body: str, internship: bool = False) -> list:
    out = []
    for e in _group_entries(body):
        if not e["header"] and not e["bullets"]:
            continue
        start, end = _date_parts(e["header"])
        heads = [h for h in e["header"]]
        first = _clean_name(heads[0]) if heads else ""
        second = _clean_name(heads[1]) if len(heads) > 1 else ""
        title = company = location = None
        for sep in (" at ", " @ ", " | ", " - ", " – ", " — ", ","):
            if sep in first and not second:
                a, b = (p.strip() for p in first.split(sep, 1))
                title, company = a, b
                break
        else:
            title = first or None
            if second:
                parts = [p.strip() for p in second.split(",", 1)]
                company = parts[0]
                location = parts[1] if len(parts) > 1 else None
        out.append(
            {
                "title": title or None,
                "company": company or None,
                "location": location,
                "start_date": start,
                "end_date": end,
                "bullets": e["bullets"],
                "is_internship": internship or bool(title and re.search(r"intern", title, re.I)),
                "raw_text": "\n".join(e["header"] + e["bullets"]),
            }
        )
    return out


def _parse_projects(body: str) -> list:
    out = []
    for e in _group_entries(body):
        if not e["header"]:
            continue
        name = _clean_name(e["header"][0])
        tech = []
        desc_lines = []
        for ln in e["header"][1:]:
            m = re.match(r"(?:tech(?:nologies)?(?: stack)?|stack|tools?|built with)\s*[:\-]\s*(.+)", ln, re.I)
            body_ln = m.group(1) if m else ln
            parts = [p.strip(" .") for p in re.split(r"[,|;•]+", body_ln) if p.strip(" .")]
            looks_like_stack = m or (len(parts) >= 2 and all(len(p.split()) <= 4 for p in parts) and not ln.endswith("."))
            (tech.extend(parts) if looks_like_stack else desc_lines.append(ln))
        raw = "\n".join(e["header"] + e["bullets"])
        link = _URL_RE.search(raw)
        out.append(
            {
                "name": name or None,
                "description": " ".join(desc_lines),
                "technologies": tech,
                "bullets": e["bullets"],
                "link": link.group(0) if link else None,
                "has_link_hint": bool(link or _LINK_WORDS.search(e["header"][0])),
                "raw_text": raw,
            }
        )
    return out


def _parse_education(body: str) -> list:
    ex = _engine()
    entries, cur = [], None
    inst_re = re.compile(r"\b(university|institute|college|school|academy|vidyalaya|mandir|iit|nit|polytechnic)\b", re.I)
    for raw in body.split("\n"):
        line = raw.strip()
        if not line:
            continue
        if inst_re.search(line) and not re.match(r"^(b\.?tech|m\.?tech|bachelor|master|class)", line, re.I) or cur is None:
            cur = {"lines": []}
            entries.append(cur)
        cur["lines"].append(line)
    out = []
    for e in entries:
        block = "\n".join(e["lines"])
        deg = ex._DEGREE_RE.search(block)
        gpa = ex._GPA_RE.search(block)
        start, end = _date_parts(e["lines"])
        if not start:
            years = re.findall(r"\b(?:19|20)\d{2}\b", block)
            end = years[-1] if years else None
        degree = deg.group(0) if deg else None
        field = None
        if degree:
            degree = re.split(r"\s*\|\s*|\s+CGPA|\s+GPA", degree, flags=re.I)[0].strip(" ,.")
            m = re.search(r"\b(?:in|of)\s+(.+)$", degree, re.I)
            field = m.group(1).strip() if m else None
        out.append(
            {
                "institution": _clean_name(e["lines"][0]) or None,
                "degree": degree,
                "field_of_study": field,
                "start_date": start,
                "end_date": end,
                "gpa": gpa.group(1).strip() if gpa else None,
                "raw_text": block,
            }
        )
    return out


def _bullets_or_lines(body: str) -> list:
    items = []
    for raw in body.split("\n"):
        s = _strip_bullet(raw.strip())
        if not s:
            continue
        if items and raw.strip() and not _is_bullet(raw.strip()) and s[:1].islower():
            items[-1] += " " + s
        else:
            items.append(s)
    return items


def _parse_skills(body: str) -> list:
    ex = _engine()
    names, seen = [], set()
    for line in body.split("\n"):
        line = _strip_bullet(line.replace("|", ",")).strip()
        for sk in ex.extract_skills(line):
            key = sk.name.lower()
            if key not in seen:
                seen.add(key)
                names.append(sk.name)
    skills = []
    for n in names:
        canon = tax.canonical(n)
        skills.append({"name": n, "category": tax.category_of(canon) if canon else "Other"})
    return skills


_PHONE_FALLBACK = re.compile(r"(?<!\d)(?:\+\d{1,3}[\s-]?)?(?:\d{5}[\s-]?\d{5}|\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})(?!\d)")


def _apply_links(contact: dict, links: list, text: str) -> None:
    if not contact.get("phone"):  # the engine's regex misses the common "98765 43210" format
        m = _PHONE_FALLBACK.search(text[:800])
        contact["phone"] = m.group(0).strip() if m else None
    for uri in links:
        low = uri.lower()
        if "linkedin.com" in low and not contact.get("linkedin"):
            contact["linkedin"] = uri
        elif "github.com" in low and not contact.get("github"):
            # profile link, not a repo link
            if len([p for p in low.split("github.com/")[-1].split("/") if p]) == 1:
                contact["github"] = uri
        elif low.startswith("mailto:") and not contact.get("email"):
            contact["email"] = uri[7:]
        elif low.startswith("http") and not any(x in low for x in ("linkedin", "github", "drive.google")) and not contact.get("portfolio"):
            contact["portfolio"] = uri
    ex = _engine()
    if not contact.get("linkedin"):
        m = ex._LINKEDIN_RE.search(text)
        contact["linkedin"] = m.group(0) if m else None
    if not contact.get("github"):
        m = ex._GITHUB_RE.search(text)
        contact["github"] = m.group(0) if m else None
    if not contact.get("email"):
        m = ex._EMAIL_RE.search(text)
        contact["email"] = m.group(0) if m else None


def parse_resume_text(raw_text: str, links: list | None = None) -> dict:
    """Parse once into the structured resume used by every analyzer."""
    ex = _engine()
    text = clean_text(raw_text)
    sections = detect_sections(text)
    header = sections.get("header", "")

    contact_obj = ex.extract_contact_info(header, nlp=None)
    contact = {
        "name": contact_obj.name,
        "email": contact_obj.email,
        "phone": contact_obj.phone,
        "location": contact_obj.location,
        "linkedin": contact_obj.linkedin,
        "github": contact_obj.github,
        "portfolio": contact_obj.portfolio,
    }
    contact = {k: (v.strip(" |") if isinstance(v, str) else v) for k, v in contact.items()}
    _apply_links(contact, links or [], text)

    certs = []
    for line in _bullets_or_lines(sections.get("certifications", "")):
        c = ex.extract_certifications(line.replace(" — ", " - "))
        certs.extend({"name": x.name, "issuer": x.issuer, "date": x.date} for x in c)

    internships = _parse_experience(sections.get("internships", ""), internship=True)
    experience = _parse_experience(sections.get("experience", ""))
    languages = [
        p.strip()
        for ln in _bullets_or_lines(sections.get("languages", ""))
        for p in re.split(r"[,;|]", ln)
        if p.strip()
    ]
    summary = " ".join(sections.get("summary", "").split()) or None
    objective = " ".join(sections.get("objective", "").split()) or None

    return {
        "personal_info": contact,
        "summary": summary,
        "objective": objective,
        "skills": _parse_skills(sections.get("skills", "")),
        "skills_labeled": len(re.findall(r"^[\s\-•–*]*[A-Za-z &/]{3,30}:\s*\S", sections.get("skills", ""), re.M)) >= 2,
        "education": _parse_education(sections.get("education", "")),
        "experience": experience,
        "internships": internships,
        "projects": _parse_projects(sections.get("projects", "")),
        "certifications": certs,
        "achievements": _bullets_or_lines(sections.get("achievements", "")),
        "languages": languages,
        "detected_sections": [s for s, b in sections.items() if s != "header" and b.strip()],
        "unknown_headings": unknown_headings(text),
    }
