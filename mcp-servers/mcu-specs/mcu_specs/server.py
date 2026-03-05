"""MCU Specs MCP Server - Spec search engine for microcontroller datasheets."""

import asyncio
import hashlib
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

from .config import settings
from .models import Document, SearchResponse, SearchResult
from .storage import QdrantStore
from .storage.qdrant_store import CHUNKS_COLLECTION
from .embedding import EmbeddingClient
from .ingestion import PDFParser, Chunker


# Create FastMCP server
mcp = FastMCP(
    "mcu-specs",
    instructions="""MCU Specs - Microcontroller Datasheet Search Engine

This server provides tools for searching and retrieving information from indexed 
microcontroller datasheets, reference manuals, and technical documentation.

## Available Tools

- `spec_list_documents` - List all indexed documents
- `spec_get_toc` - Get table of contents for a document
- `spec_search` - Hybrid search (semantic + literal) across all documents
- `spec_get_section` - Get all chunks from a specific section
- `spec_get_chunk` - Get a specific chunk by ID
- `spec_get_pages` - Get all content from specific pages
- `spec_ingest` - Ingest a new PDF document

## Usage Tips

1. Use `spec_search` for finding specific register names, peripheral info, or concepts
2. Use `spec_get_toc` to understand document structure before deep diving
3. Use `spec_get_section` when you need complete information about a topic
4. Literal search is best for exact register names (e.g., "GPIOx_MODER")
""",
)

# Global instances
_store: Optional[QdrantStore] = None
_embedding_client: Optional[EmbeddingClient] = None
_parser: Optional[PDFParser] = None
_chunker: Optional[Chunker] = None


def get_store() -> QdrantStore:
    """Get or create QdrantStore instance."""
    global _store
    if _store is None:
        _store = QdrantStore()
    return _store


def get_embedding_client() -> EmbeddingClient:
    """Get or create EmbeddingClient instance."""
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client


def get_parser() -> PDFParser:
    """Get or create PDFParser instance."""
    global _parser
    if _parser is None:
        _parser = PDFParser()
    return _parser


def get_chunker() -> Chunker:
    """Get or create Chunker instance."""
    global _chunker
    if _chunker is None:
        _chunker = Chunker()
    return _chunker


# =============================================================================
# Tools
# =============================================================================

@mcp.tool
def spec_list_documents() -> list[dict]:
    """List all indexed MCU datasheet documents.
    
    Returns:
        List of documents with id, title, filename, and page count
    """
    store = get_store()
    docs = store.list_documents()
    return [
        {
            "doc_id": doc.doc_id,
            "title": doc.title,
            "filename": doc.filename,
            "total_pages": doc.total_pages,
            "indexed_at": doc.indexed_at,
        }
        for doc in docs
    ]


@mcp.tool
def spec_get_toc(doc_id: str) -> dict:
    """Get table of contents for a document.
    
    Args:
        doc_id: Document identifier (e.g., "STM32F427_Reference_Manual")
        
    Returns:
        Document metadata with sections (TOC)
    """
    store = get_store()
    doc = store.get_document(doc_id)
    if not doc:
        return {"error": f"Document not found: {doc_id}"}
    
    return {
        "doc_id": doc.doc_id,
        "title": doc.title,
        "filename": doc.filename,
        "total_pages": doc.total_pages,
        "sections": [
            {
                "section_id": s.section_id,
                "title": s.title,
                "page_start": s.page_start,
                "page_end": s.page_end,
                "level": s.level,
            }
            for s in doc.sections
        ],
    }


@mcp.tool
async def spec_search(
    query: str,
    doc_id: Optional[str] = None,
    mode: str = "hybrid",
    limit: int = 10,
) -> dict:
    """Search for information in indexed datasheets.
    
    Uses hybrid search by default (semantic + literal). For exact register 
    names or symbols, literal mode may be more precise.
    
    Args:
        query: Search query (register name, peripheral, concept, etc.)
        doc_id: Optional document ID to limit search scope
        mode: Search mode - "semantic", "literal", or "hybrid" (default)
        limit: Maximum number of results (default 10)
        
    Returns:
        Search results with chunks and source citations
    """
    store = get_store()
    client = get_embedding_client()
    
    results = []
    
    if mode in ("semantic", "hybrid"):
        # Semantic search via embeddings
        query_vector = await client.embed_one(query)
        semantic_results = store.search_semantic(query_vector, doc_id=doc_id, limit=limit * 2)
        results.extend(semantic_results)
    
    if mode in ("literal", "hybrid"):
        # Literal text matching
        literal_results = store.search_literal(query, doc_id=doc_id, limit=limit * 2)
        results.extend(literal_results)
    
    if mode == "hybrid":
        # Reciprocal Rank Fusion
        results = _reciprocal_rank_fusion(results, limit)
    else:
        # Deduplicate by chunk_id and limit
        seen = set()
        unique = []
        for r in results:
            if r.chunk_id not in seen:
                seen.add(r.chunk_id)
                unique.append(r)
        results = unique[:limit]
    
    return {
        "query": query,
        "mode": mode,
        "total": len(results),
        "results": [
            {
                "chunk_id": r.chunk_id,
                "score": r.score,
                "source": r.source,
                "section_id": r.section_id,
                "section_title": r.section_title,
                "page": r.page,
                "content": r.content[:500] + "..." if len(r.content) > 500 else r.content,
            }
            for r in results
        ],
    }


@mcp.tool
def spec_get_section(doc_id: str, section_id: str) -> dict:
    """Get all content from a specific section.
    
    Args:
        doc_id: Document identifier
        section_id: Section identifier (e.g., "3.1" or "GPIO")
        
    Returns:
        All chunks from the section with full content
    """
    store = get_store()
    
    # Get document for section title
    doc = store.get_document(doc_id)
    if not doc:
        return {"error": f"Document not found: {doc_id}"}
    
    # Find section title
    section_title = None
    for s in doc.sections:
        if s.section_id == section_id:
            section_title = s.title
            break
    
    chunks = store.get_chunks_by_section(doc_id, section_id)
    
    if not chunks:
        return {"error": f"Section not found: {section_id}"}
    
    return {
        "doc_id": doc_id,
        "section_id": section_id,
        "section_title": section_title,
        "total_chunks": len(chunks),
        "chunks": [
            {
                "chunk_id": c["chunk_id"],
                "page_start": c["page_start"],
                "page_end": c["page_end"],
                "content": c["content"],
            }
            for c in chunks
        ],
    }


@mcp.tool
def spec_get_chunk(chunk_id: str) -> dict:
    """Get a specific chunk by ID.
    
    Use this to retrieve the full content of a chunk found via search.
    
    Args:
        chunk_id: Chunk identifier (from search results)
        
    Returns:
        Full chunk content with metadata
    """
    store = get_store()
    chunk = store.get_chunk(chunk_id)
    
    if not chunk:
        return {"error": f"Chunk not found: {chunk_id}"}
    
    return {
        "chunk_id": chunk["chunk_id"],
        "doc_id": chunk["doc_id"],
        "section_id": chunk["section_id"],
        "section_title": chunk["section_title"],
        "page_start": chunk["page_start"],
        "page_end": chunk["page_end"],
        "content": chunk["content"],
    }


@mcp.tool
def spec_get_pages(doc_id: str, pages: list[int]) -> dict:
    """Get all content from specific pages.
    
    Args:
        doc_id: Document identifier
        pages: List of page numbers to retrieve
        
    Returns:
        All chunks that overlap with the specified pages
    """
    store = get_store()
    
    # Get document for title
    doc = store.get_document(doc_id)
    if not doc:
        return {"error": f"Document not found: {doc_id}"}
    
    chunks = store.get_chunks_by_pages(doc_id, pages)
    
    return {
        "doc_id": doc_id,
        "doc_title": doc.title,
        "pages_requested": pages,
        "total_chunks": len(chunks),
        "chunks": [
            {
                "chunk_id": c["chunk_id"],
                "page_start": c["page_start"],
                "page_end": c["page_end"],
                "section_id": c["section_id"],
                "section_title": c["section_title"],
                "content": c["content"],
            }
            for c in chunks
        ],
    }


@mcp.tool
async def spec_ingest(
    pdf_path: str,
    doc_id: Optional[str] = None,
) -> dict:
    """Ingest a new PDF document into the index.
    
    Parses the PDF, chunks it, generates embeddings, and stores in Qdrant.
    
    Args:
        pdf_path: Path to PDF file
        doc_id: Optional document ID (defaults to filename stem)
        
    Returns:
        Ingestion result with document info and chunk count
    """
    path = Path(pdf_path)
    if not path.exists():
        return {"error": f"File not found: {pdf_path}"}
    
    if not path.suffix.lower() == ".pdf":
        return {"error": f"Not a PDF file: {pdf_path}"}
    
    store = get_store()
    client = get_embedding_client()
    parser = get_parser()
    chunker = get_chunker()
    
    # Parse PDF
    parsed = parser.parse(path, doc_id=doc_id)
    
    # Check if already indexed (by file hash) AND has chunks
    existing = store.get_document(parsed.doc_id)
    if existing and existing.file_hash == parsed.file_hash:
        # Verify chunks exist (in case previous indexing was incomplete)
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        chunk_results, _ = store.client.scroll(
            collection_name=CHUNKS_COLLECTION,
            scroll_filter=Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=parsed.doc_id))]
            ),
            limit=1,
            with_payload=False,
        )
        if chunk_results:
            return {
                "status": "skipped",
                "reason": "Document already indexed (same file hash)",
                "doc_id": parsed.doc_id,
            }
        # Document exists but no chunks - re-index
        store.delete_document(parsed.doc_id)
    
    # Chunk content
    chunks = chunker.chunk(parsed)
    
    if not chunks:
        return {
            "status": "error",
            "reason": "No content extracted from PDF",
            "doc_id": parsed.doc_id,
        }
    
    # Generate embeddings (batch)
    batch_size = 50
    all_embeddings = []
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        texts = [c.content for c in batch]
        embeddings = await client.embed(texts)
        all_embeddings.extend(embeddings)
    
    # Store in Qdrant
    doc = parser.to_document(parsed)
    store.store_document(doc)
    store.upsert_chunks(chunks, all_embeddings)
    
    return {
        "status": "success",
        "doc_id": parsed.doc_id,
        "title": parsed.title,
        "total_pages": parsed.total_pages,
        "total_chunks": len(chunks),
        "sections": len(parsed.sections),
    }


@mcp.tool
def spec_delete_document(doc_id: str) -> dict:
    """Delete a document and all its chunks from the index.
    
    Args:
        doc_id: Document identifier to delete
        
    Returns:
        Deletion result
    """
    store = get_store()
    
    # Check if document exists
    doc = store.get_document(doc_id)
    if not doc:
        return {"error": f"Document not found: {doc_id}"}
    
    store.delete_document(doc_id)
    
    return {
        "status": "success",
        "doc_id": doc_id,
        "title": doc.title,
    }


# =============================================================================
# Helper Functions
# =============================================================================

def _reciprocal_rank_fusion(results: list[SearchResult], limit: int, k: int = 60) -> list[SearchResult]:
    """Combine multiple result lists using Reciprocal Rank Fusion.
    
    RRF score = sum(1 / (k + rank)) for each list containing the item
    """
    # Group by chunk_id
    chunk_scores: dict[str, float] = {}
    chunk_data: dict[str, SearchResult] = {}
    
    for rank, result in enumerate(results, 1):
        chunk_id = result.chunk_id
        if chunk_id not in chunk_scores:
            chunk_scores[chunk_id] = 0.0
            chunk_data[chunk_id] = result
        chunk_scores[chunk_id] += 1.0 / (k + rank)
    
    # Sort by combined score
    sorted_chunks = sorted(
        chunk_scores.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:limit]
    
    # Build final results
    final_results = []
    for chunk_id, score in sorted_chunks:
        result = chunk_data[chunk_id]
        # Update score to RRF score
        result.score = score
        final_results.append(result)
    
    return final_results


# =============================================================================
# Entry Point
# =============================================================================

def main():
    """Entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
