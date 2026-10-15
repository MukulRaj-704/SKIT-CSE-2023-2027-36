import numpy as np
from sentence_transformers import SentenceTransformer


class Retriever:
    def __init__(self, model_name="all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self.documents = []
        self.embeddings = None

    def set_documents(self, documents):
        self.documents = documents

        if not documents:
            self.embeddings = None
            return

        texts = [document["text"] for document in documents]

        self.embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True
        ).astype("float32")

    def search(self, query, top_k=5):
        if not self.documents or self.embeddings is None:
            return []

        query_embedding = self.model.encode(
            query,
            convert_to_numpy=True,
            normalize_embeddings=True
        ).astype("float32")

        scores = np.dot(
            self.embeddings,
            query_embedding
        )

        top_k = min(top_k, len(self.documents))
        indexes = np.argsort(scores)[::-1][:top_k]

        results = []

        for index in indexes:
            result = dict(self.documents[index])
            result["score"] = float(scores[index])
            results.append(result)

        return results