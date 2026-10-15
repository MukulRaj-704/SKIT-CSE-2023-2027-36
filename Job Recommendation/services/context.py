def build_context(retrieved_documents, conversation_history=None, user_context=None):
    context_parts = []
    if user_context:
        context_parts.append(
            "User Context:\n" + format_context(user_context)
        )
    if retrieved_documents:
        context_parts.append(
            "Relevant Information:\n" +
            format_documents(retrieved_documents)
        )
    if conversation_history:
        context_parts.append(
            "Conversation History:\n" +
            format_conversation(conversation_history)
        )
    return "\n\n".join(context_parts)


def format_documents(documents):
    parts = []
    for document in documents:
        source = document.get("source", "unknown")
        text = document.get("text", "").strip()
        if text:
            parts.append(
                f"[{source}]\n{text}"
            )
    return "\n\n".join(parts)


def format_conversation(messages):
    parts = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "").strip()
        if content:
            parts.append(
                f"{role}: {content}"
            )
    return "\n".join(parts)


def format_context(data):
    if isinstance(data, str):
        return data.strip()
    if isinstance(data, list):
        return ", ".join(str(item) for item in data)
    if isinstance(data, dict):
        parts = []
        for key, value in data.items():
            if value is None:
                continue
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            parts.append(f"{key}: {value}")
        return "\n".join(parts)
    return str(data)