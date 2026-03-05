"""Qdrant storage layer for MCU Specs MCP Server."""

import re
import uuid
from datetime import datetime
from typing import Optional
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    CreateCollection,
)

from ..config import settings
from ..models import Document, Chunk, SearchResult


# Collection names
CHUNKS_COLLECTION = "mcu_specs_chunks"
DOCS_COLLECTION = "mcu_specs_docs"


def generate_uuid_from_string(s: str) -> str:
    """Generate a deterministic UUID from a string (for reproducible IDs)."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, s))


class QdrantStore:
    """Qdrant storage for chunks and document metadata."""
    
    def __init__(self, url: Optional[str] = None):
        """Initialize Qdrant client.
        
        Args:
            url: Qdrant server URL (defaults to settings.qdrant_url)
        """
        self.url = url or settings.qdrant_url
        self.client = QdrantClient(url=self.url)
        self._ensure_collections()
    
    def _ensure_collections(self):
        """Create collections if they don't exist."""
        # Chunks collection (with vectors)
        if not self.client.collection_exists(CHUNKS_COLLECTION):
            self.client.create_collection(
                collection_name=CHUNKS_COLLECTION,
                vectors_config=VectorParams(
                    size=settings.embedding_dimensions,
                    distance=Distance.COSINE,
                ),
            )
        
        # Documents metadata collection (no vectors, just payload)
        if not self.client.collection_exists(DOCS_COLLECTION):
            self.client.create_collection(
                collection_name=DOCS_COLLECTION,
                vectors_config={},  # No vectors for metadata
            )
    
    # =========================================================================
    # Document Operations
    # =========================================================================
    
    def store_document(self, doc: Document) -> None:
        """Store document metadata."""
        # Use UUID derived from doc_id for Qdrant point ID
        point_id = generate_uuid_from_string(doc.doc_id)
        self.client.upsert(
            collection_name=DOCS_COLLECTION,
            points=[
                PointStruct(
                    id=point_id,
                    vector={},  # Empty vector for metadata-only collection
                    payload=doc.model_dump(mode="json"),
                )
            ],
        )
    
    def get_document(self, doc_id: str) -> Optional[Document]:
        """Get document metadata by ID."""
        try:
            point_id = generate_uuid_from_string(doc_id)
            results = self.client.retrieve(
                collection_name=DOCS_COLLECTION,
                ids=[point_id],
                with_payload=True,
            )
            if results:
                return Document(**results[0].payload)
        except Exception:
            pass
        return None
    
    def list_documents(self) -> list[Document]:
        """List all indexed documents."""
        results, _ = self.client.scroll(
            collection_name=DOCS_COLLECTION,
            limit=100,
            with_payload=True,
        )
        return [Document(**r.payload) for r in results if r.payload]
    
    def delete_document(self, doc_id: str) -> None:
        """Delete document and all its chunks."""
        # Delete chunks
        self.client.delete(
            collection_name=CHUNKS_COLLECTION,
            points_selector=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            ),
        )
        # Delete document metadata
        point_id = generate_uuid_from_string(doc_id)
        self.client.delete(
            collection_name=DOCS_COLLECTION,
            points_selector=[point_id],
        )
    
    # =========================================================================
    # Chunk Operations
    # =========================================================================
    
    def upsert_chunks(self, chunks: list[Chunk], embeddings: list[list[float]], batch_size: int = 100) -> None:
        """Upsert chunks with embeddings.
        
        Args:
            chunks: List of chunks to store
            embeddings: Corresponding embeddings (same order as chunks)
            batch_size: Number of points per batch (to avoid payload size limits)
        """
        if len(chunks) != len(embeddings):
            raise ValueError(f"Mismatch: {len(chunks)} chunks, {len(embeddings)} embeddings")
        
        # Build all points
        points = []
        for chunk, embedding in zip(chunks, embeddings):
            # Use UUID derived from chunk_id for Qdrant point ID
            point_id = generate_uuid_from_string(chunk.chunk_id)
            points.append(
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "chunk_id": chunk.chunk_id,
                        "doc_id": chunk.doc_id,
                        "content": chunk.content,
                        "section_id": chunk.section_id,
                        "section_title": chunk.section_title,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "chunk_index": chunk.chunk_index,
                        "content_hash": chunk.content_hash,
                    },
                )
            )
        
        # Upsert in batches to avoid Qdrant payload size limits
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            self.client.upsert(
                collection_name=CHUNKS_COLLECTION,
                points=batch,
            )
    
    def get_chunk(self, chunk_id: str) -> Optional[dict]:
        """Get a specific chunk by ID."""
        try:
            point_id = generate_uuid_from_string(chunk_id)
            results = self.client.retrieve(
                collection_name=CHUNKS_COLLECTION,
                ids=[point_id],
                with_payload=True,
                with_vectors=False,
            )
            if results:
                return self._payload_to_result(results[0])
        except Exception:
            pass
        return None
    
    def get_chunks_by_section(self, doc_id: str, section_id: str) -> list[dict]:
        """Get all chunks for a section."""
        scroll_filter = Filter(
            must=[
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                FieldCondition(key="section_id", match=MatchValue(value=section_id)),
            ]
        )
        results, _ = self.client.scroll(
            collection_name=CHUNKS_COLLECTION,
            scroll_filter=scroll_filter,
            limit=100,
            with_payload=True,
            with_vectors=False,
        )
        return [self._payload_to_result(r) for r in results]
    
    def get_chunks_by_pages(self, doc_id: str, pages: list[int]) -> list[dict]:
        """Get chunks that overlap with specified pages."""
        # Note: This is a simplified approach - we get all chunks for the doc
        # and filter in Python. For large docs, this could be optimized.
        scroll_filter = Filter(
            must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
        )
        results, _ = self.client.scroll(
            collection_name=CHUNKS_COLLECTION,
            scroll_filter=scroll_filter,
            limit=1000,
            with_payload=True,
            with_vectors=False,
        )
        
        # Filter chunks that overlap with requested pages
        filtered = []
        for r in results:
            payload = r.payload
            page_start = payload.get("page_start", 0)
            page_end = payload.get("page_end", 0)
            # Check if any requested page is in the chunk's page range
            for page in pages:
                if page_start <= page <= page_end:
                    filtered.append(self._payload_to_result(r))
                    break
        
        return filtered
    
    # =========================================================================
    # Search Operations
    # =========================================================================
    
    def search_semantic(
        self,
        query_vector: list[float],
        doc_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[SearchResult]:
        """Semantic search via vector similarity."""
        query_filter = None
        if doc_id:
            query_filter = Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            )
        
        results = self.client.query_points(
            collection_name=CHUNKS_COLLECTION,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        
        return [self._to_search_result(r) for r in results.points]
    
    def search_literal(
        self,
        query: str,
        doc_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[SearchResult]:
        """Literal text matching (post-filter on content).
        
        Handles MCU symbols like GPIOx_MODER, USART_CR1, etc.
        Automatically escapes special regex characters.
        """
        # Build filter for doc_id if provided
        scroll_filter = None
        if doc_id:
            scroll_filter = Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            )
        
        # Scroll through chunks and filter by content match
        results, _ = self.client.scroll(
            collection_name=CHUNKS_COLLECTION,
            scroll_filter=scroll_filter,
            limit=1000,  # Scan more for literal matching
            with_payload=True,
            with_vectors=False,
        )
        
        # Filter by literal match (case-insensitive)
        query_lower = query.lower()
        matches = []
        for r in results:
            content = r.payload.get("content", "")
            if query_lower in content.lower():
                matches.append(self._to_search_result(r, score=0.5))  # Default score for literal
                if len(matches) >= limit:
                    break
        
        return matches
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _payload_to_result(self, point) -> dict:
        """Convert Qdrant point payload to result dict."""
        payload = point.payload
        return {
            "chunk_id": payload.get("chunk_id"),
            "doc_id": payload.get("doc_id"),
            "content": payload.get("content"),
            "section_id": payload.get("section_id"),
            "section_title": payload.get("section_title"),
            "page_start": payload.get("page_start"),
            "page_end": payload.get("page_end"),
            "chunk_index": payload.get("chunk_index"),
            "content_hash": payload.get("content_hash"),
        }
    
    def _to_search_result(self, point, score: Optional[float] = None) -> SearchResult:
        """Convert Qdrant point to SearchResult."""
        payload = point.payload
        score = score if score is not None else point.score
        
        # Build human-readable source citation
        doc_id = payload.get("doc_id", "")
        page = payload.get("page_start", 0)
        section_id = payload.get("section_id", "")
        source = f"{doc_id} p{page}"
        if section_id:
            source += f" §{section_id}"
        
        return SearchResult(
            chunk_id=payload.get("chunk_id", ""),
            doc_id=doc_id,
            content=payload.get("content", ""),
            score=score,
            source=source,
            section_id=payload.get("section_id"),
            section_title=payload.get("section_title"),
            page=page,
            doc_title=payload.get("doc_title"),
        )


# Global store instance
_store: Optional[QdrantStore] = None


def get_store() -> QdrantStore:
    """Get or create the global QdrantStore instance."""
    global _store
    if _store is None:
        _store = QdrantStore()
    return _store
