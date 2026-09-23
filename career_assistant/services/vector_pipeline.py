from typing import List, Dict, Any, Optional

from .embeddings import EmbeddingService
from .vector_store import VectorStore


class VectorPipeline:
    """
    End to end vector processing pipeline for JobRix.

    Responsibilities:

        1. Receive RAG documents
        2. Generate embeddings
        3. Store embedded documents
        4. Convert user queries into embeddings
        5. Search the vector store
        6. Return ranked results

    This class acts as the integration layer between the
    embedding service and vector store.
    """

    def __init__(
        self,
        embedding_service: Optional[
            EmbeddingService
        ] = None,
        vector_store: Optional[
            VectorStore
        ] = None
    ):
        self.embedding_service = (
            embedding_service
            or EmbeddingService()
        )

        self.vector_store = (
            vector_store
            or VectorStore(
                dimension=self.embedding_service.get_dimension()
            )
        )

    # =========================================================
    # Document Processing
    # =========================================================

    def add_document(
        self,
        document: Dict[str, Any]
    ) -> bool:
        """
        Generate an embedding for one document
        and add it to the vector store.
        """

        if not isinstance(document, dict):
            raise TypeError(
                "Document must be a dictionary."
            )

        text = document.get("text")

        if not text:
            return False

        embedding = (
            self.embedding_service.embed_text(
                text
            )
        )

        document_with_embedding = dict(
            document
        )

        document_with_embedding[
            "embedding"
        ] = embedding

        return self.vector_store.add_document(
            document_with_embedding,
            embedding
        )

    def add_documents(
        self,
        documents: List[Dict[str, Any]]
    ) -> int:
        """
        Generate embeddings for multiple documents
        and store them.
        """

        if not isinstance(documents, list):
            raise TypeError(
                "Documents must be provided as a list."
            )

        embedded_documents = (
            self.embedding_service.embed_documents(
                documents
            )
        )

        return self.vector_store.add_documents(
            embedded_documents
        )

    # =========================================================
    # Query Processing
    # =========================================================

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Convert a natural language query into an embedding
        and perform similarity search.
        """

        if not isinstance(query, str):
            raise TypeError(
                "Query must be a string."
            )

        query = query.strip()

        if not query:
            return []

        query_embedding = (
            self.embedding_service.embed_query(
                query
            )
        )

        return self.vector_store.search(
            query_embedding=query_embedding,
            top_k=top_k,
            min_score=min_score
        )

    def search_with_filters(
        self,
        query: str,
        filters: Optional[
            Dict[str, Any]
        ] = None,
        top_k: int = 5,
        min_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search with optional metadata
        filtering.

        Example:

            filters = {
                "category": "Software Development"
            }
        """

        if not query or not query.strip():
            return []

        query_embedding = (
            self.embedding_service.embed_query(
                query
            )
        )

        return self.vector_store.search_by_metadata(
            query_embedding=query_embedding,
            filters=filters,
            top_k=top_k,
            min_score=min_score
        )

    # =========================================================
    # Document Management
    # =========================================================

    def remove_document(
        self,
        document_id: str
    ) -> bool:
        """
        Remove a document from the vector store.
        """

        return self.vector_store.remove_document(
            document_id
        )

    def clear(self) -> None:
        """
        Clear the complete vector store.
        """

        self.vector_store.clear()

    def document_exists(
        self,
        document_id: str
    ) -> bool:
        """
        Check whether a document exists.
        """

        return self.vector_store.contains(
            document_id
        )

    # =========================================================
    # Pipeline Information
    # =========================================================

    def count(self) -> int:
        """
        Return the number of indexed documents.
        """

        return self.vector_store.count()

    def statistics(self) -> Dict[str, Any]:
        """
        Return information about the current
        vector pipeline.
        """

        stats = (
            self.vector_store.get_statistics()
        )

        stats["embedding_model"] = (
            self.embedding_service.get_model_name()
        )

        return stats

    # =========================================================
    # Context Preparation
    # =========================================================

    def retrieve_context(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Retrieve only the relevant information needed
        by the RAG context builder.

        The embedding itself is removed from the returned
        documents because it is not required by the LLM.
        """

        results = self.search(
            query=query,
            top_k=top_k,
            min_score=min_score
        )

        context_documents = []

        for result in results:

            document = dict(result)

            document.pop(
                "embedding",
                None
            )

            context_documents.append(
                document
            )

        return context_documents


def create_vector_pipeline(
    dimension: int = 384
) -> VectorPipeline:
    """
    Factory function for creating a complete
    vector processing pipeline.
    """

    embedding_service = EmbeddingService(
        dimension=dimension
    )

    vector_store = VectorStore(
        dimension=dimension
    )

    return VectorPipeline(
        embedding_service=embedding_service,
        vector_store=vector_store
    )