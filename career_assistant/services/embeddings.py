from typing import List, Dict, Any, Optional
import math
import os


class EmbeddingService:
    """
    Service responsible for converting text documents into
    numerical vector representations.

    The service currently provides a deterministic local
    embedding implementation so that the vector pipeline
    can be developed and tested without requiring an
    external embedding API.

    The interface is intentionally designed so that a
    production embedding provider can be plugged in later.
    """

    def __init__(
        self,
        dimension: int = 384,
        model_name: Optional[str] = None
    ):
        self.dimension = dimension

        self.model_name = (
            model_name
            or os.getenv(
                "KAI_EMBEDDING_MODEL",
                "jobrix-local-embedding"
            )
        )

        if self.dimension <= 0:
            raise ValueError(
                "Embedding dimension must be greater than zero."
            )

    # ---------------------------------------------------------
    # Public API
    # ---------------------------------------------------------

    def embed_text(self, text: str) -> List[float]:
        """
        Convert a single text string into an embedding vector.
        """

        if not isinstance(text, str):
            raise TypeError(
                "Text must be a string."
            )

        text = self._normalize_text(text)

        if not text:
            return self._zero_vector()

        tokens = self._tokenize(text)

        if not tokens:
            return self._zero_vector()

        vector = self._create_vector(tokens)

        return self._normalize_vector(vector)

    def embed_documents(
        self,
        documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Add embeddings to a list of RAG documents.

        Each document is expected to contain a 'text' field.
        The original document is preserved and an 'embedding'
        field is added.
        """

        if not isinstance(documents, list):
            raise TypeError(
                "Documents must be provided as a list."
            )

        embedded_documents = []

        for document in documents:
            if not isinstance(document, dict):
                continue

            text = document.get("text", "")

            if not isinstance(text, str):
                text = str(text)

            embedding = self.embed_text(text)

            embedded_document = dict(document)

            embedded_document["embedding"] = embedding

            embedded_document["embedding_model"] = (
                self.model_name
            )

            embedded_document["embedding_dimension"] = (
                self.dimension
            )

            embedded_documents.append(
                embedded_document
            )

        return embedded_documents

    def embed_query(self, query: str) -> List[float]:
        """
        Generate an embedding for a user search query.

        Queries use the same vector space as documents so
        similarity search can compare them directly.
        """

        return self.embed_text(query)

    # ---------------------------------------------------------
    # Text Processing
    # ---------------------------------------------------------

    def _normalize_text(self, text: str) -> str:
        """
        Normalize whitespace and casing before vectorization.
        """

        return " ".join(
            text.lower().strip().split()
        )

    def _tokenize(self, text: str) -> List[str]:
        """
        Lightweight tokenizer used by the local embedding
        implementation.
        """

        cleaned_text = (
            text.replace(",", " ")
            .replace(".", " ")
            .replace(":", " ")
            .replace(";", " ")
            .replace("(", " ")
            .replace(")", " ")
            .replace("[", " ")
            .replace("]", " ")
            .replace("{", " ")
            .replace("}", " ")
            .replace("/", " ")
            .replace("\\", " ")
            .replace("-", " ")
            .replace("_", " ")
        )

        tokens = cleaned_text.split()

        return [
            token
            for token in tokens
            if token
        ]

    # ---------------------------------------------------------
    # Local Vector Generation
    # ---------------------------------------------------------

    def _create_vector(
        self,
        tokens: List[str]
    ) -> List[float]:
        """
        Create a deterministic vector from tokens.

        Python's built-in hash() is intentionally avoided because
        its result can change between interpreter sessions.
        """

        vector = [0.0] * self.dimension

        for token in tokens:
            positions = self._token_positions(token)

            for position, value in positions:
                vector[position] += value

        token_count = max(len(tokens), 1)

        return [
            value / token_count
            for value in vector
        ]

    def _token_positions(
        self,
        token: str
    ):
        """
        Generate deterministic vector positions for a token.

        Multiple positions are used for every token so that
        semantically related documents can share vector space
        information instead of depending on a single position.
        """

        seed = self._stable_hash(token)

        position_one = seed % self.dimension

        position_two = (
            (seed * 31) + len(token) * 17
        ) % self.dimension

        position_three = (
            (seed * 131) + len(token) * 7
        ) % self.dimension

        magnitude = (
            0.5 + min(len(token), 12) / 24
        )

        return [
            (position_one, magnitude),
            (position_two, magnitude * 0.7),
            (position_three, magnitude * 0.4)
        ]

    def _stable_hash(self, value: str) -> int:
        """
        Generate a stable integer hash without relying on
        Python's randomized hash implementation.
        """

        result = 2166136261

        for character in value:
            result ^= ord(character)
            result *= 16777619
            result &= 0xFFFFFFFF

        return result

    # ---------------------------------------------------------
    # Vector Utilities
    # ---------------------------------------------------------

    def _normalize_vector(
        self,
        vector: List[float]
    ) -> List[float]:
        """
        Normalize a vector to unit length.

        This allows cosine similarity to be calculated using
        a simple dot product later.
        """

        magnitude = math.sqrt(
            sum(value * value for value in vector)
        )

        if magnitude == 0:
            return self._zero_vector()

        return [
            value / magnitude
            for value in vector
        ]

    def _zero_vector(self) -> List[float]:
        """
        Return an empty-information vector.
        """

        return [0.0] * self.dimension

    # ---------------------------------------------------------
    # Similarity
    # ---------------------------------------------------------

    def cosine_similarity(
        self,
        vector_a: List[float],
        vector_b: List[float]
    ) -> float:
        """
        Calculate cosine similarity between two vectors.

        Since vectors generated by this service are normalized,
        the result is effectively their dot product.
        """

        if len(vector_a) != len(vector_b):
            raise ValueError(
                "Vectors must have the same dimension."
            )

        magnitude_a = math.sqrt(
            sum(value * value for value in vector_a)
        )

        magnitude_b = math.sqrt(
            sum(value * value for value in vector_b)
        )

        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0

        dot_product = sum(
            a * b
            for a, b in zip(vector_a, vector_b)
        )

        return dot_product / (
            magnitude_a * magnitude_b
        )

    # ---------------------------------------------------------
    # Batch Utilities
    # ---------------------------------------------------------

    def embed_texts(
        self,
        texts: List[str]
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple text strings.
        """

        if not isinstance(texts, list):
            raise TypeError(
                "Texts must be provided as a list."
            )

        return [
            self.embed_text(text)
            for text in texts
        ]

    def get_dimension(self) -> int:
        """
        Return the configured embedding dimension.
        """

        return self.dimension

    def get_model_name(self) -> str:
        """
        Return the embedding model identifier.
        """

        return self.model_name


def create_embedding_service(
    dimension: int = 384
) -> EmbeddingService:
    """
    Factory function used by other services to create
    an embedding service.
    """

    return EmbeddingService(
        dimension=dimension
    )