"""PDF parsing for MCU datasheets and reference manuals."""

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pdfplumber

from ..models import Document, Section


@dataclass
class PageContent:
    """Content extracted from a single PDF page."""
    page_num: int
    text: str
    width: float
    height: float


@dataclass
class ParsedPDF:
    """Result of parsing a PDF file."""
    doc_id: str
    title: str
    filename: str
    total_pages: int
    pages: list[PageContent] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    file_hash: str = ""


class PDFParser:
    """Parse PDF datasheets and extract structure."""
    
    # Common section patterns in MCU datasheets
    SECTION_PATTERNS = [
        # STM32 style: "3.1 GPIO modes"
        re.compile(r'^(\d+(?:\.\d+)*)\s+([A-Z][^\n]+?)(?:\s*$)', re.MULTILINE),
        # Alternative: "Section 3.1: GPIO modes"
        re.compile(r'^[Ss]ection\s+(\d+(?:\.\d+)*)\s*[:\-]?\s*([A-Z][^\n]+?)(?:\s*$)', re.MULTILINE),
    ]
    
    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 100):
        """Initialize PDF parser.
        
        Args:
            chunk_size: Target size for text chunks (characters)
            chunk_overlap: Overlap between chunks (characters)
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def parse(self, pdf_path: Path, doc_id: Optional[str] = None) -> ParsedPDF:
        """Parse a PDF file.
        
        Args:
            pdf_path: Path to PDF file
            doc_id: Optional document ID (defaults to filename stem)
            
        Returns:
            ParsedPDF with extracted content and structure
        """
        pdf_path = Path(pdf_path)
        doc_id = doc_id or pdf_path.stem
        
        # Calculate file hash for deduplication
        file_hash = self._hash_file(pdf_path)
        
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            
            # Extract title from first page or metadata
            title = self._extract_title(pdf)
            
            # Extract all pages
            pages = []
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                pages.append(PageContent(
                    page_num=i + 1,
                    text=text,
                    width=page.width,
                    height=page.height,
                ))
            
            # Extract sections from TOC or by pattern matching
            sections = self._extract_sections(pdf, pages)
        
        return ParsedPDF(
            doc_id=doc_id,
            title=title,
            filename=pdf_path.name,
            total_pages=total_pages,
            pages=pages,
            sections=sections,
            file_hash=file_hash,
        )
    
    def _hash_file(self, path: Path) -> str:
        """Calculate SHA-256 hash of file."""
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()[:16]
    
    def _extract_title(self, pdf) -> str:
        """Extract document title from PDF metadata or first page."""
        # Try metadata first
        if pdf.metadata and pdf.metadata.get("Title"):
            return pdf.metadata["Title"]
        
        # Try first page
        if pdf.pages:
            first_page = pdf.pages[0]
            text = first_page.extract_text() or ""
            # Look for title-like text at the start
            lines = text.split("\n")
            for line in lines[:5]:  # Check first 5 lines
                line = line.strip()
                if line and len(line) > 5 and len(line) < 100:
                    # Likely a title
                    return line
        
        return "Unknown Title"
    
    def _extract_sections(self, pdf, pages: list[PageContent]) -> list[Section]:
        """Extract sections from TOC or by pattern matching.
        
        Prefers TOC (bookmarks) if available, falls back to pattern matching.
        """
        sections = []
        
        # Try TOC first
        toc = pdf.outline if hasattr(pdf, 'outline') else None
        if toc:
            sections = self._parse_toc(toc)
        
        # Fall back to pattern matching if no TOC or empty
        if not sections:
            sections = self._extract_sections_by_pattern(pages)
        
        return sections
    
    def _parse_toc(self, toc: list) -> list[Section]:
        """Parse PDF table of contents (bookmarks)."""
        sections = []
        
        def walk_toc(items: list, parent_id: str = ""):
            for item in items:
                if isinstance(item, dict):
                    title = item.get("title", "").strip()
                    page = item.get("page", 0)
                    if isinstance(page, int):
                        page_num = page
                    elif isinstance(page, str):
                        # Sometimes page is a string
                        try:
                            page_num = int(page)
                        except ValueError:
                            page_num = 0
                    else:
                        page_num = 0
                    
                    # Generate section ID from title
                    section_id = self._title_to_section_id(title, parent_id)
                    
                    if title and page_num > 0:
                        sections.append(Section(
                            section_id=section_id,
                            title=title,
                            page_start=page_num,
                            page_end=page_num,  # Will be updated later
                            level=title.count(".") + 1 if "." in title else 1,
                        ))
                    
                    # Recurse into children
                    children = item.get("children", [])
                    if children:
                        walk_toc(children, section_id)
                elif isinstance(item, (list, tuple)):
                    # Some PDFs have nested lists
                    walk_toc(item, parent_id)
        
        walk_toc(toc)
        
        # Sort by page and update page_end values
        sections.sort(key=lambda s: s.page_start)
        for i in range(len(sections) - 1):
            sections[i].page_end = sections[i + 1].page_start - 1
        if sections:
            sections[-1].page_end = 9999  # Last section extends to end
        
        return sections
    
    def _extract_sections_by_pattern(self, pages: list[PageContent]) -> list[Section]:
        """Extract sections by pattern matching on page text."""
        sections = []
        
        for page in pages:
            for pattern in self.SECTION_PATTERNS:
                for match in pattern.finditer(page.text):
                    section_num = match.group(1)
                    section_title = match.group(2).strip()
                    
                    # Skip very short titles (likely false positives)
                    if len(section_title) < 3:
                        continue
                    
                    sections.append(Section(
                        section_id=section_num,
                        title=f"{section_num} {section_title}",
                        page_start=page.page_num,
                        page_end=page.page_num,
                        level=section_num.count(".") + 1,
                    ))
        
        # Deduplicate and sort
        seen = set()
        unique_sections = []
        for s in sections:
            key = s.section_id
            if key not in seen:
                seen.add(key)
                unique_sections.append(s)
        
        unique_sections.sort(key=lambda s: (s.page_start, s.section_id))
        
        # Update page_end values
        for i in range(len(unique_sections) - 1):
            unique_sections[i].page_end = unique_sections[i + 1].page_start - 1
        if unique_sections:
            unique_sections[-1].page_end = 9999
        
        return unique_sections
    
    def _title_to_section_id(self, title: str, parent_id: str = "") -> str:
        """Convert section title to section ID.
        
        Examples:
            "3.1 GPIO modes" -> "3.1"
            "Section 3.1: GPIO modes" -> "3.1"
        """
        # Try to extract section number from title
        match = re.match(r'^[Ss]ection\s+(\d+(?:\.\d+)*)', title)
        if match:
            return match.group(1)
        
        match = re.match(r'^(\d+(?:\.\d+)*)', title)
        if match:
            return match.group(1)
        
        # Fall back to slugified title
        slug = re.sub(r'[^a-zA-Z0-9]+', '-', title.lower()).strip('-')
        return slug[:30]
    
    def to_document(self, parsed: ParsedPDF) -> Document:
        """Convert ParsedPDF to Document model."""
        return Document(
            doc_id=parsed.doc_id,
            title=parsed.title,
            filename=parsed.filename,
            total_pages=parsed.total_pages,
            file_hash=parsed.file_hash,
            sections=parsed.sections,
        )
