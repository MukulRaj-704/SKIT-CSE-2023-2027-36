
import os
import re
import io
import json
import html
import hashlib
import sqlite3
from datetime import datetime

import streamlit as st

from pypdf import PdfReader
from docx import Document
from openai import OpenAI

from career_assistant.data.jobrix_data import get_software_jobs
from career_assistant.services.job_matching import JobMatchingService
from career_assistant.services.skill_gap_analyzer import SkillGapAnalyzer
from career_assistant.services.ingestion import ingest_jobrix_jobs
from career_assistant.services.chunking import chunk_documents
from career_assistant.services.vector_pipeline import VectorPipeline
from career_assistant.services.query_expander import QueryExpander
from career_assistant.services.assistant import CareerAssistant


# ============================================================
# 1. APPLICATION CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="JobRix | Career Marketplace",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

APP_NAME = "JobRix"
DATABASE = "jobrix.db"
JOB_LIMIT = 100
JOB_CACHE_SECONDS = 600
MAX_RESUME_SIZE_MB = 10


# ============================================================
# 2. DATABASE CONNECTION
# ============================================================

def get_db():

    connection = sqlite3.connect(
        DATABASE,
        check_same_thread=False
    )

    connection.row_factory = sqlite3.Row

    return connection


def initialize_database():

    with get_db() as db:

        db.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                user_id TEXT PRIMARY KEY,
                name TEXT DEFAULT '',
                email TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                location TEXT DEFAULT '',
                target_role TEXT DEFAULT '',
                experience TEXT DEFAULT 'Fresher',
                skills TEXT DEFAULT '[]',
                education TEXT DEFAULT '',
                resume_text TEXT DEFAULT '',
                resume_name TEXT DEFAULT '',
                updated_at TEXT
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS saved_jobs (
                user_id TEXT NOT NULL,
                job_id TEXT NOT NULL,
                job_data TEXT NOT NULL,
                saved_at TEXT,
                PRIMARY KEY (user_id, job_id)
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                title TEXT,
                created_at TEXT
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT
            )
        """)

        db.commit()


initialize_database()


# ============================================================
# 3. PROFILE PERSISTENCE
# ============================================================

def empty_profile():

    return {
        "name": "",
        "email": "",
        "phone": "",
        "location": "Remote",
        "target_role": "Software Developer",
        "experience": "Fresher",
        "skills": [],
        "education": "",
        "resume_text": "",
        "resume_name": ""
    }


def load_profile(user_id):

    if not user_id:
        return empty_profile()

    with get_db() as db:

        row = db.execute(
            "SELECT * FROM profiles WHERE user_id = ?",
            (user_id,)
        ).fetchone()

    if not row:
        return empty_profile()

    profile = dict(row)

    try:
        profile["skills"] = json.loads(
            profile.get("skills") or "[]"
        )
    except (ValueError, TypeError):
        profile["skills"] = []

    return profile


def save_profile(user_id, profile):

    if not user_id:
        raise ValueError("Profile ID is required.")

    with get_db() as db:

        db.execute("""
            INSERT INTO profiles (
                user_id,
                name,
                email,
                phone,
                location,
                target_role,
                experience,
                skills,
                education,
                resume_text,
                resume_name,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(user_id) DO UPDATE SET
                name = excluded.name,
                email = excluded.email,
                phone = excluded.phone,
                location = excluded.location,
                target_role = excluded.target_role,
                experience = excluded.experience,
                skills = excluded.skills,
                education = excluded.education,
                resume_text = excluded.resume_text,
                resume_name = excluded.resume_name,
                updated_at = excluded.updated_at
        """, (
            user_id,
            profile.get("name", ""),
            profile.get("email", ""),
            profile.get("phone", ""),
            profile.get("location", ""),
            profile.get("target_role", ""),
            profile.get("experience", "Fresher"),
            json.dumps(profile.get("skills", [])),
            profile.get("education", ""),
            profile.get("resume_text", ""),
            profile.get("resume_name", ""),
            datetime.now().isoformat()
        ))

        db.commit()


# ============================================================
# 4. SAVED JOBS
# ============================================================

def make_job_id(job):

    original_id = (
        job.get("id")
        or job.get("job_id")
        or job.get("url")
        or json.dumps(job, sort_keys=True, default=str)
    )

    return hashlib.sha256(
        str(original_id).encode("utf-8")
    ).hexdigest()[:32]


def save_job(user_id, job):

    identifier = make_job_id(job)

    with get_db() as db:

        db.execute("""
            INSERT OR REPLACE INTO saved_jobs (
                user_id,
                job_id,
                job_data,
                saved_at
            )
            VALUES (?, ?, ?, ?)
        """, (
            user_id,
            identifier,
            json.dumps(job, default=str),
            datetime.now().isoformat()
        ))

        db.commit()


def remove_saved_job(user_id, identifier):

    with get_db() as db:

        db.execute("""
            DELETE FROM saved_jobs
            WHERE user_id = ? AND job_id = ?
        """, (user_id, identifier))

        db.commit()


def get_saved_jobs(user_id):

    if not user_id:
        return []

    with get_db() as db:

        rows = db.execute("""
            SELECT job_id, job_data, saved_at
            FROM saved_jobs
            WHERE user_id = ?
            ORDER BY saved_at DESC
        """, (user_id,)).fetchall()

    result = []

    for row in rows:

        try:

            result.append({
                "id": row["job_id"],
                "job": json.loads(row["job_data"]),
                "saved_at": row["saved_at"]
            })

        except (ValueError, TypeError):
            continue

    return result


# ============================================================
# 5. CHAT PERSISTENCE
# ============================================================

def create_conversation(user_id, title):

    with get_db() as db:

        cursor = db.execute("""
            INSERT INTO conversations (
                user_id,
                title,
                created_at
            )
            VALUES (?, ?, ?)
        """, (
            user_id,
            title[:80],
            datetime.now().isoformat()
        ))

        db.commit()

        return cursor.lastrowid


def get_conversations(user_id):

    if not user_id:
        return []

    with get_db() as db:

        rows = db.execute("""
            SELECT conversation_id, title, created_at
            FROM conversations
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,)).fetchall()

    return [dict(row) for row in rows]


def save_message(conversation_id, role, content):

    with get_db() as db:

        db.execute("""
            INSERT INTO messages (
                conversation_id,
                role,
                content,
                created_at
            )
            VALUES (?, ?, ?, ?)
        """, (
            conversation_id,
            role,
            content,
            datetime.now().isoformat()
        ))

        db.commit()


def load_messages(conversation_id):

    with get_db() as db:

        rows = db.execute("""
            SELECT role, content
            FROM messages
            WHERE conversation_id = ?
            ORDER BY message_id ASC
        """, (conversation_id,)).fetchall()

    return [dict(row) for row in rows]


def delete_conversation(conversation_id, user_id):

    with get_db() as db:

        db.execute("""
            DELETE FROM messages
            WHERE conversation_id = ?
        """, (conversation_id,))

        db.execute("""
            DELETE FROM conversations
            WHERE conversation_id = ? AND user_id = ?
        """, (conversation_id, user_id))

        db.commit()

# ============================================================
# 6. RESUME TEXT EXTRACTION
# ============================================================

SUPPORTED_RESUME_TYPES = ["pdf", "docx"]

KNOWN_SKILLS = [
    "Python", "C", "C++", "Java", "JavaScript", "TypeScript",
    "SQL", "MySQL", "PostgreSQL", "MongoDB", "SQLite",
    "HTML", "CSS", "React", "Node.js", "Express.js",
    "Flask", "Django", "FastAPI", "Streamlit",
    "Machine Learning", "Deep Learning", "Artificial Intelligence",
    "NLP", "TensorFlow", "PyTorch", "Scikit-learn",
    "Pandas", "NumPy", "Matplotlib",
    "Data Structures", "Algorithms", "DSA",
    "Object Oriented Programming", "OOP",
    "Operating Systems", "Computer Networks", "DBMS",
    "Git", "GitHub", "Docker", "Kubernetes",
    "AWS", "Azure", "Linux", "REST API",
    "PHP", "Laravel", "Spring Boot", "Redis",
    "Power BI", "Tableau", "Excel",
    "C#", ".NET", "Go", "Rust"
]


def extract_pdf_text(file_bytes):

    reader = PdfReader(io.BytesIO(file_bytes))

    pages = []

    for page in reader.pages:

        text = page.extract_text() or ""

        if text.strip():
            pages.append(text)

    return "\n".join(pages)


def extract_docx_text(file_bytes):

    document = Document(io.BytesIO(file_bytes))

    paragraphs = [
        paragraph.text.strip()
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]

    table_text = []

    for table in document.tables:

        for row in table.rows:

            cells = [
                cell.text.strip()
                for cell in row.cells
                if cell.text.strip()
            ]

            if cells:
                table_text.append(" | ".join(cells))

    return "\n".join(paragraphs + table_text)


def extract_resume_text(uploaded_file):

    if uploaded_file is None:
        return ""

    extension = uploaded_file.name.rsplit(".", 1)[-1].lower()

    if extension not in SUPPORTED_RESUME_TYPES:
        raise ValueError("Only PDF and DOCX resumes are supported.")

    file_bytes = uploaded_file.getvalue()

    if len(file_bytes) > MAX_RESUME_SIZE_MB * 1024 * 1024:
        raise ValueError(
            f"Resume must be smaller than {MAX_RESUME_SIZE_MB} MB."
        )

    if extension == "pdf":
        text = extract_pdf_text(file_bytes)

    else:
        text = extract_docx_text(file_bytes)

    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    if not text.strip():
        raise ValueError(
            "No readable text found. The PDF may be scanned or image-based. "
            "Please upload a text-based PDF or DOCX."
        )

    return text[:30000]


# ============================================================
# 7. RESUME INFORMATION EXTRACTION
# ============================================================

def extract_skills_from_resume(resume_text):

    if not resume_text:
        return []

    text_lower = resume_text.lower()
    found = []

    for skill in KNOWN_SKILLS:

        pattern = r"(?<![a-z0-9+#.])" + re.escape(
            skill.lower()
        ) + r"(?![a-z0-9+#.])"

        if re.search(pattern, text_lower):
            found.append(skill)

    return found


def extract_email_from_resume(resume_text):

    match = re.search(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        resume_text,
        re.IGNORECASE
    )

    return match.group(0) if match else ""


def extract_phone_from_resume(resume_text):

    match = re.search(
        r"(?<!\d)(?:\+?\d[\d\s().-]{8,16}\d)(?!\d)",
        resume_text
    )

    return match.group(0).strip() if match else ""


def extract_education_from_resume(resume_text):

    lines = [
        line.strip()
        for line in resume_text.splitlines()
        if line.strip()
    ]

    keywords = [
        "education",
        "university",
        "college",
        "bachelor",
        "b.tech",
        "btech",
        "b.e.",
        "m.tech",
        "mtech",
        "degree",
        "school",
        "cbse",
        "diploma"
    ]

    selected = []

    for index, line in enumerate(lines):

        if any(word in line.lower() for word in keywords):

            selected.append(line)

            if index + 1 < len(lines):
                selected.append(lines[index + 1])

    # Keep extracted source text; do not invent qualifications.
    return "\n".join(dict.fromkeys(selected))[:2000]


def analyze_resume(resume_text):

    return {
        "skills": extract_skills_from_resume(resume_text),
        "email": extract_email_from_resume(resume_text),
        "phone": extract_phone_from_resume(resume_text),
        "education": extract_education_from_resume(resume_text)
    }


# ============================================================
# 8. JOB DATA NORMALIZATION
# ============================================================

def normalize_job(item):

    if not isinstance(item, dict):
        return {}

    nested = item.get("job")

    if isinstance(nested, dict):

        result = dict(nested)

        for key, value in item.items():

            if key != "job" and key not in result:
                result[key] = value

        return result

    return item


def job_value(job, *keys, default=None):

    if not isinstance(job, dict):
        return default

    for key in keys:

        value = job.get(key)

        if value not in (None, "", [], {}):
            return value

    metadata = job.get("metadata", {})

    if isinstance(metadata, dict):

        for key in keys:

            value = metadata.get(key)

            if value not in (None, "", [], {}):
                return value

    return default


def job_tags(job):

    tags = job_value(
        job,
        "tags",
        "skills",
        "technical_skills",
        default=[]
    )

    if isinstance(tags, str):

        tags = re.split(r"[,|]", tags)

    if not isinstance(tags, (list, tuple)):
        tags = []

    return [
        str(tag).strip()
        for tag in tags
        if str(tag).strip()
    ][:12]


def job_search_text(job):

    values = [
        job_value(job, "title", "job_title", default=""),
        job_value(job, "company", "company_name", default=""),
        job_value(
            job,
            "location",
            "candidate_required_location",
            default=""
        ),
        job_value(job, "category", default=""),
        job_value(job, "description", "job_description", default=""),
        " ".join(job_tags(job))
    ]

    return " ".join(str(value) for value in values).lower()


# ============================================================
# 9. LIVE JOB FEED
# ============================================================

@st.cache_data(
    ttl=JOB_CACHE_SECONDS,
    show_spinner=False
)
def fetch_live_jobs():

    raw_jobs = get_software_jobs(limit=JOB_LIMIT) or []

    return [
        normalize_job(job)
        for job in raw_jobs
        if isinstance(job, dict)
    ]


def refresh_live_jobs():

    fetch_live_jobs.clear()
    load_kai_backend.clear()


# ============================================================
# 10. KAI KNOWLEDGE BASE
# ============================================================

@st.cache_resource(show_spinner=False)
def load_kai_backend():

    jobs = fetch_live_jobs()

    documents = ingest_jobrix_jobs(jobs)
    chunks = chunk_documents(documents)

    pipeline = VectorPipeline()

    if chunks:
        pipeline.add_documents(chunks)

    return (
        pipeline,
        QueryExpander(),
        CareerAssistant()
    )


# ============================================================
# 11. BUILD PERSONALIZED USER CONTEXT
# ============================================================

def build_user_context(profile, jobs, saved_jobs):

    resume_text = profile.get("resume_text", "")

    return {
        "profile": {
            "name": profile.get("name", ""),
            "skills": profile.get("skills", []),
            "target_role": profile.get("target_role", ""),
            "experience": profile.get("experience", ""),
            "location": profile.get("location", ""),
            "education": profile.get("education", "")
        },

        "resume": {
            "filename": profile.get("resume_name", ""),
            "extracted_text": resume_text[:18000]
        },

        "available_job_count": len(jobs),

        "saved_job_count": len(saved_jobs),

        "saved_jobs": [
            {
                "title": job_value(
                    item["job"],
                    "title",
                    default=""
                ),
                "company": job_value(
                    item["job"],
                    "company",
                    default=""
                )
            }
            for item in saved_jobs[:20]
        ]
    }

# ============================================================
# 12. PROFESSIONAL LIGHT UI
# ============================================================

st.markdown("""
<style>

@import url(
'https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Manrope:wght@500;600;700;800&display=swap'
);

:root {
    --ink: #17233b;
    --muted: #69778f;
    --blue: #315cf5;
    --blue-dark: #2146d8;
    --line: #e7ebf3;
    --surface: #ffffff;
    --canvas: #f5f7fb;
}

.stApp,
[data-testid="stAppViewContainer"] {
    background: #f5f7fb !important;
    color: #17233b !important;
    font-family: 'DM Sans', sans-serif !important;
}

[data-testid="stHeader"] {
    background: transparent !important;
}

.block-container {
    max-width: 1480px;
    padding: 1.5rem 2.5rem 3rem;
}

/* MAIN TEXT */

h1, h2, h3, h4,
p, li, label,
[data-testid="stMarkdownContainer"] {
    color: #17233b;
    font-family: 'DM Sans', sans-serif;
}

h1, h2, h3 {
    font-family: 'Manrope', sans-serif;
    letter-spacing: -0.5px;
    font-weight: 800;
}

[data-testid="stCaptionContainer"] p {
    color: #69778f !important;
}

/* SIDEBAR */

[data-testid="stSidebar"] {
    background: #111d35 !important;
    border-right: 1px solid #243452;
}

[data-testid="stSidebar"] * {
    color: #eaf0fb;
}

[data-testid="stSidebar"] label {
    color: #eaf0fb !important;
}

[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    color: #aab8ce !important;
}

[data-testid="stSidebar"] input,
[data-testid="stSidebar"] textarea {
    background: #1c2a45 !important;
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    border: 1px solid #354663 !important;
    border-radius: 10px !important;
}

[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background: #1c2a45 !important;
    border-color: #354663 !important;
}

.brand {
    color: white !important;
    font-family: 'Manrope', sans-serif;
    font-size: 30px;
    font-weight: 800;
    letter-spacing: -1px;
}

.brand-blue {
    color: #77a1ff !important;
}

.brand-caption {
    color: #9eacc4 !important;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 2px;
}

/* HERO */

.hero-box {
    background: linear-gradient(
        115deg,
        #152441 0%,
        #2446a5 58%,
        #315cf5 100%
    );
    border-radius: 22px;
    padding: 38px;
    margin-bottom: 25px;
    box-shadow: 0 14px 35px rgba(36,70,165,.15);
}

.hero-box * {
    color: #ffffff !important;
}

.hero-kicker {
    color: #c9d7ff !important;
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 2px;
    margin-bottom: 12px;
}

.hero-box h1 {
    color: #ffffff !important;
    font-family: 'Manrope', sans-serif;
    font-size: clamp(28px, 3vw, 42px);
    font-weight: 800;
    line-height: 1.2;
    margin: 0;
}

.hero-box p {
    color: #e0e8ff !important;
    font-size: 15px;
    line-height: 1.7;
    margin-top: 12px;
    max-width: 720px;
}

/* TOPLINE */

.topline {
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: #69778f;
    font-size: 13px;
    margin-bottom: 20px;
}

.online-dot {
    color: #16845b;
    font-weight: 800;
}

/* METRICS */

[data-testid="stMetric"] {
    background: #ffffff !important;
    border: 1px solid #e7ebf3 !important;
    border-radius: 15px !important;
    padding: 18px !important;
    box-shadow: 0 4px 16px rgba(23,35,59,.035);
}

[data-testid="stMetricLabel"] {
    color: #69778f !important;
}

[data-testid="stMetricValue"] {
    color: #17233b !important;
    font-weight: 800 !important;
}

/* CONTAINERS */

div[data-testid="stVerticalBlockBorderWrapper"] {
    background: #ffffff !important;
    border: 1px solid #e7ebf3 !important;
    border-radius: 15px !important;
}

/* INPUTS */

.stTextInput input,
.stTextArea textarea,
.stSelectbox [data-baseweb="select"] > div,
.stMultiSelect [data-baseweb="select"] > div {
    background: #ffffff !important;
    background-color: #ffffff !important;
    color: #17233b !important;
    -webkit-text-fill-color: #17233b !important;
    border: 1px solid #dce3ef !important;
    border-radius: 10px !important;
    box-shadow: none !important;
}

.stTextInput input::placeholder,
.stTextArea textarea::placeholder {
    color: #94a3b8 !important;
    -webkit-text-fill-color: #94a3b8 !important;
    opacity: 1 !important;
}

.stTextInput input:focus,
.stTextArea textarea:focus {
    border-color: #315cf5 !important;
    box-shadow: 0 0 0 2px rgba(49,92,245,.10) !important;
}

.stTextInput label,
.stTextArea label,
.stSelectbox label,
.stFileUploader label {
    color: #40506a !important;
    font-weight: 650 !important;
}

/* BUTTONS */

.stButton > button,
.stButton > button:focus,
.stButton > button:active {
    background: #ffffff !important;
    background-color: #ffffff !important;
    color: #315cf5 !important;
    border: 1px solid #dce3ef !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    min-height: 43px;
    box-shadow: none !important;
}

.stButton > button:hover {
    background: #eef3ff !important;
    color: #2146d8 !important;
    border-color: #315cf5 !important;
}

.stButton > button[kind="primary"],
.stButton > button[kind="primary"]:focus,
.stButton > button[kind="primary"]:active {
    background: #315cf5 !important;
    background-color: #315cf5 !important;
    color: #ffffff !important;
    border-color: #315cf5 !important;
}

.stButton > button[kind="primary"]:hover {
    background: #2146d8 !important;
    color: #ffffff !important;
}

.stLinkButton > a {
    background: #315cf5 !important;
    color: #ffffff !important;
    border: 1px solid #315cf5 !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
}

.stLinkButton > a:hover {
    background: #2146d8 !important;
}

/* JOB TAGS */

.job-company {
    color: #315cf5 !important;
    font-size: 13px;
    font-weight: 800;
}

.job-heading {
    color: #17233b !important;
    font-size: 19px;
    font-weight: 800;
    margin: 5px 0;
}

.job-meta {
    color: #69778f !important;
    font-size: 12px;
    line-height: 1.8;
}

.tag {
    display: inline-block;
    background: #eef3ff;
    color: #3155bd !important;
    border-radius: 20px;
    padding: 5px 10px;
    margin: 3px;
    font-size: 11px;
    font-weight: 700;
}

.match-badge {
    background: #e5f7ef;
    color: #08734c !important;
    border-radius: 20px;
    padding: 5px 10px;
    font-size: 10px;
    font-weight: 800;
}

/* CHAT */

[data-testid="stChatMessage"] {
    background: #ffffff !important;
    background-color: #ffffff !important;
    color: #17233b !important;
    border: 1px solid #e7ebf3 !important;
    border-radius: 15px !important;
    padding: 16px !important;
    box-shadow: 0 4px 14px rgba(23,35,59,.04) !important;
}

[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] li,
[data-testid="stChatMessage"] h1,
[data-testid="stChatMessage"] h2,
[data-testid="stChatMessage"] h3,
[data-testid="stChatMessage"] strong,
[data-testid="stChatMessage"] code {
    color: #17233b !important;
}

[data-testid="stChatInput"],
[data-testid="stChatInput"] > div,
[data-testid="stBottom"],
[data-testid="stBottom"] > div {
    background: #f5f7fb !important;
}

[data-testid="stChatInput"] {
    background: #ffffff !important;
    border: 1.5px solid #dce3ef !important;
    border-radius: 14px !important;
    box-shadow: none !important;
}

[data-testid="stChatInput"] textarea {
    background: #ffffff !important;
    color: #17233b !important;
    -webkit-text-fill-color: #17233b !important;
    caret-color: #315cf5 !important;
}

[data-testid="stChatInput"] textarea::placeholder {
    color: #94a3b8 !important;
    -webkit-text-fill-color: #94a3b8 !important;
}

[data-testid="stChatInput"] button {
    background: #315cf5 !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: 10px !important;
}

[data-testid="stChatInput"] button:hover {
    background: #2146d8 !important;
}

[data-testid="stChatInput"]:focus-within {
    border-color: #315cf5 !important;
    box-shadow: 0 0 0 3px rgba(49,92,245,.10) !important;
}

/* FILE UPLOADER */

[data-testid="stFileUploader"] {
    background: #ffffff !important;
    border: 1px dashed #b9c6da !important;
    border-radius: 14px !important;
    padding: 12px !important;
}

[data-testid="stFileUploader"] section {
    background: #ffffff !important;
}

/* EXPANDERS */

[data-testid="stExpander"] {
    background: #ffffff !important;
    border: 1px solid #e7ebf3 !important;
    border-radius: 12px !important;
}

[data-testid="stExpander"] summary {
    color: #17233b !important;
}

/* EMPTY STATE */

.empty-state {
    background: #ffffff;
    border: 1px dashed #cbd5e1;
    border-radius: 15px;
    padding: 28px;
    text-align: center;
    color: #69778f !important;
}

/* RESPONSIVE */

@media(max-width: 900px) {
    .block-container {
        padding: 1rem;
    }

    .hero-box {
        padding: 24px;
    }
}

footer {
    visibility: hidden;
}


/* JOBRIX VISIBILITY FIX */

/* Sidebar resume review: dark text on white content */
[data-testid="stSidebar"] [data-testid="stExpanderDetails"] {
    background: #ffffff !important;
    color: #1e293b !important;
}

[data-testid="stSidebar"] [data-testid="stExpanderDetails"] p,
[data-testid="stSidebar"] [data-testid="stExpanderDetails"] span,
[data-testid="stSidebar"] [data-testid="stExpanderDetails"] div,
[data-testid="stSidebar"] [data-testid="stExpanderDetails"] label,
[data-testid="stSidebar"] [data-testid="stExpanderDetails"] strong,
[data-testid="stSidebar"] [data-testid="stExpanderDetails"] li {
    color: #1e293b !important;
}

/* Resume uploader text */
[data-testid="stSidebar"] [data-testid="stFileUploader"] {
    color: #1e293b !important;
}

[data-testid="stSidebar"] [data-testid="stFileUploader"] section,
[data-testid="stSidebar"] [data-testid="stFileUploader"] small,
[data-testid="stSidebar"] [data-testid="stFileUploader"] span {
    color: #334155 !important;
}

/* KAI user and assistant message text */
[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] li,
[data-testid="stChatMessage"] span,
[data-testid="stChatMessage"] strong,
[data-testid="stChatMessage"] h1,
[data-testid="stChatMessage"] h2,
[data-testid="stChatMessage"] h3 {
    color: #1e293b !important;
}

/* KAI message container */
[data-testid="stChatMessage"] {
    color: #1e293b !important;
}

/* Loading spinner visibility */
[data-testid="stSpinner"] {
    visibility: visible !important;
    opacity: 1 !important;
    color: #2563eb !important;
}

[data-testid="stSpinner"] svg {
    visibility: visible !important;
    opacity: 1 !important;
    stroke: #2563eb !important;
}

</style>
""", unsafe_allow_html=True)


# ============================================================
# 13. SESSION STATE
# ============================================================

DEFAULT_STATE = {
    "user_id": "",
    "page": "Home",
    "chat_history": [],
    "conversation_id": None,
    "pending_prompt": None,
    "job_results": None,
    "skill_report": None,
    "resume_analysis": None,
    "resume_upload_key": None,
    "search_query": "",
    "profile_loaded_for": None
}

for key, value in DEFAULT_STATE.items():

    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# 14. ACCOUNT IDENTIFIER
# ============================================================

st.sidebar.markdown(
    '<div class="brand">🚀 Job<span class="brand-blue">Rix</span></div>'
    '<div class="brand-caption">CAREER DISCOVERY, REIMAGINED</div>',
    unsafe_allow_html=True
)

st.sidebar.divider()

st.sidebar.markdown("#### YOUR PROFILE")

account_id = st.sidebar.text_input(
    "Email / Profile ID",
    value=st.session_state.user_id,
    placeholder="Enter your email address",
    key="account_identifier"
).strip().lower()

if account_id != st.session_state.user_id:

    st.session_state.user_id = account_id
    st.session_state.profile_loaded_for = account_id
    st.session_state.chat_history = []
    st.session_state.conversation_id = None
    st.session_state.job_results = None
    st.session_state.skill_report = None
    st.session_state.resume_analysis = None

if account_id:

    profile = load_profile(account_id)

else:

    profile = empty_profile()


# ============================================================
# 15. RESUME UPLOAD AND PROFILE EDITOR
# ============================================================

st.sidebar.divider()

st.sidebar.markdown("#### RESUME & CAREER DETAILS")

uploaded_resume = st.sidebar.file_uploader(
    "Upload your resume",
    type=["pdf", "docx"],
    help="Maximum 10 MB. Text-based PDF and DOCX supported.",
    key="resume_uploader"
)

if uploaded_resume is not None:

    upload_signature = hashlib.sha256(
        uploaded_resume.getvalue()
    ).hexdigest()

    if st.session_state.resume_upload_key != upload_signature:

        try:

            extracted_text = extract_resume_text(
                uploaded_resume
            )

            analysis = analyze_resume(
                extracted_text
            )

            st.session_state.resume_analysis = {
                "text": extracted_text,
                "name": uploaded_resume.name,
                **analysis
            }

            st.session_state.resume_upload_key = upload_signature

            st.sidebar.success(
                "Resume read successfully. Review extracted details below."
            )

        except Exception as error:

            st.session_state.resume_analysis = None

            st.sidebar.error(
                f"Resume processing failed: {error}"
            )


resume_analysis = st.session_state.resume_analysis

if resume_analysis:

    with st.sidebar.expander(
        "Review extracted resume details",
        expanded=True
    ):

        st.write(
            f"**File:** {resume_analysis['name']}"
        )

        st.write(
            f"**Email:** {resume_analysis['email'] or 'Not found'}"
        )

        st.write(
            f"**Phone:** {resume_analysis['phone'] or 'Not found'}"
        )

        st.write("**Detected skills:**")

        if resume_analysis["skills"]:

            st.write(
                ", ".join(resume_analysis["skills"])
            )

        else:

            st.caption(
                "No recognized skills found automatically."
            )

        if resume_analysis["education"]:

            st.write("**Education text:**")
            st.write(resume_analysis["education"])

        if st.button(
            "Use extracted resume details",
            key="apply_resume_details",
            type="primary",
            use_container_width=True
        ):

            profile["resume_text"] = resume_analysis["text"]
            profile["resume_name"] = resume_analysis["name"]

            if resume_analysis["email"]:
                profile["email"] = resume_analysis["email"]

            if resume_analysis["phone"]:
                profile["phone"] = resume_analysis["phone"]

            if resume_analysis["education"]:
                profile["education"] = resume_analysis["education"]

            existing = {
                skill.lower()
                for skill in profile["skills"]
            }

            for skill in resume_analysis["skills"]:

                if skill.lower() not in existing:
                    profile["skills"].append(skill)

            if account_id:

                save_profile(account_id, profile)

                st.sidebar.success(
                    "Resume details added to your profile."
                )

                st.rerun()

            else:

                st.sidebar.warning(
                    "Enter your Email / Profile ID before saving."
                )


with st.sidebar.form("career_profile_form"):

    profile_name = st.text_input(
        "Full name",
        value=profile["name"]
    )

    profile_email = st.text_input(
        "Email",
        value=profile["email"]
    )

    profile_phone = st.text_input(
        "Phone",
        value=profile["phone"]
    )

    profile_skills = st.text_area(
        "Skills (comma separated)",
        value=", ".join(profile["skills"]),
        height=100
    )

    profile_role = st.text_input(
        "Target role",
        value=profile["target_role"]
    )

    experience_options = [
        "Fresher",
        "0-1 years",
        "1-2 years",
        "2-3 years",
        "3+ years"
    ]

    current_experience = profile["experience"]

    if current_experience not in experience_options:
        current_experience = "Fresher"

    profile_experience = st.selectbox(
        "Experience",
        experience_options,
        index=experience_options.index(current_experience)
    )

    profile_location = st.text_input(
        "Preferred location",
        value=profile["location"]
    )

    profile_education = st.text_area(
        "Education",
        value=profile["education"],
        height=70
    )

    save_profile_button = st.form_submit_button(
        "Save career profile",
        type="primary",
        use_container_width=True
    )

if save_profile_button:

    if not account_id:

        st.sidebar.error(
            "Enter your Email / Profile ID first."
        )

    elif not profile_name.strip():

        st.sidebar.error(
            "Name is required."
        )

    else:

        updated_profile = {
            "name": profile_name.strip(),
            "email": profile_email.strip(),
            "phone": profile_phone.strip(),
            "skills": [
                item.strip()
                for item in profile_skills.split(",")
                if item.strip()
            ],
            "target_role": profile_role.strip(),
            "experience": profile_experience,
            "location": profile_location.strip(),
            "education": profile_education.strip(),
            "resume_text": profile.get("resume_text", ""),
            "resume_name": profile.get("resume_name", "")
        }

        save_profile(account_id, updated_profile)

        st.sidebar.success(
            "Career profile saved permanently."
        )

        st.rerun()



# ============================================================
# 16. ACTIVE PROFILE + AUTOMATIC RESUME CONTEXT
# ============================================================

if account_id:

    profile = load_profile(account_id)

else:

    profile = empty_profile()


# Attach uploaded resume immediately.
# Do not require the user to click another but
resume_analysis = st.session_state.get("resume_analysis")

if resume_analysis:

    profile["resume_text"] = resume_analysis.get(
        "text",
        ""
    )

    profile["resume_name"] = resume_analysis.get(
        "name",
        ""
    )

    if resume_analysis.get("email"):
        profile["email"] = resume_analysis["email"]

    if resume_analysis.get("phone"):
        profile["phone"] = resume_analysis["phone"]

    if resume_analysis.get("education"):
        profile["education"] = resume_analysis["education"]

    # Merge extracted skills without duplicates.
    existing_skills = {
        skill.lower()
        for skill in profile.get("skills", [])
    }

    for skill in resume_analysis.get("skills", []):

        if skill.lower() not in existing_skills:

            profile.setdefault("skills", []).append(skill)

            existing_skills.add(skill.lower())


# Build context after attaching resume.
profile_context = {
    "name": profile["name"],
    "skills": profile["skills"],
    "target_role": profile["target_role"],
    "experience": profile["experience"],
    "location": profile["location"],
    "education": profile["education"]
}

# ============================================================
# 17. SIDEBAR NAVIGATION
# ============================================================

st.sidebar.divider()

navigation_pages = [
    "Home",
    "Explore Jobs",
    "AI Recommendations",
    "Saved Jobs",
    "My Profile",
    "Skill Insights",
    "Chat with KAI"
]

if st.session_state.page not in navigation_pages:
    st.session_state.page = "Home"

selected_page = st.sidebar.radio(
    "NAVIGATION",
    navigation_pages,
    index=navigation_pages.index(st.session_state.page),
    key="main_navigation"
)

st.session_state.page = selected_page

st.sidebar.divider()

st.sidebar.caption(
    "JobRix | Powered by Gemini AI"
)

# ============================================================
# 18. LOAD JOBS AND KAI SERVICES
# ============================================================

try:

    with st.spinner("Loading live opportunities and KAI..."):

        jobs = fetch_live_jobs()

        pipeline, expander, assistant = load_kai_backend()

except Exception as error:

    st.error(f"Unable to initialize JobRix: {error}")

    st.info(
        "Check your internet connection, API key and backend configuration."
    )

    st.stop()


# ============================================================
# 19. COMMON HELPERS
# ============================================================

def get_saved_job_ids():

    if not account_id:
        return set()

    return {
        item["id"]
        for item in get_saved_jobs(account_id)
    }


def render_tags(tags):

    if not tags:
        return

    st.markdown(
        "".join(
            f'<span class="tag">{html.escape(str(tag))}</span>'
            for tag in tags
        ),
        unsafe_allow_html=True
    )


def render_job_card(job, index=0, show_match=False):

    title = str(
        job_value(
            job,
            "title",
            "job_title",
            default="Untitled opportunity"
        )
    )

    company = str(
        job_value(
            job,
            "company",
            "company_name",
            default="Company not listed"
        )
    )

    location = str(
        job_value(
            job,
            "location",
            "candidate_required_location",
            default="Location not specified"
        )
    )

    job_type = str(
        job_value(
            job,
            "job_type",
            "employment_type",
            "type",
            default="Not specified"
        )
    )

    salary = str(
        job_value(
            job,
            "salary",
            "salary_range",
            default="Not disclosed"
        )
    )

    url = job_value(
        job,
        "url",
        "job_url",
        "apply_url"
    )

    identifier = make_job_id(job)

    with st.container(border=True):

        left, right = st.columns([5, 1])

        with left:

            st.markdown(
                f'<div class="job-company">{html.escape(company)}</div>',
                unsafe_allow_html=True
            )

            st.markdown(
                f'<div class="job-heading">{html.escape(title)}</div>',
                unsafe_allow_html=True
            )

        with right:

            if show_match:

                st.markdown(
                    '<span class="match-badge">AI MATCH</span>',
                    unsafe_allow_html=True
                )

        st.markdown(
            f'<div class="job-meta">'
            f'📍 {html.escape(location)} &nbsp; | &nbsp; '
            f'💼 {html.escape(job_type)} &nbsp; | &nbsp; '
            f'💰 {html.escape(salary)}'
            f'</div>',
            unsafe_allow_html=True
        )

        render_tags(job_tags(job))

        col1, col2 = st.columns(2)

        with col1:

            if url:

                st.link_button(
                    "View job / Apply ↗",
                    str(url),
                    use_container_width=True
                )

            else:

                st.button(
                    "Application link unavailable",
                    disabled=True,
                    key=f"missing-url-{identifier}-{index}",
                    use_container_width=True
                )

        with col2:

            if not account_id:

                st.button(
                    "Sign in to save",
                    disabled=True,
                    key=f"no-account-{identifier}-{index}",
                    use_container_width=True
                )

            else:

                saved = identifier in get_saved_job_ids()

                if st.button(
                    "♥ Saved" if saved else "♡ Save job",
                    key=f"save-job-{identifier}-{index}",
                    use_container_width=True
                ):

                    if saved:

                        remove_saved_job(
                            account_id,
                            identifier
                        )

                    else:

                        save_job(
                            account_id,
                            job
                        )

                    st.rerun()

        with st.expander("Job description and details"):

            description = job_value(
                job,
                "description",
                "job_description",
                default=""
            )

            if description:

                st.markdown(str(description))

            else:

                st.caption(
                    "The job source did not provide a description."
                )

            st.caption(
                "Source: " + str(
                    job_value(job, "source", default="Connected job feed")
                )
            )


def render_page_header(title, subtitle=None):

    st.title(title)

    if subtitle:
        st.caption(subtitle)


# ============================================================
# 20. TOP BAR
# ============================================================

st.markdown("""
<div class="topline">
    <span>JOBRIX / CAREER MARKETPLACE</span>
    <span><span class="online-dot">●</span> LIVE WORKSPACE</span>
</div>
""", unsafe_allow_html=True)


# ============================================================
# 21. HOME DASHBOARD
# ============================================================

if selected_page == "Home":

    st.markdown("""
    <div class="hero-box">
        <div class="hero-kicker">
            YOUR NEXT CHAPTER STARTS HERE
        </div>
        <h1>Find a job that fits your ambition.</h1>
        <p>
            Explore opportunities, discover your strengths
            and get personalized career guidance from KAI.
        </p>
    </div>
    """, unsafe_allow_html=True)

    search_col, button_col = st.columns([5, 1])

    with search_col:

        home_search = st.text_input(
            "Search opportunities",
            placeholder="Job title, company, skill or keyword...",
            label_visibility="collapsed",
            key="home_search"
        )

    with button_col:

        if st.button(
            "Search jobs",
            type="primary",
            use_container_width=True
        ):

            st.session_state.search_query = home_search
            st.session_state.page = "Explore Jobs"
            st.rerun()

    saved_count = len(
        get_saved_jobs(account_id)
    ) if account_id else 0

    m1, m2, m3, m4 = st.columns(4)

    m1.metric("Live opportunities", len(jobs))
    m2.metric("Your skills", len(profile["skills"]))
    m3.metric("Saved jobs", saved_count)
    m4.metric("KAI knowledge chunks", pipeline.count())

    refresh_col, refresh_note = st.columns([1, 4])

    with refresh_col:

        if st.button(
            "↻ Refresh jobs",
            use_container_width=True
        ):

            with st.spinner("Fetching latest jobs..."):

                refresh_live_jobs()

            st.rerun()

    with refresh_note:

        st.caption(
            "Job feed refreshes automatically every 10 minutes."
        )

    st.markdown(
        '<div class="section-title">Explore by interest</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="section-subtitle">'
        'Choose an area and discover relevant opportunities.'
        '</div>',
        unsafe_allow_html=True
    )

    interest_categories = [
        ("💻", "Software Development", "software"),
        ("🧠", "AI & Machine Learning", "machine learning"),
        ("📊", "Data & Analytics", "data"),
        ("⚙️", "Backend Engineering", "backend"),
        ("🎨", "Frontend Engineering", "frontend"),
        ("🌍", "Remote Opportunities", "remote")
    ]

    category_columns = st.columns(3)

    for index, (icon, label, keyword) in enumerate(interest_categories):

        with category_columns[index % 3]:

            with st.container(border=True):

                st.markdown(f"### {icon} {label}")

                if st.button(
                    "Explore opportunities →",
                    key=f"interest-{index}",
                    use_container_width=True
                ):

                    st.session_state.search_query = keyword
                    st.session_state.page = "Explore Jobs"
                    st.rerun()

    st.markdown(
        '<div class="section-title">Latest opportunities</div>',
        unsafe_allow_html=True
    )

    if jobs:

        for index, job in enumerate(jobs[:5]):

            render_job_card(
                job,
                index
            )

    else:

        st.info(
            "No jobs were returned by the connected job source."
        )


# ============================================================
# 22. EXPLORE JOBS
# ============================================================

elif selected_page == "Explore Jobs":

    render_page_header(
        "Explore opportunities",
        "Search, filter and discover jobs from the connected live feed."
    )

    search_query = st.text_input(
        "Search by title, company, skills or keyword",
        value=st.session_state.search_query,
        placeholder="Python Developer, React, SQL..."
    )

    st.session_state.search_query = search_query

    categories = sorted({
        str(job_value(job, "category", default=""))
        for job in jobs
        if job_value(job, "category", default="")
    })

    locations = sorted({
        str(job_value(
            job,
            "location",
            "candidate_required_location",
            default=""
        ))
        for job in jobs
        if job_value(
            job,
            "location",
            "candidate_required_location",
            default=""
        )
    })

    job_types = sorted({
        str(job_value(
            job,
            "job_type",
            "employment_type",
            "type",
            default=""
        ))
        for job in jobs
        if job_value(
            job,
            "job_type",
            "employment_type",
            "type",
            default=""
        )
    })

    f1, f2, f3 = st.columns(3)

    with f1:

        category_filter = st.selectbox(
            "Category",
            ["All categories"] + categories
        )

    with f2:

        location_filter = st.selectbox(
            "Location",
            ["All locations"] + locations
        )

    with f3:

        type_filter = st.selectbox(
            "Employment type",
            ["All types"] + job_types
        )

    sort_option = st.selectbox(
        "Sort jobs",
        [
            "Newest first",
            "Company A-Z",
            "Job title A-Z"
        ]
    )

    filtered_jobs = []

    for job in jobs:

        if (
            search_query
            and search_query.lower() not in job_search_text(job)
        ):
            continue

        category = str(
            job_value(job, "category", default="")
        )

        location = str(
            job_value(
                job,
                "location",
                "candidate_required_location",
                default=""
            )
        )

        job_type = str(
            job_value(
                job,
                "job_type",
                "employment_type",
                "type",
                default=""
            )
        )

        if (
            category_filter != "All categories"
            and category != category_filter
        ):
            continue

        if (
            location_filter != "All locations"
            and location != location_filter
        ):
            continue

        if (
            type_filter != "All types"
            and job_type != type_filter
        ):
            continue

        filtered_jobs.append(job)

    if sort_option == "Company A-Z":

        filtered_jobs.sort(
            key=lambda item: str(
                job_value(item, "company", default="")
            ).lower()
        )

    elif sort_option == "Job title A-Z":

        filtered_jobs.sort(
            key=lambda item: str(
                job_value(item, "title", default="")
            ).lower()
        )

    else:

        filtered_jobs.sort(
            key=lambda item: str(
                job_value(item, "publication_date", default="")
            ),
            reverse=True
        )

    st.markdown(
        f"### {len(filtered_jobs)} opportunities found"
    )

    if filtered_jobs:

        for index, job in enumerate(filtered_jobs):

            render_job_card(
                job,
                index
            )

    else:

        st.markdown(
            '<div class="empty-state">'
            'No jobs match your search. Try changing your filters.'
            '</div>',
            unsafe_allow_html=True
        )


# ============================================================
# 23. AI JOB RECOMMENDATIONS
# ============================================================

elif selected_page == "AI Recommendations":

    render_page_header(
        "Recommended for you",
        "Find jobs based on your skills, experience and career goals."
    )

    st.info(
        f"Target role: {profile['target_role']}  |  "
        f"Experience: {profile['experience']}  |  "
        f"Location: {profile['location']}"
    )

    st.markdown(
        "**Your skills:** " + (
            ", ".join(profile["skills"])
            if profile["skills"]
            else "No skills added yet"
        )
    )

    if st.button(
        "✨ Find my matching jobs",
        type="primary"
    ):

        if not profile["skills"]:

            st.warning(
                "Add your skills in your profile before matching jobs."
            )

        else:

            with st.spinner(
                "Analysing your profile and matching opportunities..."
            ):

                try:

                    matcher = JobMatchingService()

                    st.session_state.job_results = matcher.match(
                        profile_context,
                        jobs,
                        limit=20
                    )

                    st.session_state.match_error = None

                except Exception as error:

                    st.session_state.job_results = None
                    st.session_state.match_error = str(error)

    if st.session_state.get("match_error"):

        st.error(
            st.session_state.match_error
        )

    results = st.session_state.job_results

    if results is not None:

        if results:

            st.markdown(
                f"### {len(results)} matching opportunities"
            )

            for index, item in enumerate(results):

                normalized = normalize_job(item)

                render_job_card(
                    normalized,
                    index + 1000,
                    show_match=True
                )

        else:

            st.warning(
                "No matching jobs were returned. "
                "Try updating your skills or target role."
            )

    else:

        st.markdown(
            '<div class="empty-state">'
            'Your personalized recommendations will appear here.'
            '</div>',
            unsafe_allow_html=True
        )


# ============================================================
# 24. SAVED JOBS
# ============================================================

elif selected_page == "Saved Jobs":

    render_page_header(
        "Saved jobs",
        "Your personal shortlist of career opportunities."
    )

    if not account_id:

        st.warning(
            "Enter your email / Profile ID in the sidebar "
            "to access saved jobs."
        )

    else:

        saved_jobs = get_saved_jobs(account_id)

        st.markdown(
            f"### {len(saved_jobs)} saved opportunities"
        )

        if saved_jobs:

            for index, saved_item in enumerate(saved_jobs):

                render_job_card(
                    saved_item["job"],
                    index
                )

                if st.button(
                    "Remove from saved jobs",
                    key=f"remove-saved-{saved_item['id']}"
                ):

                    remove_saved_job(
                        account_id,
                        saved_item["id"]
                    )

                    st.rerun()

        else:

            st.markdown(
                '<div class="empty-state">'
                'No saved jobs yet. Explore opportunities and save jobs '
                'you want to revisit.'
                '</div>',
                unsafe_allow_html=True
            )

# ============================================================
# 25. MY PROFILE
# ============================================================

elif selected_page == "My Profile":

    render_page_header(
        "My career profile",
        "Your professional identity and career information."
    )

    if not account_id:

        st.warning(
            "Enter your Email / Profile ID in the sidebar first."
        )

    else:

        current_profile = load_profile(account_id)

        st.markdown(
            f"## {current_profile['name'] or 'Your profile'}"
        )

        st.caption(
            current_profile["email"] or "Email not added"
        )

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Skills",
            len(current_profile["skills"])
        )

        c2.metric(
            "Experience",
            current_profile["experience"]
        )

        c3.metric(
            "Resume",
            "Uploaded" if current_profile["resume_text"] else "Not uploaded"
        )

        st.divider()

        left, right = st.columns(2)

        with left:

            st.markdown("### Personal details")

            st.write(
                f"**Name:** {current_profile['name'] or 'Not added'}"
            )

            st.write(
                f"**Email:** {current_profile['email'] or 'Not added'}"
            )

            st.write(
                f"**Phone:** {current_profile['phone'] or 'Not added'}"
            )

            st.write(
                f"**Location:** {current_profile['location']}"
            )

        with right:

            st.markdown("### Career preferences")

            st.write(
                f"**Target role:** {current_profile['target_role']}"
            )

            st.write(
                f"**Experience:** {current_profile['experience']}"
            )

            st.write(
                f"**Education:** {current_profile['education'] or 'Not added'}"
            )

        st.divider()

        st.markdown("### Technical skills")

        if current_profile["skills"]:

            render_tags(current_profile["skills"])

        else:

            st.info(
                "Add skills through the profile editor in the sidebar."
            )

        st.divider()

        st.markdown("### Resume")

        if current_profile["resume_text"]:

            st.success(
                f"Resume available: {current_profile['resume_name']}"
            )

            with st.expander("Preview extracted resume text"):

                st.text(
                    current_profile["resume_text"][:12000]
                )

        else:

            st.info(
                "Upload your PDF or DOCX resume through the sidebar."
            )

        st.caption(
            "To edit your profile, use the Career Profile form in the sidebar."
        )


# ============================================================
# 26. SKILL INSIGHTS
# ============================================================

elif selected_page == "Skill Insights":

    render_page_header(
        "Skill gap analysis",
        "Understand your strengths and identify skills to develop."
    )

    if not profile["skills"]:

        st.warning(
            "Add your skills in the sidebar before running the analysis."
        )

    else:

        st.markdown("### Your current skill set")

        render_tags(profile["skills"])

        if profile.get("resume_name"):

            st.caption(
                f"Resume context: {profile['resume_name']}"
            )

        if st.button(
            "Analyse my skills",
            type="primary"
        ):

            with st.spinner(
                "Analysing your skills against available opportunities..."
            ):

                try:

                    analyzer = SkillGapAnalyzer()

                    report = analyzer.analyze(
                        profile_context,
                        jobs=jobs
                    )

                    st.session_state.skill_report = report
                    st.session_state.skill_error = None

                except Exception as error:

                    st.session_state.skill_report = None
                    st.session_state.skill_error = str(error)

        if st.session_state.get("skill_error"):

            st.error(
                st.session_state.skill_error
            )

        report = st.session_state.skill_report

        if report is not None:

            st.markdown("### Your analysis")

            if isinstance(report, dict):

                # Display common summary values when supplied
                summary_fields = [
                    ("coverage", "Skill coverage"),
                    ("coverage_percentage", "Coverage percentage"),
                    ("matched_skills", "Matched skills"),
                    ("missing_skills", "Missing skills")
                ]

                for key, label in summary_fields:

                    if key in report:

                        value = report[key]

                        if isinstance(value, (int, float)):

                            st.metric(label, value)

                st.json(report, expanded=True)

            else:

                st.write(report)

        else:

            st.info(
                "Run the analysis to view your skill gaps and recommendations."
            )

    st.divider()

    st.markdown("### Resume-based skills")

    if profile.get("resume_text"):

        resume_skills = extract_skills_from_resume(
            profile["resume_text"]
        )

        if resume_skills:

            render_tags(resume_skills)

        else:

            st.caption(
                "No recognized skills were detected in the resume text."
            )

    else:

        st.caption(
            "Upload a resume to extract and review its skills."
        )

# ============================================================
# 27. KAI STREAMING CHAT
# ============================================================

elif selected_page == "Chat with KAI":

    from career_assistant.prompts.career_assistant import SYSTEM_PROMPT

    render_page_header(
        "Chat with KAI",
        "Your personal AI career assistant. Ask about jobs, resumes, skills and interviews."
    )

    if not account_id:

        st.warning(
            "Enter your Email / Profile ID in the sidebar. "
            "This enables persistent chat history."
        )

    # --------------------------------------------------------
    # CONVERSATION ACTIONS
    # --------------------------------------------------------

    action_col, history_col = st.columns([1, 3])

    with action_col:

        if st.button(
            "＋ New chat",
            type="primary",
            use_container_width=True
        ):

            st.session_state.conversation_id = None
            st.session_state.chat_history = []
            st.rerun()

    conversations = (
        get_conversations(account_id)
        if account_id
        else []
    )

    with history_col:

        if conversations:

            conversation_options = {
                f"{item['title']} · {item['created_at'][:10]}":
                item["conversation_id"]
                for item in conversations
            }

            selected_conversation = st.selectbox(
                "Previous conversations",
                ["Select a conversation"] + list(conversation_options.keys()),
                key="conversation_selector"
            )

            load_col, delete_col = st.columns(2)

            with load_col:

                if st.button(
                    "Load conversation",
                    use_container_width=True
                ):

                    if selected_conversation != "Select a conversation":

                        conversation_id = conversation_options[
                            selected_conversation
                        ]

                        st.session_state.conversation_id = conversation_id

                        st.session_state.chat_history = load_messages(
                            conversation_id
                        )

                        st.rerun()

            with delete_col:

                if st.button(
                    "Delete selected conversation",
                    use_container_width=True
                ):

                    if selected_conversation != "Select a conversation":

                        conversation_id = conversation_options[
                            selected_conversation
                        ]

                        delete_conversation(
                            conversation_id,
                            account_id
                        )

                        if (
                            st.session_state.conversation_id
                            == conversation_id
                        ):

                            st.session_state.conversation_id = None
                            st.session_state.chat_history = []

                        st.rerun()

    st.divider()

    # --------------------------------------------------------
    # CHAT SUGGESTIONS
    # --------------------------------------------------------

    suggestions = [
        "Which jobs match my resume and profile?",
        "Identify the most important skill gaps in my resume.",
        "Prepare me for a Python backend interview.",
        "Suggest projects based on my existing skills."
    ]

    if not st.session_state.chat_history:

        st.markdown("### Start with a question")

        suggestion_columns = st.columns(2)

        for index, suggestion in enumerate(suggestions):

            with suggestion_columns[index % 2]:

                if st.button(
                    suggestion,
                    key=f"kai-suggestion-{index}",
                    use_container_width=True
                ):

                    st.session_state.pending_prompt = suggestion
                    st.rerun()

    # --------------------------------------------------------
    # DISPLAY CHAT HISTORY
    # --------------------------------------------------------

    for message in st.session_state.chat_history:

        if message["role"] not in ("user", "assistant"):
            continue

        with st.chat_message(message["role"]):

            st.markdown(message["content"])

    # --------------------------------------------------------
    # STREAMING RESPONSE FUNCTION
    # --------------------------------------------------------

    def stream_kai_response(
        query,
        history,
        user_context,
        retrieved_documents
    ):

        context_parts = []

        context_parts.append(
            "CAREER PROFILE:\n"
            + json.dumps(
                user_context["profile"],
                ensure_ascii=False,
                default=str
            )
        )

        context_parts.append(
            "\nRESUME INFORMATION:\n"
            + user_context["resume_text"][:16000]
        )

        context_parts.append(
            "\nAVAILABLE JOB COUNT:\n"
            + str(user_context["available_job_count"])
        )

        context_parts.append(
            "\nSAVED JOBS:\n"
            + json.dumps(
                user_context["saved_jobs"],
                ensure_ascii=False,
                default=str
            )
        )

        if retrieved_documents:

            context_parts.append(
                "\nRETRIEVED JOB KNOWLEDGE:\n"
                + str(retrieved_documents)[:12000]
            )

        context = "\n\n".join(context_parts)

        messages = [
            {
                "role": "system",
                "content": (
                    SYSTEM_PROMPT
                    + "\n\nUse the supplied career profile, resume, "
                    "conversation and retrieved job context when relevant. "
                    "Do not invent resume details, job availability, "
                    "qualifications or experience. "
                    "If information is missing, say so clearly. "
                    + "Always treat the supplied resume text as the source of truth. "
                    + "If no resume text is supplied, explicitly say that no resume "
                    + "is currently available. Never claim to have read a resume "
                    + "that is missing from the context. "
                    "Use readable Markdown headings, bullet points "
                    "and numbered steps."
                )
            },
            {
                "role": "system",
                "content": "USER CONTEXT:\n" + context
            }
        ]

        # Keep recent messages to control prompt size.
        for message in history[-16:]:

            if message["role"] in ("user", "assistant"):

                messages.append({
                    "role": message["role"],
                    "content": message["content"]
                })

        messages.append({
            "role": "user",
            "content": query
        })

        response = assistant.client.chat.completions.create(
            model=assistant.model,
            messages=messages,
            stream=True,
            temperature=0.5
        )

        for chunk in response:

            if not chunk.choices:
                continue

            content = chunk.choices[0].delta.content

            if content:
                yield content

    # --------------------------------------------------------
    # CHAT INPUT AND MESSAGE PROCESSING
    # --------------------------------------------------------

    prompt = st.chat_input(
        "Message KAI about your career, resume or jobs..."
    )

    if st.session_state.pending_prompt:

        prompt = st.session_state.pending_prompt
        st.session_state.pending_prompt = None

    if prompt:

        prompt = prompt.strip()

        if prompt:

            # Create a new conversation when needed.
            if (
                account_id
                and not st.session_state.conversation_id
            ):

                st.session_state.conversation_id = create_conversation(
                    account_id,
                    prompt
                )

            # Store user message in session.
            st.session_state.chat_history.append({
                "role": "user",
                "content": prompt
            })

            # Persist user message.
            if st.session_state.conversation_id:

                save_message(
                    st.session_state.conversation_id,
                    "user",
                    prompt
                )

            with st.chat_message("user"):

                st.markdown(prompt)

            with st.chat_message("assistant"):

                try:

                    with st.spinner("KAI is preparing your response..."):

                        # Expand the query for job retrieval.
                        expanded_queries = expander.expand_for_jobs(
                            prompt,
                            profile_context
                        )

                        retrieval_query = (
                            " ".join(expanded_queries[:4])
                            if expanded_queries
                            else prompt
                        )

                        retrieved_documents = pipeline.retrieve_context(
                            retrieval_query,
                            top_k=5
                        )

                        saved_jobs = (
                            get_saved_jobs(account_id)
                            if account_id
                            else []
                        )

                        user_context = {
                            "profile": profile_context,
                            "resume_text": profile.get(
                                "resume_text",
                                ""
                            ),
                            "available_job_count": len(jobs),
                            "saved_jobs": [
                                {
                                    "title": job_value(
                                        item["job"],
                                        "title",
                                        default=""
                                    ),
                                    "company": job_value(
                                        item["job"],
                                        "company",
                                        default=""
                                    )
                                }
                                for item in saved_jobs[:20]
                            ]
                        }

                    # Stream text as Gemini generates it.
                    response_text = st.write_stream(
                        stream_kai_response(
                            query=prompt,
                            history=st.session_state.chat_history[:-1],
                            user_context=user_context,
                            retrieved_documents=retrieved_documents
                        )
                    )

                    if not response_text:

                        response_text = (
                            "I could not generate a response. "
                            "Please try again."
                        )

                        st.warning(response_text)

                    # Save completed assistant response.
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": response_text
                    })

                    if st.session_state.conversation_id:

                        save_message(
                            st.session_state.conversation_id,
                            "assistant",
                            response_text
                        )

                except Exception as error:

                    error_message = (
                        "KAI could not complete this request: "
                        + str(error)
                    )

                    st.error(error_message)


# ============================================================
# 28. APPLICATION FOOTER
# ============================================================

st.divider()

footer_left, footer_right = st.columns([3, 1])

with footer_left:

    st.caption(
        "JobRix | Discover opportunities. Build skills. Move forward."
    )

with footer_right:

    st.caption(
        "KAI | Gemini-powered career assistant"
    )
