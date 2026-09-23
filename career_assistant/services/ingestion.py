import json


def load_json_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    return data if isinstance(data, list) else []


def clean_text(text):
    if not isinstance(text, str):
        return ""

    return " ".join(text.split()).strip()


def prepare_document(text, source, document_id=None, metadata=None):
    text = clean_text(text)
    if not text:
        return None

    document = {
        "id": document_id,
        "text": text,
        "source": source
    }

    if metadata:
        document["metadata"] = metadata

    return document


def document_from_item(item, source, index):
    if isinstance(item, str):
        return prepare_document(
            item,
            source,
            f"{source}_{index}"
        )

    if not isinstance(item, dict):
        return None

    text = item.get("text") or item.get("content") or item.get("description")
    document_id = item.get("id") or f"{source}_{index}"

    metadata = {
        key: value
        for key, value in item.items()
        if key not in {"id", "text", "content", "description"}
    }

    return prepare_document(
        text,
        source,
        document_id,
        metadata
    )


def ingest_documents(items, source):
    documents = []

    for index, item in enumerate(items):
        document = document_from_item(item, source, index)
        if document:
            documents.append(document)

    return documents


def ingest_json_file(file_path, source):
    data = load_json_file(file_path)
    return ingest_documents(data, source)


def ingest_sources(sources):
    documents = []

    for source, file_path in sources.items():
        documents.extend(
            ingest_json_file(file_path, source)
        )

    return documents


def ingest_text(text, source, document_id, metadata=None):
    return prepare_document(
        text,
        source,
        document_id,
        metadata
    )


def ingest_report(report, source, document_id=None):
    if isinstance(report, str):
        return prepare_document(
            report,
            source,
            document_id
        )

    if not isinstance(report, dict):
        return None

    parts = []

    for key, value in report.items():
        if value is None:
            continue

        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)

        if isinstance(value, dict):
            value = json.dumps(value, ensure_ascii=False)

        parts.append(f"{key}: {value}")

    return prepare_document(
        "\n".join(parts),
        source,
        document_id,
        {"type": "report"}
    )
def ingest_jobrix_jobs(jobs):
    """
    Convert JobRix API job listings into RAG documents.
    """

    documents = []

    for index, job in enumerate(jobs):
        if not isinstance(job, dict):
            continue

        job_text = "\n".join(
            [
                f"Job Title: {job.get('title', '')}",
                f"Company: {job.get('company', '')}",
                f"Category: {job.get('category', '')}",
                f"Job Type: {job.get('job_type', '')}",
                f"Location: {job.get('location', '')}",
                f"Experience: {job.get('experience', '')}",
                f"Salary: {job.get('salary', '')}",
                f"Skills: {', '.join(job.get('tags', []))}",
                f"Description: {job.get('description', '')}"
            ]
        )

        metadata = {
            "company": job.get("company", ""),
            "category": job.get("category", ""),
            "job_type": job.get("job_type", ""),
            "location": job.get("location", ""),
            "salary": job.get("salary", ""),
            "publication_date": job.get(
                "publication_date",
                ""
            ),
            "url": job.get("url", ""),
            "tags": job.get("tags", []),
            "source": job.get("source", "JobRix")
        }

        document = prepare_document(
            job_text,
            "jobrix",
            job.get("id") or f"jobrix_{index}",
            metadata
        )

        if document:
            documents.append(document)

    return documents