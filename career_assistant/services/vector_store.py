from typing import List, Dict, Any, Optional
import math


class VectorStore:
    """
    In-memory vector store for the JobRix career assistant.

    Responsibilities:
        1. Store documents and their embeddings
        2. Add new documents
        3. Remove documents
        4. Search documents using cosine similarity
        5. Return the most relevant documents
        6. Keep document metadata available for RAG

    The storage layer is intentionally isolated from the
    embedding service so that a persistent vector database
    can be introduced later without changing the rest of
    the RAG pipeline.
    """

    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.documents: Dict[str, Dict[str, Any]] = {}

    # =========================================================
    # Document Management
    # =========================================================

    def add_document(
        self,
        document: Dict[str, Any],
        embedding: List[float]
    ) -> bool:
        """
        Add a document and its embedding to the vector store.
        """

        if not isinstance(document, dict):
            raise TypeError(
                "Document must be a dictionary."
            )

        if not isinstance(embedding, list):
            raise TypeError(
                "Embedding must be a list."
            )

        if len(embedding) != self.dimension:
            raise ValueError(
                f"Embedding dimension must be "
                f"{self.dimension}, got {len(embedding)}."
            )

        document_id = document.get("id")

        if not document_id:
            raise ValueError(
                "Document must contain an 'id' field."
            )

        stored_document = dict(document)

        stored_document["embedding"] = embedding

        self.documents[str(document_id)] = stored_document

        return True

    def add_documents(
        self,
        documents: List[Dict[str, Any]]
    ) -> int:
        """
        Add multiple documents.

        Each document must contain an 'embedding' field.
        """

        if not isinstance(documents, list):
            raise TypeError(
                "Documents must be provided as a list."
            )

        added_count = 0

        for document in documents:

            if not isinstance(document, dict):
                continue

            embedding = document.get("embedding")

            if not embedding:
                continue

            try:
                self.add_document(
                    document,
                    embedding
                )

                added_count += 1

            except (TypeError, ValueError):
                continue

        return added_count

    def remove_document(
        self,
        document_id: str
    ) -> bool:
        """
        Remove a document from the vector store.
        """

        document_id = str(document_id)

        if document_id not in self.documents:
            return False

        del self.documents[document_id]

        return True

    def clear(self) -> None:
        """
        Remove all documents from the vector store.
        """

        self.documents.clear()

    # =========================================================
    # Retrieval
    # =========================================================

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        min_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Search the vector store using cosine similarity.

        Returns the highest scoring documents first.
        """

        if not isinstance(query_embedding, list):
            raise TypeError(
                "Query embedding must be a list."
            )

        if len(query_embedding) != self.dimension:
            raise ValueError(
                f"Query embedding dimension must be "
                f"{self.dimension}, got "
                f"{len(query_embedding)}."
            )

        if top_k <= 0:
            return []

        scored_documents = []

        for document in self.documents.values():

            embedding = document.get("embedding")

            if not embedding:
                continue

            score = self.cosine_similarity(
                query_embedding,
                embedding
            )

            if score < min_score:
                continue

            result = dict(document)

            result["score"] = round(
                score,
                6
            )

            scored_documents.append(result)

        scored_documents.sort(
            key=lambda item: item["score"],
            reverse=True
        )

        return scored_documents[:top_k]

    # =========================================================
    # Similarity
    # =========================================================

    def cosine_similarity(
        self,
        vector_a: List[float],
        vector_b: List[float]
    ) -> float:
        """
        Calculate cosine similarity between two vectors.
        """

        if len(vector_a) != len(vector_b):
            raise ValueError(
                "Vectors must have the same dimension."
            )

        magnitude_a = math.sqrt(
            sum(
                value * value
                for value in vector_a
            )
        )

        magnitude_b = math.sqrt(
            sum(
                value * value
                for value in vector_b
            )
        )

        if magnitude_a == 0:
            return 0.0

        if magnitude_b == 0:
            return 0.0

        dot_product = sum(
            a * b
            for a, b in zip(
                vector_a,
                vector_b
            )
        )

        return dot_product / (
            magnitude_a * magnitude_b
        )

    # =========================================================
    # Filtering
    # =========================================================

    def search_by_metadata(
        self,
        query_embedding: List[float],
        filters: Optional[Dict[str, Any]] = None,
        top_k: int = 5,
        min_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Perform vector search with optional metadata filters.

        Example:

            {
                "category": "Software Development",
                "location": "India"
            }
        """

        if not filters:
            return self.search(
                query_embedding,
                top_k,
                min_score
            )

        filtered_documents = []

        for document in self.documents.values():

            metadata = document.get(
                "metadata",
                {}
            )

            matches = True

            for key, expected_value in filters.items():

                actual_value = metadata.get(key)

                if isinstance(actual_value, list):

                    if expected_value not in actual_value:
                        matches = False
                        break

                elif actual_value != expected_value:

                    matches = False
                    break

            if matches:
                filtered_documents.append(
                    document
                )

        scored_documents = []

        for document in filtered_documents:

            embedding = document.get(
                "embedding"
            )

            if not embedding:
                continue

            score = self.cosine_similarity(
                query_embedding,
                embedding
            )

            if score < min_score:
                continue

            result = dict(document)

            result["score"] = round(
                score,
                6
            )

            scored_documents.append(result)

        scored_documents.sort(
            key=lambda item: item["score"],
            reverse=True
        )

        return scored_documents[:top_k]

    # =========================================================
    # Store Information
    # =========================================================

    def get_document(
        self,
        document_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve one document by ID.
        """

        return self.documents.get(
            str(document_id)
        )

    def contains(
        self,
        document_id: str
    ) -> bool:
        """
        Check whether a document exists.
        """

        return str(document_id) in self.documents

    def count(self) -> int:
        """
        Return the number of stored documents.
        """

        return len(self.documents)

    def get_all_documents(
        self
    ) -> List[Dict[str, Any]]:
        """
        Return all stored documents.
        """

        return list(
            self.documents.values()
        )

    def get_statistics(self) -> Dict[str, Any]:
        """
        Return basic vector store statistics.
        """

        return {
            "document_count": self.count(),
            "embedding_dimension": self.dimension,
            "storage_type": "in_memory",
        }


def create_vector_store(
    dimension: int = 384
) -> VectorStore:
    """
    Factory function for creating a vector store.
    """

    return VectorStore(
        dimension=dimension
    )