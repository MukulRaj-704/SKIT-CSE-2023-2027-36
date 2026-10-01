"""Shared fixtures for the analyzer tests: real PDF/DOCX files and sample texts."""

import io
import zipfile
from xml.sax.saxutils import escape

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APITestCase

RESUME_LINES = [
    "Aarav Mehta",
    "aarav.mehta@example.com | +91 98765 43210",
    "Jaipur, India | linkedin.com/in/aaravmehta | github.com/aaravm",
    "Professional Summary",
    "Backend developer with hands-on experience building REST APIs in Django and PostgreSQL.",
    "Technical Skills",
    "Languages: Python, SQL, JavaScript",
    "Frameworks: Django, Django REST Framework, React.js",
    "Databases: PostgreSQL, MySQL",
    "Tools: Git, GitHub, Postman",
    "Work Experience",
    "Software Engineer Intern | Jan 2024 - Jun 2024",
    "Acme Technologies, Jaipur",
    "- Built Django REST Framework APIs used by 3 internal teams.",
    "- Optimised PostgreSQL queries, cutting report time by 30%.",
    "",
    "Projects",
    "TaskHub - Task management web app (GitHub)",
    "Django, PostgreSQL, React.js",
    "- Designed the REST API and database schema for tasks, teams and comments.",
    "- Implemented token authentication and role based permissions.",
    "Education",
    "Swami Keshvanand Institute of Technology, Jaipur | 2021 - 2025",
    "B.Tech in Computer Science & Engineering | CGPA: 8.9/10",
    "Certifications",
    "- Django Web Development - GeeksforGeeks",
]

JOB_DESCRIPTION = """Backend Engineer
We are hiring a Backend Engineer with 2+ years of Django experience.
Requirements:
- Strong Python, Django and RESTful APIs
- PostgreSQL, Docker, Redis, Git
- Bachelor's degree in Computer Science or related field
Nice to have:
- CI/CD, Kubernetes
Responsibilities:
- Build and maintain REST API development for our platform
- Design databases and optimise queries
"""


def build_pdf(lines=None, image=False, text=True) -> bytes:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    y = 60
    if text:
        for line in (RESUME_LINES if lines is None else lines):
            page.insert_text((60, y), line, fontsize=10)
            y += 14
    if image:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
        pix.clear_with(200)
        page.insert_image(pymupdf.Rect(60, 400, 160, 500), pixmap=pix)
    data = doc.tobytes()
    doc.close()
    return data


def build_docx(lines=None, tables=0) -> bytes:
    paras = "".join(
        f"<w:p><w:r><w:t xml:space=\"preserve\">{escape(l)}</w:t></w:r></w:p>" for l in (RESUME_LINES if lines is None else lines)
    )
    tbl = "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>cell</w:t></w:r></w:p></w:tc></w:tr></w:tbl>" * tables
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paras}{tbl}</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", xml)
    return buf.getvalue()


def upload(data, name="resume.pdf", ctype="application/pdf"):
    return SimpleUploadedFile(name, data, content_type=ctype)


class AnalyzerAPITestCase(APITestCase):
    """Anonymous client (the module has no login) + a clean throttle cache."""

    def setUp(self):
        cache.clear()

    def upload_resume(self, data=None, name="resume.pdf"):
        return self.client.post(reverse("analyzer_api:resume_upload"),
                                {"file": upload(build_pdf() if data is None else data, name)}, format="multipart")
