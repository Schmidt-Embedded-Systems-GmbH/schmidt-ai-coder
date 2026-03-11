# MCU Specs MCP Server

A spec search engine for microcontroller datasheets, reference manuals, and technical documentation. Provides semantic and literal search capabilities through the Model Context Protocol (MCP).

## Features

- **Hybrid Search**: Combines semantic (vector) and literal (text) search with Reciprocal Rank Fusion
- **Section-Aware Chunking**: Respects document structure for better context
- **Page Tracking**: Every chunk knows its source pages
- **MCU Symbol Support**: Handles register names like `GPIOx_MODER`, `USART_CR1`, etc.
- **PDF Ingestion**: Parse and index PDF datasheets with TOC extraction

## Installation

```bash
cd mcp-servers/mcu-specs
uv sync
```

## Configuration

Set the following environment variables:

```bash
# Required: OpenRouter API key for embeddings
export OPENROUTER_API_KEY="your-api-key"

# Optional: Qdrant URL (default: http://localhost:6333)
export QDRANT_URL="http://localhost:6333"
```

### Qdrant Setup

Run Qdrant in Docker:

```bash
docker run -p 6333:6333 qdrant/qdrant
```

## Usage

### Running the Server

```bash
uv run mcu-specs
```

### MCP Tools

| Tool                   | Description                          |
| ---------------------- | ------------------------------------ |
| `spec_list_documents`  | List all indexed documents           |
| `spec_get_toc`         | Get table of contents for a document |
| `spec_search`          | Hybrid search across all documents   |
| `spec_get_section`     | Get all chunks from a section        |
| `spec_get_chunk`       | Get a specific chunk by ID           |
| `spec_get_pages`       | Get content from specific pages      |
| `spec_ingest`          | Ingest a new PDF document            |
| `spec_delete_document` | Delete a document from the index     |

---

## Datasheet Ingestion Workflow

### How It Works

1. **PDF Parsing**: Extracts text, table of contents (TOC), and page structure using `pdfplumber`
2. **Section-Aware Chunking**: Splits content into ~800 char chunks, respecting section boundaries
3. **Embedding Generation**: Creates vector embeddings via OpenRouter API (`text-embedding-3-small`)
4. **Storage**: Stores chunks with embeddings in Qdrant for fast semantic search

### Ingesting Datasheets

#### Option 1: Via MCP Tool (Recommended)

Use the `spec_ingest` tool from your AI assistant:

```
# In Kilo Code / AI assistant
spec_ingest(pdf_path="/path/to/datasheet.pdf", doc_id="STM32F427_RM")
```

#### Option 2: Via HTTP API (for scripting)

```bash
# Start server in HTTP mode
cd mcp-servers/mcu-specs
uv run fastmcp run main.py -t http -p 8009

# Ingest via HTTP (using MCP protocol)
curl -X POST http://localhost:8009/mcp/tools/spec_ingest \
  -H "Content-Type: application/json" \
  -d '{"pdf_path": "/path/to/datasheet.pdf", "doc_id": "MyDoc"}'
```

#### Option 3: Via Python Script (for batch ingestion)

```python
# scripts/ingest_datasheets.py
import asyncio
import sys
sys.path.insert(0, "/path/to/mcp-servers/mcu-specs")

from mcu_specs.server import spec_ingest

async def main():
    datasheets = [
        ("/path/to/rm0090-stm32f4.pdf", "STM32F4_RM0090"),
        ("/path/to/dm00031020.pdf", "STM32F427_RM"),
    ]

    for pdf_path, doc_id in datasheets:
        result = await spec_ingest(pdf_path, doc_id)
        print(f"{doc_id}: {result}")

asyncio.run(main())
```

### Example Usage

```python
# In your MCP client (e.g., Kilo Code)

# List indexed documents
spec_list_documents()

# Search for GPIO configuration
spec_search(query="GPIO mode configuration", mode="hybrid")

# Search for exact register
spec_search(query="GPIOx_MODER", mode="literal")

# Get section content
spec_get_section(doc_id="STM32F427_Reference_Manual", section_id="3.1")

# Ingest a new datasheet
spec_ingest(pdf_path="/path/to/datasheet.pdf", doc_id="MyMCU_Reference_Manual")
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      MCP Server                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Tools     │  │  Resources  │  │     Prompts         │  │
│  │  (search,   │  │  (docs,     │  │  (debugging,       │  │
│  │   ingest)   │  │   chunks)   │  │   analysis)        │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
└─────────┼────────────────┼───────────────────┼──────────────┘
          │                │                   │
          ▼                ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                    Storage Layer                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Qdrant Vector Store                     │    │
│  │  • Chunks collection (with embeddings)               │    │
│  │  • Documents collection (metadata only)              │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                   Ingestion Pipeline                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │  PDF Parser  │─▶│   Chunker    │─▶│ Embedding Client │   │
│  │  (pdfplumber)│  │ (section-    │  │  (OpenRouter)    │   │
│  │              │  │  aware)      │  │                  │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Search Modes

### Semantic Search

Best for conceptual queries:

- "How to configure UART for 115200 baud"
- "Power saving modes in sleep"
- "DMA transfer configuration"

### Literal Search

Best for exact symbol matching:

- `GPIOx_MODER`
- `USART_CR1_TE`
- `RCC_CFGR_SW`

### Hybrid Search (Default)

Combines both with Reciprocal Rank Fusion for best results.

## Chunk ID Format

Chunks use deterministic IDs for deduplication:

```
{doc_id}|{section_id}|p{page_start}-p{page_end}|i{index:04d}|h{content_hash}
```

Example:

```
STM32F427_RM|3.1|p45-p47|i0002|h8a3f2c1b
```

## Development

### Project Structure

```
mcp-servers/mcu-specs/
├── main.py                 # Entry point
├── pyproject.toml          # Project config
├── mcu_specs/
│   ├── __init__.py
│   ├── config.py           # Settings (pydantic-settings)
│   ├── models.py           # Pydantic models
│   ├── server.py           # FastMCP server & tools
│   ├── embedding/
│   │   ├── __init__.py
│   │   └── client.py       # OpenRouter embedding client
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── pdf_parser.py   # PDF parsing with pdfplumber
│   │   └── chunker.py      # Section-aware chunking
│   └── storage/
│       ├── __init__.py
│       └── qdrant_store.py # Qdrant storage layer
└── README.md
```

### Running Tests

```bash
uv run pytest
```

## License

MIT
