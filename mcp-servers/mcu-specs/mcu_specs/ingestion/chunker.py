"""Section-aware chunking for MCU datasheets."""

import hashlib
from dataclasses import dataclass
from typing import Optional

from ..models import Chunk, Section
from .pdf_parser import ParsedPDF, PageContent


@dataclass
class ChunkingConfig:
    """Configuration for chunking."""
    chunk_size: int = 800  # Target characters per chunk
    chunk_overlap: int = 100  # Overlap between chunks
    min_chunk_size: int = 100  # Minimum chunk size (smaller chunks are merged)


class Chunker:
    """Section-aware text chunker for MCU datasheets.
    
    Features:
    - Respects section boundaries when possible
    - Maintains page number tracking
    - Generates deterministic chunk IDs
    - Handles tables and code blocks specially
    """
    
    def __init__(self, config: Optional[ChunkingConfig] = None):
        """Initialize chunker.
        
        Args:
            config: Chunking configuration (uses defaults if not provided)
        """
        self.config = config or ChunkingConfig()
    
    def chunk(self, parsed: ParsedPDF) -> list[Chunk]:
        """Chunk a parsed PDF into smaller pieces.
        
        Args:
            parsed: Parsed PDF content
            
        Returns:
            List of Chunk objects
        """
        chunks = []
        
        # Build page lookup
        pages_by_num = {p.page_num: p for p in parsed.pages}
        
        # Process each section
        for section in parsed.sections:
            section_chunks = self._chunk_section(
                parsed.doc_id,
                section,
                pages_by_num,
            )
            chunks.extend(section_chunks)
        
        # Handle content outside sections (front matter, etc.)
        orphan_chunks = self._chunk_orphan_content(
            parsed.doc_id,
            parsed.pages,
            parsed.sections,
        )
        chunks.extend(orphan_chunks)
        
        # Sort by chunk_id for consistent ordering
        chunks.sort(key=lambda c: c.chunk_id)
        
        return chunks
    
    def _chunk_section(
        self,
        doc_id: str,
        section: Section,
        pages_by_num: dict[int, PageContent],
    ) -> list[Chunk]:
        """Chunk a single section."""
        chunks = []
        
        # Gather all text for this section
        section_text = ""
        page_start = section.page_start
        page_end = section.page_end
        
        for page_num in range(page_start, min(page_end + 1, max(pages_by_num.keys()) + 1)):
            page = pages_by_num.get(page_num)
            if page:
                section_text += f"\n[PAGE {page_num}]\n{page.text}"
        
        if not section_text.strip():
            return chunks
        
        # Split into chunks
        text_chunks = self._split_text(section_text)
        
        for i, text in enumerate(text_chunks):
            chunk_id = self._generate_chunk_id(
                doc_id=doc_id,
                section_id=section.section_id,
                page_start=page_start,
                page_end=page_end,
                index=i,
                content=text,
            )
            
            # Determine actual page range for this chunk
            chunk_page_start, chunk_page_end = self._extract_page_range(text)
            
            chunks.append(Chunk(
                chunk_id=chunk_id,
                doc_id=doc_id,
                content=text.strip(),
                section_id=section.section_id,
                section_title=section.title,
                page_start=chunk_page_start or page_start,
                page_end=chunk_page_end or page_end,
                chunk_index=i,
                content_hash=self._hash_content(text),
            ))
        
        return chunks
    
    def _chunk_orphan_content(
        self,
        doc_id: str,
        pages: list[PageContent],
        sections: list[Section],
    ) -> list[Chunk]:
        """Chunk content not covered by any section."""
        # Find pages not covered by sections
        covered_pages = set()
        for section in sections:
            for page in range(section.page_start, section.page_end + 1):
                covered_pages.add(page)
        
        orphan_pages = [p for p in pages if p.page_num not in covered_pages]
        
        if not orphan_pages:
            return []
        
        chunks = []
        for page in orphan_pages:
            if not page.text.strip():
                continue
            
            text_chunks = self._split_text(page.text)
            for i, text in enumerate(text_chunks):
                chunk_id = self._generate_chunk_id(
                    doc_id=doc_id,
                    section_id="frontmatter",
                    page_start=page.page_num,
                    page_end=page.page_num,
                    index=i,
                    content=text,
                )
                
                chunks.append(Chunk(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    content=text.strip(),
                    section_id="frontmatter",
                    section_title="Front Matter",
                    page_start=page.page_num,
                    page_end=page.page_num,
                    chunk_index=i,
                    content_hash=self._hash_content(text),
                ))
        
        return chunks
    
    def _split_text(self, text: str) -> list[str]:
        """Split text into chunks respecting boundaries.
        
        Tries to split on paragraph boundaries when possible.
        """
        if len(text) <= self.config.chunk_size:
            return [text]
        
        chunks = []
        paragraphs = text.split("\n\n")
        
        current_chunk = ""
        for para in paragraphs:
            # Check if adding this paragraph would exceed chunk size
            if len(current_chunk) + len(para) + 2 > self.config.chunk_size:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                
                # If paragraph itself is too large, split it
                if len(para) > self.config.chunk_size:
                    sub_chunks = self._split_large_paragraph(para)
                    chunks.extend(sub_chunks[:-1])
                    current_chunk = sub_chunks[-1] if sub_chunks else ""
                else:
                    current_chunk = para
            else:
                current_chunk += "\n\n" + para if current_chunk else para
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        # Merge very small chunks with neighbors
        chunks = self._merge_small_chunks(chunks)
        
        return chunks
    
    def _split_large_paragraph(self, text: str) -> list[str]:
        """Split a large paragraph on sentence boundaries."""
        chunks = []
        
        # Try sentence boundaries first
        sentences = []
        current = ""
        for char in text:
            current += char
            if char in ".!?" and len(current) >= self.config.chunk_size // 2:
                sentences.append(current)
                current = ""
        
        if current:
            sentences.append(current)
        
        if len(sentences) > 1:
            # Merge sentences into chunks
            current_chunk = ""
            for sent in sentences:
                if len(current_chunk) + len(sent) > self.config.chunk_size:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sent
                else:
                    current_chunk += sent
            if current_chunk:
                chunks.append(current_chunk.strip())
        else:
            # Fall back to hard split
            for i in range(0, len(text), self.config.chunk_size - self.config.chunk_overlap):
                chunks.append(text[i:i + self.config.chunk_size])
        
        return chunks
    
    def _merge_small_chunks(self, chunks: list[str]) -> list[str]:
        """Merge chunks that are too small with neighbors."""
        if len(chunks) <= 1:
            return chunks
        
        merged = []
        i = 0
        while i < len(chunks):
            chunk = chunks[i]
            
            # If chunk is too small and there's a next chunk, merge
            while (len(chunk) < self.config.min_chunk_size and 
                   i + 1 < len(chunks) and
                   len(chunk) + len(chunks[i + 1]) < self.config.chunk_size * 1.5):
                i += 1
                chunk += "\n\n" + chunks[i]
            
            merged.append(chunk)
            i += 1
        
        return merged
    
    def _generate_chunk_id(
        self,
        doc_id: str,
        section_id: str,
        page_start: int,
        page_end: int,
        index: int,
        content: str,
    ) -> str:
        """Generate deterministic chunk ID.
        
        Format: {doc_id}|{section_id}|p{page_start}-p{page_end}|i{index:04d}|h{content_hash}
        """
        content_hash = self._hash_content(content)[:8]
        return f"{doc_id}|{section_id}|p{page_start}-p{page_end}|i{index:04d}|h{content_hash}"
    
    def _hash_content(self, content: str) -> str:
        """Generate SHA-256 hash of content."""
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _extract_page_range(self, text: str) -> tuple[Optional[int], Optional[int]]:
        """Extract page range from [PAGE N] markers in text."""
        import re
        markers = re.findall(r'\[PAGE (\d+)\]', text)
        if markers:
            pages = [int(m) for m in markers]
            return min(pages), max(pages)
        return None, None
