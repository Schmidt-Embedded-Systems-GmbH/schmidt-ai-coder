#!/usr/bin/env python3
"""
Batch ingest all PDFs from the datasheets directory.

Usage:
    cd mcp-servers/mcu-specs
    uv run python scripts/ingest_all.py
    
Cost estimate:
    - OpenRouter text-embedding-3-small: $0.02/1M tokens
    - Typical datasheet: ~500k tokens
    - 10 datasheets: ~$0.10 total
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcu_specs.server import spec_ingest


# Default datasheets directory (relative to project root)
DEFAULT_DATASHEETS_DIR = Path(__file__).parent.parent.parent.parent / "datasheets"


async def ingest_all(datasheets_dir: Path | None = None):
    """Ingest all PDFs from the datasheets directory."""
    if datasheets_dir is None:
        datasheets_dir = DEFAULT_DATASHEETS_DIR
    
    if not datasheets_dir.exists():
        print(f"Error: Datasheets directory not found: {datasheets_dir}")
        sys.exit(1)
    
    pdfs = list(datasheets_dir.glob("*.pdf"))
    if not pdfs:
        print(f"No PDF files found in {datasheets_dir}")
        sys.exit(0)
    
    print(f"Found {len(pdfs)} PDF files to ingest")
    print(f"Estimated cost: ~${len(pdfs) * 0.01:.2f} (assuming ~500k tokens per PDF)")
    print()
    
    # Check for OPENROUTER_API_KEY
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("Error: OPENROUTER_API_KEY environment variable not set")
        print("Set it with: export OPENROUTER_API_KEY='your-key'")
        sys.exit(1)
    
    # Check Qdrant
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:6333/collections", timeout=5.0)
            if resp.status_code != 200:
                print("Error: Qdrant not responding properly")
                sys.exit(1)
    except Exception as e:
        print(f"Error: Cannot connect to Qdrant at localhost:6333")
        print(f"Start it with: docker run -p 6333:6333 qdrant/qdrant")
        sys.exit(1)
    
    print("Ingesting PDFs...")
    print("-" * 60)
    
    results = []
    for pdf_path in pdfs:
        doc_id = pdf_path.stem.replace(" ", "_").replace("-", "_")
        print(f"\nIngesting: {pdf_path.name}")
        print(f"  Doc ID: {doc_id}")
        
        try:
            result = await spec_ingest(str(pdf_path), doc_id)
            status = result.get("status", "unknown")
            if status == "success":
                print(f"  ✓ Success: {result.get('total_chunks', 0)} chunks, {result.get('sections', 0)} sections")
            elif status == "skipped":
                print(f"  ⊘ Skipped: {result.get('reason', 'already indexed')}")
            else:
                print(f"  ✗ Error: {result.get('error', result.get('reason', 'unknown error'))}")
            results.append((pdf_path.name, status, result))
        except Exception as e:
            print(f"  ✗ Exception: {e}")
            results.append((pdf_path.name, "error", {"error": str(e)}))
    
    print()
    print("=" * 60)
    print("Summary:")
    success = sum(1 for _, status, _ in results if status == "success")
    skipped = sum(1 for _, status, _ in results if status == "skipped")
    errors = sum(1 for _, status, _ in results if status in ("error", None))
    
    print(f"  Successful: {success}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")
    
    if errors > 0:
        print("\nFailed files:")
        for name, status, result in results:
            if status in ("error", None):
                print(f"  - {name}: {result.get('error', result.get('reason', 'unknown'))}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Batch ingest PDFs into MCU Specs")
    parser.add_argument(
        "--dir", "-d",
        type=Path,
        default=None,
        help=f"Directory containing PDFs (default: {DEFAULT_DATASHEETS_DIR})",
    )
    
    args = parser.parse_args()
    asyncio.run(ingest_all(args.dir))