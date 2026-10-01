"""
analyzer/services/skills_taxonomy.py
====================================
One place that knows what a "skill" is: canonical names, categories, spelling
variants ("REST API" == "RESTful APIs"), implied skills and related skills.

Everything is plain data + a tiny matcher, so the behaviour is explainable and
easy to extend: add a line to ``_TABLE`` and the whole analyzer learns it.
"""

from __future__ import annotations

import re
from collections import OrderedDict

LANG, FRAMEWORK, DB = "Programming Languages", "Frameworks", "Databases"
CLOUD, DEVOPS, ML = "Cloud", "DevOps", "Machine Learning"
DATA, WEB, TOOLS = "Data Science", "Web Development", "Tools"
CONCEPT, SOFT = "Core Concepts", "Soft Skills"

# category | canonical | aliases (;-separated). Aliases are case-insensitive and
# tolerate plural "s", and spaces match "-" / multiple spaces as well.
_TABLE = """
Programming Languages|python|python3
Programming Languages|java|
Programming Languages|javascript|ecmascript;es6
Programming Languages|typescript|
Programming Languages|c++|cpp;c plus plus
Programming Languages|c#|csharp;c sharp
Programming Languages|golang|
Programming Languages|rust|
Programming Languages|kotlin|
Programming Languages|swift|
Programming Languages|php|
Programming Languages|ruby|
Programming Languages|scala|
Programming Languages|sql|t-sql;pl/sql
Programming Languages|bash|shell scripting;shell script
Frameworks|django|
Frameworks|django rest framework|drf;django rest;django restframework
Frameworks|django channels|
Frameworks|flask|
Frameworks|fastapi|fast api
Frameworks|spring boot|springboot
Frameworks|express.js|expressjs;express js
Frameworks|node.js|nodejs;node js
Frameworks|react|react.js;reactjs;react js
Frameworks|angular|angularjs
Frameworks|vue|vue.js;vuejs
Frameworks|next.js|nextjs
Frameworks|.net|dotnet;asp.net
Frameworks|laravel|
Frameworks|tailwind css|tailwind
Frameworks|bootstrap|
Databases|postgresql|postgres;postgre sql
Databases|mysql|my sql
Databases|sqlite|
Databases|mongodb|mongo db;mongo
Databases|redis|
Databases|sql server|mssql;microsoft sql server
Databases|oracle|oracle db
Databases|elasticsearch|elastic search
Databases|dynamodb|dynamo db
Databases|firebase|firestore
Databases|cassandra|
Databases|orm|object relational mapping
Cloud|aws|amazon web services;ec2;s3;aws lambda
Cloud|gcp|google cloud;google cloud platform
Cloud|azure|microsoft azure
Cloud|heroku|
Cloud|render|
Cloud|cloudinary|
DevOps|docker|dockerfile;containerization
DevOps|kubernetes|k8s
DevOps|ci/cd|cicd;ci cd;continuous integration;continuous deployment;continuous delivery
DevOps|jenkins|
DevOps|github actions|
DevOps|gitlab ci|gitlab ci/cd
DevOps|terraform|
DevOps|ansible|
DevOps|nginx|
DevOps|linux|unix
DevOps|celery|
DevOps|kafka|apache kafka
DevOps|rabbitmq|
Machine Learning|machine learning|ml
Machine Learning|deep learning|neural networks;neural network
Machine Learning|tensorflow|
Machine Learning|pytorch|
Machine Learning|keras|
Machine Learning|scikit-learn|sklearn;scikit learn
Machine Learning|xgboost|
Machine Learning|ensemble learning|random forest;gradient boosting
Machine Learning|nlp|natural language processing
Machine Learning|computer vision|opencv
Machine Learning|generative ai|genai;gen ai;generative artificial intelligence
Machine Learning|llm|large language model
Machine Learning|rag|retrieval-augmented generation;retrieval augmented generation
Machine Learning|transformers|hugging face;huggingface
Machine Learning|sentence transformers|sentence-transformers;sbert
Machine Learning|faiss|vector search;vector database
Machine Learning|langchain|
Machine Learning|mlops|model deployment
Machine Learning|feature engineering|
Data Science|pandas|
Data Science|numpy|
Data Science|matplotlib|
Data Science|seaborn|
Data Science|data analysis|data analytics
Data Science|statistics|statistical analysis;statistical tests
Data Science|data visualization|data visualisation
Data Science|data preprocessing|data cleaning;data preparation
Data Science|power bi|powerbi
Data Science|tableau|
Data Science|excel|ms excel;microsoft excel
Data Science|jupyter notebook|jupyter
Data Science|etl|
Data Science|spark|apache spark;pyspark
Data Science|hadoop|
Web Development|rest api|restful api;restful web services;rest api development;restful services;rest web services
Web Development|graphql|
Web Development|websockets|websocket;web socket
Web Development|html|html5
Web Development|css|css3
Web Development|microservices|micro services;microservice architecture
Web Development|jwt|json web token
Web Development|ajax|
Web Development|responsive design|responsive web design
Tools|git|
Tools|github|
Tools|gitlab|
Tools|jira|
Tools|postman|
Tools|swagger|openapi
Tools|figma|
Tools|selenium|
Tools|pytest|unittest
Core Concepts|data structures and algorithms|dsa;data structures & algorithms;data structures;algorithms
Core Concepts|operating systems|
Core Concepts|dbms|database management systems;database management system
Core Concepts|computer networks|computer networking
Core Concepts|oop|object oriented programming;object-oriented programming;object oriented
Core Concepts|system design|
Core Concepts|unit testing|unit tests;test driven development;tdd
Core Concepts|agile|scrum;kanban
Core Concepts|design patterns|
Core Concepts|api design|
Core Concepts|version control|
Core Concepts|multithreading|concurrency;multi-threading
Soft Skills|communication|communication skills
Soft Skills|teamwork|team player;collaboration;collaborative;collaborate
Soft Skills|leadership|team lead;led a team
Soft Skills|problem solving|problem-solving;analytical skills;analytical thinking
Soft Skills|time management|
Soft Skills|adaptability|adaptable;fast learner;quick learner
Soft Skills|critical thinking|
Soft Skills|ownership|self-motivated;self motivated
Soft Skills|mentoring|mentorship
Soft Skills|stakeholder management|
"""

# Words that, when the *requirement* is missing from the resume but one of these
# generic hints is present, mean "mentioned loosely, not explicitly".
HINTS = {
    "rest api": ["api", "apis", "web service"],
    "docker": ["container", "containers"],
    "aws": ["cloud"],
    "sql": ["database", "databases"],
    "unit testing": ["testing", "tests"],
}

# Strong, deterministic implications ("A on the resume proves B").
IMPLIES = {
    "django rest framework": ["django", "rest api"],
    "postgresql": ["sql"],
    "mysql": ["sql"],
    "sqlite": ["sql"],
    "sql server": ["sql"],
    "scikit-learn": ["machine learning"],
    "tensorflow": ["machine learning", "deep learning"],
    "pytorch": ["machine learning", "deep learning"],
    "keras": ["machine learning", "deep learning"],
    "next.js": ["react"],
    "sentence transformers": ["transformers"],
    "gitlab ci": ["ci/cd"],
    "github actions": ["ci/cd"],
    "jenkins": ["ci/cd"],
    "pytest": ["unit testing"],
    "django channels": ["django", "websockets"],
}

# Skills that are close but NOT identical: earn partial credit, never a match.
RELATED_GROUPS = [
    {"django", "flask", "fastapi"},
    {"react", "angular", "vue", "next.js"},
    {"postgresql", "mysql", "sqlite", "sql server", "oracle"},
    {"mongodb", "dynamodb", "cassandra", "firebase"},
    {"aws", "gcp", "azure"},
    {"tensorflow", "pytorch", "keras"},
    {"docker", "kubernetes"},
    {"ci/cd", "jenkins", "github actions", "gitlab ci"},
    {"power bi", "tableau", "matplotlib", "seaborn"},
    {"kafka", "rabbitmq", "celery"},
    {"git", "github", "gitlab", "version control"},
    {"terraform", "ansible"},
    {"java", "kotlin", "scala", "spring boot"},
    {"c", "c++", "rust", "golang"},
    {"llm", "rag", "langchain", "generative ai", "transformers", "sentence transformers"},
    {"pytest", "unit testing", "selenium"},
    {"node.js", "express.js"},
    {"javascript", "typescript"},
]

_SEP = r"[\s\-_]+"


def _alias_regex(alias: str) -> str:
    parts = [re.escape(p) for p in re.split(r"\s+", alias.strip()) if p]
    body = _SEP.join(parts)
    if alias[-1].isalpha() and len(alias) > 2:
        body += "s?"
    return body


class Skill:
    __slots__ = ("name", "category", "aliases")

    def __init__(self, name, category, aliases):
        self.name, self.category, self.aliases = name, category, aliases


SKILLS: "OrderedDict[str, Skill]" = OrderedDict()
for _line in _TABLE.strip().splitlines():
    _cat, _name, _al = _line.split("|")
    SKILLS[_name] = Skill(_name, _cat, [a.strip() for a in _al.split(";") if a.strip()])

_BOUNDARY_L, _BOUNDARY_R = r"(?<![A-Za-z0-9+#])", r"(?![A-Za-z0-9+#])"

# alias -> canonical, longest alias first so the most specific phrase wins.
_PATTERNS: list[tuple[re.Pattern, str]] = []
for _s in SKILLS.values():
    for _a in {_s.name, *_s.aliases}:
        _PATTERNS.append(
            (re.compile(_BOUNDARY_L + _alias_regex(_a) + _BOUNDARY_R, re.I), _s.name)
        )
_PATTERNS.sort(key=lambda p: -len(p[0].pattern))

# The language "C" is too ambiguous for the generic matcher: uppercase only.
SKILLS["c"] = Skill("c", LANG, [])
_C_RE = re.compile(r"(?<![A-Za-z0-9+#.\-])C(?![A-Za-z0-9+#])(?!\.\w)")
_C_CONTEXT = re.compile(r"(?:\bC\s*/\s*C\+\+|\bC\s*[,;|]|[,;|:]\s*C\b|\bin C\b|\bC\s+and\b|\bC\s+language|\blanguages?\s*:?\s*C\b)")

_RELATED: dict[str, set[str]] = {}
for _g in RELATED_GROUPS:
    for _m in _g:
        _RELATED.setdefault(_m, set()).update(_g - {_m})


def find_skills(text: str) -> "OrderedDict[str, int]":
    """Canonical skill -> mention count, in order of first appearance."""
    found: dict[str, tuple[int, int]] = {}
    for pattern, name in _PATTERNS:
        for m in pattern.finditer(text or ""):
            cur = found.get(name)
            found[name] = (min(cur[0], m.start()) if cur else m.start(), (cur[1] if cur else 0) + 1)
    if _C_CONTEXT.search(text or "") and _C_RE.search(text or ""):
        found["c"] = (_C_RE.search(text).start(), 1)
    return OrderedDict(sorted(((k, v[1]) for k, v in found.items()), key=lambda kv: found[kv[0]][0]))


def canonical(term: str) -> str | None:
    """Canonical skill name for a free-text term ("RESTful APIs" -> "rest api")."""
    term = (term or "").strip()
    if not term:
        return None
    if term == "C":
        return "c"
    for pattern, name in _PATTERNS:
        m = pattern.fullmatch(term)
        if m:
            return name
    return None


def category_of(name: str) -> str:
    skill = SKILLS.get(name)
    return skill.category if skill else "Other"


def display_name(name: str) -> str:
    """Human friendly casing for output ("rest api" -> "REST API")."""
    special = {
        "aws": "AWS", "gcp": "GCP", "sql": "SQL", "html": "HTML", "css": "CSS",
        "ci/cd": "CI/CD", "rest api": "REST API", "nlp": "NLP", "llm": "LLM",
        "rag": "RAG", "oop": "OOP", "orm": "ORM", "dbms": "DBMS", "etl": "ETL",
        "jwt": "JWT", "ajax": "AJAX", "faiss": "FAISS", "mysql": "MySQL",
        "postgresql": "PostgreSQL", "mongodb": "MongoDB", "dynamodb": "DynamoDB",
        "numpy": "NumPy", "pytorch": "PyTorch", "tensorflow": "TensorFlow",
        "fastapi": "FastAPI", "graphql": "GraphQL", "github": "GitHub",
        "gitlab": "GitLab", "javascript": "JavaScript", "typescript": "TypeScript",
        "node.js": "Node.js", "next.js": "Next.js", "express.js": "Express.js",
        "react": "React", "vue": "Vue", "c++": "C++", "c#": "C#", "c": "C",
        "scikit-learn": "Scikit-learn", "xgboost": "XGBoost", "mlops": "MLOps",
        "devops": "DevOps", "langchain": "LangChain", "power bi": "Power BI",
        "tailwind css": "Tailwind CSS", "django rest framework": "Django REST Framework",
        "sql server": "SQL Server", "websockets": "WebSockets", "jira": "Jira",
        "dsa": "DSA", "data structures and algorithms": "Data Structures & Algorithms",
        "ensemble learning": "Ensemble Learning", "gitlab ci": "GitLab CI",
        "github actions": "GitHub Actions", "elasticsearch": "Elasticsearch",
        "sentence transformers": "Sentence Transformers", "pytest": "pytest", "generative ai": "Generative AI",
        ".net": ".NET", "golang": "Go (Golang)", "kafka": "Kafka",
    }
    return special.get(name, name.title() if " " in name or name.isalpha() else name)


def is_technical(name: str) -> bool:
    return category_of(name) not in (SOFT, "Other")


def related_to(name: str) -> set[str]:
    return _RELATED.get(name, set())


def implied_by(name: str, resume_skills) -> str | None:
    """A resume skill that deterministically proves ``name`` (or None)."""
    for have in resume_skills:
        if name in IMPLIES.get(have, ()):
            return have
    return None
