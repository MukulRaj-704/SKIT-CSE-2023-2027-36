from typing import List, Dict, Any, Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from .vector_store import VectorStore


class Retriever:
    """
    Semantic retriever for the JobRix Career Assistant.

    This retriever combines SentenceTransformer embeddings
    with the JobRix VectorStore.

    Responsibilities:

        1. Load an embedding model
        2. Convert documents into embeddings
        3. Store documents inside the vector store
        4. Convert user queries into embeddings
        5. Perform similarity search
        6. Return ranked documents with relevance scores
        7. Support optional metadata filtering

    The class keeps the same public methods used by the
    previous retrieval implementation so existing RAG
    components can continue to use it.
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        vector_store: Optional[VectorStore] = None
    ):
        self.model_name = model_name

        self.model = SentenceTransformer(
            model_name
        )

        self.documents: List[
            Dict[str, Any]
        ] = []

        self.embeddings = None

        embedding_dimension = (
            self.model.get_sentence_embedding_dimension()
        )

        self.vector_store = (
            vector_store
            or VectorStore(
                dimension=embedding_dimension
            )
        )

    # =========================================================
    # Document Indexing
    # =========================================================

    def set_documents(
        self,
        documents: List[Dict[str, Any]]
    ):
        """
        Replace the current document collection.

        Documents are embedded using SentenceTransformer
        and then indexed inside the VectorStore.
        """

        if not isinstance(documents, list):
            raise TypeError(
                "Documents must be provided as a list."
            )

        self.documents = documents

        self.vector_store.clear()

        if not documents:
            self.embeddings = None
            return

        texts = []

        valid_documents = []

        for document in documents:

            if not isinstance(document, dict):
                continue

            text = document.get(
                "text",
                ""
            )

            if not isinstance(text, str):
                continue

            if not text.strip():
                continue

            texts.append(text)

            valid_documents.append(
                document
            )

        self.documents = valid_documents

        if not texts:
            self.embeddings = None
            return

        self.embeddings = self.model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True
        ).astype("float32")

        self._index_documents()

    def _index_documents(self):
        """
        Store embedded documents inside the VectorStore.
        """

        if self.embeddings is None:
            return

        for index, document in enumerate(
            self.documents
        ):

            embedding = (
                self.embeddings[index]
                .tolist()
            )

            document_id = (
                document.get("id")
                or f"document_{index}"
            )

            indexed_document = dict(
                document
            )

            indexed_document["id"] = (
                document_id
            )

            indexed_document[
                "embedding"
            ] = embedding

            self.vector_store.add_document(
                indexed_document,
                embedding
            )

    # =========================================================
    # Search
    # =========================================================

    def search(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Search documents using semantic similarity.
        """

        if not isinstance(query, str):
            raise TypeError(
                "Query must be a string."
            )

        query = query.strip()

        if not query:
            return []

        if not self.documents:
            return []

        query_embedding = self.model.encode(
            query,
            convert_to_numpy=True,
            normalize_embeddings=True
        ).astype("float32")

        results = self.vector_store.search(
            query_embedding=query_embedding.tolist(),
            top_k=top_k,
            min_score=min_score
        )

        return self._clean_results(
            results
        )

    # =========================================================
    # Filtered Search
    # =========================================================

    def search_by_metadata(
        self,
        query: str,
        filters: Optional[
            Dict[str, Any]
        ] = None,
        top_k: int = 5,
        min_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic search with metadata filters.

        Example:

            filters = {
                "category": "Software Development"
            }
        """

        if not isinstance(query, str):
            raise TypeError(
                "Query must be a string."
            )

        query = query.strip()

        if not query:
            return []

        if not self.documents:
            return []

        query_embedding = self.model.encode(
            query,
            convert_to_numpy=True,
            normalize_embeddings=True
        ).astype("float32")

        results = (
            self.vector_store.search_by_metadata(
                query_embedding=query_embedding.tolist(),
                filters=filters,
                top_k=top_k,
                min_score=min_score
            )
        )

        return self._clean_results(
            results
        )

    # =========================================================
    # Result Processing
    # =========================================================

    def _clean_results(
        self,
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Remove embeddings from retrieval results.

        Embeddings are required internally for similarity
        search but should not be passed unnecessarily into
        the LLM context.
        """

        cleaned_results = []

        for result in results:

            cleaned_result = dict(
                result
            )

            cleaned_result.pop(
                "embedding",
                None
            )

            cleaned_results.append(
                cleaned_result
            )

        return cleaned_results

    # =========================================================
    # Document Management
    # =========================================================

    def add_document(
        self,
        document: Dict[str, Any]
    ) -> bool:
        """
        Add one new document to the existing index.
        """

        if not isinstance(document, dict):
            raise TypeError(
                "Document must be a dictionary."
            )

        text = document.get(
            "text",
            ""
        )

        if not text.strip():
            return False

        embedding = self.model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True
        ).astype("float32")

        document_id = (
            document.get("id")
            or f"document_{len(self.documents)}"
        )

        indexed_document = dict(
            document
        )

        indexed_document["id"] = (
            document_id
        )

        indexed_document[
            "embedding"
        ] = embedding.tolist()

        self.vector_store.add_document(
            indexed_document,
            embedding.tolist()
        )

        self.documents.append(
            indexed_document
        )

        if self.embeddings is None:
            self.embeddings = (
                embedding.reshape(1, -1)
            )

        else:
            self.embeddings = np.vstack(
                [
                    self.embeddings,
                    embedding
                ]
            )

        return True

    def remove_document(
        self,
        document_id: str
    ) -> bool:
        """
        Remove a document from the retriever.
        """

        removed = (
            self.vector_store.remove_document(
                document_id
            )
        )

        if not removed:
            return False

        self.documents = [
            document
            for document in self.documents
            if str(document.get("id"))
            != str(document_id)
        ]

        if not self.documents:
            self.embeddings = None

        else:

            texts = [
                document["text"]
                for document in self.documents
            ]

            self.embeddings = self.model.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True
            ).astype("float32")

        return True

    # =========================================================
    # Statistics
    # =========================================================

    def count(self) -> int:
        """
        Return the number of indexed documents.
        """

        return self.vector_store.count()

    def get_statistics(self) -> Dict[str, Any]:
        """
        Return retriever and vector store information.
        """

        return {
            "document_count": self.count(),
            "embedding_model": self.model_name,
            "embedding_dimension": (
                self.model
                .get_sentence_embedding_dimension()
            ),
            "vector_store": "in_memory"
        }