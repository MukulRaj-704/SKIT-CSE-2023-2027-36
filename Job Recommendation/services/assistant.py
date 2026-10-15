import os

from openai import OpenAI

from ..prompts.career_assistant import SYSTEM_PROMPT
from .context import build_context


class CareerAssistant:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set")

        self.client = OpenAI(
            api_key=api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        self.model = os.getenv("KAI_MODEL", "gemini-3.6-flash")

    def generate_response(
        self,
        query,
        retrieved_documents=None,
        conversation_history=None,
        user_context=None
    ):
        context = build_context(
            retrieved_documents or [],
            conversation_history or [],
            user_context
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": f"Context:\n{context}\n\nUser question:\n{query}"
                }
            ]
        )

        return response.choices[0].message.content.strip()