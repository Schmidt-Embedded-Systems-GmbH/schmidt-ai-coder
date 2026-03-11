# MCU Specs MCP Server Implementation Plan

## Overview

A FastMCP 3.x server that provides a "spec search engine" for microcontroller datasheets and reference manuals. The server enables LLM agents to search, retrieve, and analyze technical documentation through keyword, semantic, and hybrid search.

## Key Design Decisions

| Decision          | Choice                   | Rationale                                      |
| ----------------- | ------------------------ | ---------------------------------------------- |
| **Qdrant**        | Docker container         | Easiest setup, well-maintained image           |
| **SQLite**        | Not needed               | Qdrant handles both vector + payload filtering |
| **Chunk storage** | Qdrant payloads          | Avoid duplication, single source of truth      |
| **Async model**   | Sync tools + `to_thread` | Simpler for demo, avoid async gotchas          |
| **Chunk IDs**     | Deterministic + hash     | Stable citations, incremental reindexing       |

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     MCU Specs MCP Server                         │
├─────────────────────────────────────────────────────────────────┤
│  Tools (6 core + 1 agentic)                                      │
│  ├─ spec_list_documents()     - List available documents         │
│  ├─ spec_get_toc()            - Get table of contents           │
│  ├─ spec_search()             - Search (literal/semantic/hybrid) │
│  ├─ spec_get_section()        - Fetch section by ID              │
│  ├─ spec_get_chunk()          - Fetch specific chunk            │
│  ├─ spec_get_pages()          - Fetch specific pages            │
│  └─ spec_answer() [agentic]   - Intelligent QA via sampling     │
├─────────────────────────────────────────────────────────────────┤
│  Storage Layer (Simplified)                                      │
│  ├─ Qdrant (Docker)          - Vector search + payload storage  │
│  │   ├─ Embeddings           - Semantic similarity              │
│  │   ├─ Chunk payloads       - Text, metadata, citations        │
│  │   └─ Payload filtering    - doc_id, section_id, page filters │
│  └─ File System              - Original PDFs only               │
├─────────────────────────────────────────────────────────────────┤
│  Ingestion Pipeline                                              │
│  ├─ PDF Parser               - Extract text, TOC, structure     │
│  ├─ Chunker                  - Section-aware chunking            │
│  ├─ Embedder                 - Generate embeddings via API      │
│  └─ Indexer                  - Upsert to Qdrant                 │
└─────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
mcp-servers/mcu-specs/
├── pyproject.toml              # Project metadata, dependencies
├── README.md                  # Usage documentation
├── uv.lock                     # Dependency lockfile
├── mcu_specs/
│   ├── __init__.py
│   ├── server.py              # FastMCP server entry point
│   ├── config.py              # Configuration (embedding endpoint, etc.)
│   ├── models.py              # Pydantic models for API
│   ├── storage/
│   │   ├── __init__.py
│   │   └── qdrant_store.py    # Qdrant operations (vector + payload)
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── pdf_parser.py      # PDF parsing (pdfplumber)
│   │   ├── chunker.py         # Section-aware chunking
│   │   └── indexer.py         # Upsert to Qdrant
│   └── embedding/
│       ├── __init__.py
│       └── client.py          # Embedding API client
└── tests/
    ├── __init__.py
    ├── test_server.py
    ├── test_storage.py
    └── test_ingestion.py
```

## Dependencies

```toml
[project]
name = "mcu-specs"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastmcp>=3.0.0",
    "qdrant-client>=1.7.0",     # Vector DB (connects to Docker)
    "pdfplumber>=0.10.0",       # PDF parsing
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0", # Configuration
    "httpx>=0.27.0",            # Embedding API client
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
]
```

## Qdrant Setup (Docker)

```bash
# Start Qdrant container
docker run -d \
  --name mcu-specs-qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v $(pwd)/.mcu-specs/qdrant:/qdrant/storage \
  qdrant/qdrant

# Environment variable for connection
export MCU_SPECS_QDRANT_URL="http://localhost:6333"
```

## Core Tools Design

### 1. `spec_list_documents()`

List all indexed documents with metadata.

```python
@mcp.tool()
async def spec_list_documents() -> list[dict]:
    """
    List available microcontroller documents (datasheets, reference manuals).

    Returns:
        List of documents with id, title, version, page_count, indexed_at
    """
```

**Output:**

```json
[
	{
		"doc_id": "stm32f4_rm0090@rev17",
		"title": "STM32F4 Reference Manual",
		"version": "Rev 17",
		"page_count": 1150,
		"indexed_at": "2026-03-03T12:00:00Z"
	}
]
```

### 2. `spec_get_toc()`

Get table of contents for a document.

```python
@mcp.tool()
async def spec_get_toc(
    doc_id: str,
    depth: int = 3,
) -> dict:
    """
    Return a TOC-style listing with stable section IDs and page ranges.

    Args:
        doc_id: Document identifier
        depth: Maximum depth of TOC hierarchy (default: 3)

    Returns:
        Hierarchical TOC with section_id, title, page_start, page_end
    """
```

**Output:**

```json
{
	"doc_id": "stm32f4_rm0090@rev17",
	"sections": [
		{
			"section_id": "11",
			"title": "GPIOs",
			"page_start": 385,
			"page_end": 420,
			"children": [
				{
					"section_id": "11.4",
					"title": "GPIO mode configuration",
					"page_start": 390,
					"page_end": 395
				}
			]
		}
	]
}
```

### 3. `spec_search()` (The "Search Engine" Tool)

Multi-mode search supporting literal, semantic, and hybrid.

```python
@mcp.tool()
def spec_search(  # Note: sync tool for simplicity
    query: str,
    mode: str = "hybrid",  # "literal" | "semantic" | "hybrid"
    doc_id: str | None = None,
    max_results: int = 5,
    min_score: float = 0.0,
) -> dict:
    """
    Search across indexed MCU specs.

    Args:
        query: Search query
        mode: Search mode:
            - "literal": Exact text matching (for symbols like GPIOx_MODER)
            - "semantic": Vector similarity (for natural language queries)
            - "hybrid": Combine both with reciprocal rank fusion
        doc_id: Optional document filter
        max_results: Maximum results (default: 5)
        min_score: Minimum relevance score (0.0-1.0)

    Returns:
        Search results with content, source citation, score

    Note:
        For MCU symbols with underscores (GPIOx_MODER) or special chars,
        use "literal" mode. The query is automatically escaped for safe matching.
    """
```

**Output:**

```json
{
	"results": [
		{
			"content": "The GPIOx_MODER register configures the I/O mode...",
			"source": "RM0090 rev17 p387 §11.4.2",
			"score": 0.92,
			"doc_id": "stm32f4_rm0090@rev17",
			"section_id": "11.4.2",
			"chunk_id": "stm32f4_rm0090@rev17|11.4.2|p387-p388|i003|h3a2b1c4d",
			"page": 387
		}
	],
	"total_found": 15,
	"tokens_estimate": 450
}
```

**Chunk ID Format** (deterministic, enables stable citations):

```
{doc_id}|{section_id}|p{page_start}-p{page_end}|i{chunk_index:04d}|h{content_hash}
```

### 4. `spec_get_section()`

Fetch a complete section/chapter by ID.

```python
@mcp.tool()
async def spec_get_section(
    doc_id: str,
    section_id: str,
    max_chars: int = 12000,
    offset: int = 0,
) -> dict:
    """
    Fetch section text (chapter/section). Supports paging.

    Args:
        doc_id: Document identifier
        section_id: Section ID (e.g., "11.4.2")
        max_chars: Maximum characters to return (default: 12000)
        offset: Character offset for pagination

    Returns:
        Section content with metadata
    """
```

### 5. `spec_get_chunk()`

Fetch a specific chunk by ID (precise citation target).

```python
@mcp.tool()
def spec_get_chunk(
    doc_id: str,
    chunk_id: str,
) -> dict:
    """
    Fetch an exact chunk by ID (the most precise citation target).

    Args:
        doc_id: Document identifier
        chunk_id: Chunk identifier (deterministic format)

    Returns:
        Chunk content with full metadata
    """
```

### 6. `spec_get_pages()` (New - Recommended)

Fetch specific pages from a document. Very useful for debugging scenarios
where an agent wants to see a table that spans multiple pages.

```python
@mcp.tool()
def spec_get_pages(
    doc_id: str,
    pages: list[int],
) -> dict:
    """
    Fetch specific pages from a document.

    Useful for viewing tables or figures that span multiple pages.

    Args:
        doc_id: Document identifier
        pages: List of page numbers (0-indexed PDF page indices)

    Returns:
        Page contents with metadata

    Note:
        Uses PDF page index (not printed page numbers which may differ).
        Page 0 is the first page of the PDF.
    """
```

**Output:**

```json
{
	"doc_id": "stm32f4_rm0090@rev17",
	"pages": [
		{
			"page_index": 386,
			"printed_page": "387",
			"content": "11.4.2 GPIO mode register (GPIOx_MODER)...",
			"has_tables": true
		}
	]
}
```

### 7. `spec_answer()` (Agentic Tool - Tagged)

Intelligent QA using MCP sampling for synthesis.

```python
@mcp.tool(tags={"agentic"})
async def spec_answer(
    question: str,
    doc_id: str | None = None,
    ctx: Context = None,
) -> str:
    """
    "Intelligent" QA:
    1) Retrieve passages (hybrid search)
    2) Ask the client model to synthesize an answer, citing sources

    This tool uses MCP sampling to request an LLM completion
    through the client during tool execution.

    Args:
        question: The question to answer
        doc_id: Optional document filter

    Returns:
        Synthesized answer with citations
    """
```

## Ingestion Pipeline

### PDF Parsing

Use `pdfplumber` for reliable text extraction with structure preservation:

```python
# ingestion/pdf_parser.py
import pdfplumber

def parse_pdf(path: str) -> ParsedDocument:
    """Extract text, TOC, and structure from PDF."""
    with pdfplumber.open(path) as pdf:
        # Extract TOC from PDF bookmarks
        toc = extract_toc(pdf)

        # Extract text per page with layout preservation
        pages = []
        for page in pdf.pages:
            pages.append(Page(
                number=page.page_number,
                text=page.extract_text(layout=True),
                width=page.width,
                height=page.height,
            ))

        return ParsedDocument(toc=toc, pages=pages)
```

### Section-Aware Chunking

Chunk by section boundaries first, then sub-chunk if too large.
Uses deterministic chunk IDs with content hash for stable citations:

```python
# ingestion/chunker.py
import hashlib

def make_chunk_id(doc_id: str, section_id: str, page_start: int, page_end: int, index: int, content: str) -> str:
    """Generate deterministic chunk ID with content hash."""
    content_hash = hashlib.sha1(content.encode()).hexdigest()[:8]
    return f"{doc_id}|{section_id}|p{page_start}-p{page_end}|i{index:04d}|h{content_hash}"

def chunk_document(doc: ParsedDocument) -> list[Chunk]:
    """Create section-aware chunks."""
    chunks = []

    for section in doc.toc.sections:
        # Get text for this section
        section_text = extract_section_text(doc.pages, section)

        # Target chunk size: 300-900 tokens (~1200-3600 chars)
        if len(section_text) <= 3600:
            chunk_id = make_chunk_id(
                doc.doc_id, section.section_id,
                section.page_start, section.page_end,
                0, section_text
            )
            chunks.append(Chunk(
                chunk_id=chunk_id,
                content=section_text,
                section_id=section.section_id,
                page_start=section.page_start,
                page_end=section.page_end,
            ))
        else:
            # Sub-chunk large sections
            for i, sub_chunk in enumerate(split_chunk(section_text, max_chars=3600, overlap=200)):
                chunk_id = make_chunk_id(
                    doc.doc_id, section.section_id,
                    section.page_start, section.page_end,
                    i, sub_chunk
                )
                chunks.append(Chunk(
                    chunk_id=chunk_id,
                    content=sub_chunk,
                    section_id=section.section_id,
                    ...
                ))

    return chunks
```

### Embedding Client

Configurable embedding endpoint (OpenRouter/OpenAI-compatible):

```python
# embedding/client.py
import httpx

class EmbeddingClient:
    def __init__(self, endpoint: str, api_key: str, model: str):
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.endpoint}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "input": texts,
                }
            )
            response.raise_for_status()
            data = response.json()
            return [item["embedding"] for item in data["data"]]
```

### Indexing

Store everything in Qdrant (simplified - no SQLite):

```python
# ingestion/indexer.py
import asyncio
from qdrant_client.models import PointStruct

def index_document(doc: ParsedDocument, chunks: list[Chunk], store: QdrantStore, embedder: EmbeddingClient):
    """Index document into Qdrant (sync, run in thread if needed)."""
    # 1. Generate embeddings (batch for efficiency)
    embeddings = embedder.embed([c.content for c in chunks])

    # 2. Create Qdrant points with full payload
    points = []
    for chunk, embedding in zip(chunks, embeddings):
        points.append(PointStruct(
            id=chunk.chunk_id,  # Use deterministic chunk_id as point ID
            vector=embedding,
            payload={
                "doc_id": doc.doc_id,
                "chunk_id": chunk.chunk_id,
                "content": chunk.content,
                "section_id": chunk.section_id,
                "section_title": chunk.section_title,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "doc_title": doc.title,
                "doc_version": doc.version,
            }
        ))

    # 3. Upsert to Qdrant
    store.client.upsert(
        collection_name="mcu_specs",
        points=points,
    )

    # 4. Store document metadata separately (for list_documents)
    store.store_document_metadata(doc)
```

## Storage Layer (Simplified - Qdrant Only)

### Qdrant Store

```python
# storage/qdrant_store.py
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, Filter, FieldCondition, MatchValue
import re

class QdrantStore:
    def __init__(self, url: str = "http://localhost:6333"):
        self.client = QdrantClient(url=url)
        self._ensure_collection()

    def _ensure_collection(self):
        """Create collection if not exists."""
        if not self.client.collection_exists("mcu_specs"):
            self.client.create_collection(
                collection_name="mcu_specs",
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
            )

    def search_semantic(
        self,
        query_vector: list[float],
        doc_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Semantic search via vector similarity."""
        query_filter = None
        if doc_id:
            query_filter = Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            )

        results = self.client.search(
            collection_name="mcu_specs",
            query_vector=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return [self._to_result(r) for r in results]

    def search_literal(
        self,
        query: str,
        doc_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Literal text matching (post-filter on content).

        Handles MCU symbols like GPIOx_MODER, USART_CR1, etc.
        Automatically escapes special regex characters.
        """
        # Escape special regex characters for safe matching
        escaped_query = re.escape(query)

        # Scroll through chunks and filter by content match
        # Note: This is less efficient than FTS but works for demo
        query_filter = None
        if doc_id:
            query_filter = Filter(
                must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
            )

        results, _ = self.client.scroll(
            collection_name="mcu_specs",
            query_filter=query_filter,
            limit=1000,  # Scan more for literal matching
            with_payload=True,
        )

        # Filter by literal match
        matches = []
        for r in results:
            content = r.payload.get("content", "")
            if query.lower() in content.lower():
                matches.append(self._to_result(r))
                if len(matches) >= limit:
                    break

        return matches

    def get_chunk(self, chunk_id: str) -> dict | None:
        """Get a specific chunk by ID."""
        try:
            result = self.client.retrieve(
                collection_name="mcu_specs",
                ids=[chunk_id],
                with_payload=True,
            )
            if result:
                return self._to_result(result[0])
        except Exception:
            pass
        return None

    def get_chunks_by_section(self, doc_id: str, section_id: str) -> list[dict]:
        """Get all chunks for a section."""
        query_filter = Filter(
            must=[
                FieldCondition(key="doc_id", match=MatchValue(value=doc_id)),
                FieldCondition(key="section_id", match=MatchValue(value=section_id)),
            ]
        )
        results, _ = self.client.scroll(
            collection_name="mcu_specs",
            query_filter=query_filter,
            limit=100,
            with_payload=True,
        )
        return [self._to_result(r) for r in results]

    def list_documents(self) -> list[dict]:
        """List all indexed documents."""
        # This would need a separate metadata collection or aggregation
        # For simplicity, we can store doc metadata in a separate collection
        pass
```

### Hybrid Search with RRF

```python
# storage/hybrid_search.py
def reciprocal_rank_fusion(
    literal_results: list[dict],
    semantic_results: list[dict],
    k: int = 60,
) -> list[dict]:
    """Merge results using Reciprocal Rank Fusion."""
    scores = {}
    results_by_id = {}

    for rank, result in enumerate(literal_results):
        chunk_id = result["chunk_id"]
        scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (k + rank)
        results_by_id[chunk_id] = result

    for rank, result in enumerate(semantic_results):
        chunk_id = result["chunk_id"]
        scores[chunk_id] = scores.get(chunk_id, 0) + 1 / (k + rank)
        results_by_id[chunk_id] = result

    # Sort by combined score and return full results
    sorted_ids = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [(results_by_id[id], score) for id, score in sorted_ids]
```

## Configuration

Environment variables for configuration:

```python
# config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Qdrant (Docker)
    qdrant_url: str = "http://localhost:6333"

    # Embedding API (OpenRouter)
    # Using text-embedding-3-small: 1536 dims, $0.02/1M tokens, 62.3% MTEB
    # This matches the Qdrant collection vector size (1536)
    embedding_endpoint: str = "https://openrouter.ai/api/v1"
    embedding_api_key: str | None = None
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dimensions: int = 1536  # Fixed for text-embedding-3-small

    # Storage (for PDFs and metadata)
    storage_path: str = ".mcu-specs"

    # Search
    default_search_mode: str = "hybrid"
    default_max_results: int = 5

    # Chunking
    chunk_max_chars: int = 3600
    chunk_overlap_chars: int = 200

    class Config:
        env_prefix = "MCU_SPECS_"
```

## VS Code Integration

Add to `.vscode/mcp.json`:

```json
{
	"servers": {
		"mcu-specs": {
			"command": "uv",
			"args": ["run", "--directory", "/path/to/mcp-servers/mcu-specs", "fastmcp", "run", "mcu_specs/server.py"],
			"env": {
				"MCU_SPECS_EMBEDDING_API_KEY": "${input:embeddingApiKey}",
				"MCU_SPECS_QDRANT_URL": "http://localhost:6333",
				"AID_WORKSPACE_ROOT": "${workspaceFolder}"
			}
		}
	}
}
```

## Implementation Phases

### Phase 1: Core Infrastructure (Functional First)

1. **Project Setup**

    - Create directory structure
    - Set up `pyproject.toml` with dependencies
    - Basic FastMCP server skeleton

2. **Storage Layer**

    - Qdrant client wrapper (connects to Docker)
    - Collection management
    - Document metadata collection

3. **PDF Ingestion**

    - PDF parsing with pdfplumber
    - TOC extraction (with fallback for missing bookmarks)
    - Section-aware chunking with deterministic IDs

4. **Embedding Integration**
    - Configurable embedding client
    - Batch embedding for efficiency

### Phase 2: Search Tools

5. **Literal Search**

    - Post-filter on content in Qdrant
    - Escape special chars for MCU symbols

6. **Semantic Search**

    - Qdrant vector search
    - Similarity scoring

7. **Hybrid Search**
    - RRF merge implementation

### Phase 3: Retrieval Tools

8. **Document Management**

    - `spec_list_documents`
    - `spec_get_toc`

9. **Content Retrieval**
    - `spec_get_section`
    - `spec_get_chunk`
    - `spec_get_pages` (new)

### Phase 4: Agentic Features (Optional)

10. **Intelligent QA**
    - `spec_answer` with MCP sampling
    - Citation formatting

## Testing Strategy

```python
# tests/test_server.py
import pytest
from mcu_specs.server import mcp

def test_spec_list_documents():
    result = mcp.call_tool("spec_list_documents", {})
    assert "documents" in result

def test_spec_search_literal():
    result = mcp.call_tool("spec_search", {
        "query": "GPIO_MODER",
        "mode": "literal",
        "max_results": 5,
    })
    assert len(result["results"]) <= 5

def test_spec_search_semantic():
    result = mcp.call_tool("spec_search", {
        "query": "How do I configure GPIO for output mode?",
        "mode": "semantic",
        "max_results": 5,
    })
    assert len(result["results"]) <= 5
```

## Demo Documents

The following PDFs are available in the `datasheets/` directory for demo:

| File                               | Description                                       |
| ---------------------------------- | ------------------------------------------------- |
| `dm00031020-*.pdf`                 | STM32F405/407/427/429 Reference Manual (main doc) |
| `pm0214-*.pdf`                     | STM32 Cortex-M4 Programming Manual                |
| `um1472-*.pdf`                     | Discovery Kit with STM32F407VG MCU User Manual    |
| `STM32F4DIS-BB User Manual.pdf`    | STM32F4DIS-BB board manual                        |
| `DM-STF4BB_SCH.pdf`                | STM32F4DIS-BB schematic                           |
| `mb997-f407vgt6-b02_schematic.pdf` | STM32F407VGT6 board schematic                     |
| `dm00037051.pdf`                   | Additional STM32 documentation                    |
| `p197294-dm-stf4bb.pdf`            | STM32F4DIS-BB product info                        |
| `p197297-dm-lcd35rt.pdf`           | LCD display info                                  |
| `1671412.pdf`                      | Additional documentation                          |

**Note**: Some files may be duplicates or very similar. The ingestion pipeline should handle deduplication by checking doc_id hashes.

## Next Steps

1. **User provides**: PDF documents for demo
2. **User provides**: Embedding API endpoint and key
3. **Implementation**: Create the server following this plan
4. **Testing**: Verify with demo documents
5. **Integration**: Add to Embedded Debug mode's MCP server list

## Design Decisions Summary

| Decision           | Choice                    | Rationale                                           |
| ------------------ | ------------------------- | --------------------------------------------------- |
| **Qdrant**         | Docker container          | Easiest setup, well-maintained image                |
| **SQLite**         | Not needed                | Qdrant handles both vector + payload filtering      |
| **Chunk storage**  | Qdrant payloads           | Avoid duplication, single source of truth           |
| **Async model**    | Sync tools + `to_thread`  | Simpler for demo, avoid async gotchas               |
| **Chunk IDs**      | Deterministic + hash      | Stable citations, incremental reindexing            |
| **Search modes**   | literal, semantic, hybrid | No separate "keyword" mode - literal covers symbols |
| **TOC extraction** | PDF bookmarks + fallback  | Handle missing bookmarks gracefully                 |
| **Page citations** | PDF page index            | More reliable than printed page numbers             |

## Feedback Incorporated

Based on external review feedback:

1. **Simplified architecture**: Removed SQLite, using Qdrant only
2. **Deterministic chunk IDs**: Added content hash for verification
3. **No storage duplication**: Chunks stored in Qdrant payloads only
4. **Sync tools**: Using sync tools with `asyncio.to_thread()` for blocking calls
5. **FTS query parsing**: Escaping special chars for MCU symbols (GPIOx_MODER, etc.)
6. **TOC fallback**: Handle missing PDF bookmarks
7. **Added `spec_get_pages`**: New tool for multi-page viewing
8. **Added pydantic-settings**: Missing dependency added

## Questions Resolved

- ✅ **PDF Ingestion**: Direct PDF support in server
- ✅ **Embeddings**: `openai/text-embedding-3-small` via OpenRouter (1536 dims, $0.02/1M tokens)
- ✅ **Storage**: Workspace-local `.mcu-specs/` directory
- ✅ **Initial Documents**: STM32F4 datasheets in `datasheets/` directory
- ✅ **Qdrant**: Docker container (easiest)
- ✅ **SQLite**: Not needed (Qdrant handles everything)
