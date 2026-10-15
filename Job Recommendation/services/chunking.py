def split_text(text, chunk_size=500, overlap=80):
    if not text:
        return []

    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    paragraphs = [
        paragraph.strip()
        for paragraph in text.split("\n")
        if paragraph.strip()
    ]

    chunks = []
    current_words = []

    for paragraph in paragraphs:
        words = paragraph.split()

        if len(current_words) + len(words) <= chunk_size:
            current_words.extend(words)
            continue

        if current_words:
            chunks.append(" ".join(current_words))

        overlap_words = current_words[-overlap:] if overlap else []
        current_words = overlap_words + words

        while len(current_words) > chunk_size:
            chunks.append(" ".join(current_words[:chunk_size]))
            current_words = current_words[chunk_size - overlap:] if overlap else current_words[chunk_size:]

    if current_words:
        chunks.append(" ".join(current_words))

    return chunks


def chunk_document(document, chunk_size=500, overlap=80):
    text = document.get("text", "")
    chunks = split_text(text, chunk_size, overlap)

    result = []

    for index, chunk in enumerate(chunks):
        item = {
            "id": f"{document['id']}_chunk_{index}",
            "text": chunk,
            "source": document.get("source"),
            "document_id": document.get("id")
        }

        if document.get("metadata"):
            item["metadata"] = document["metadata"]

        result.append(item)

    return result


def chunk_documents(documents, chunk_size=500, overlap=80):
    chunks = []

    for document in documents:
        chunks.extend(
            chunk_document(
                document,
                chunk_size,
                overlap
            )
        )

    return chunks