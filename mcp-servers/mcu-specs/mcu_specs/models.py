"""Pydantic models for MCU Specs MCP Server API."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Document(BaseModel):
    """Represents an indexed document."""
    doc_id: str = Field(..., description="Unique document identifier")
    title: str = Field(..., description="Document title")
    filename: str = Field(..., description="Original filename")
    version: Optional[str] = Field(None, description="Document version")
    total_pages: int = Field(..., description="Number of pages")
    indexed_at: datetime = Field(default_factory=datetime.utcnow, description="Indexing timestamp")
    file_hash: str = Field(..., description="SHA256 hash of file for deduplication")
    sections: list["Section"] = Field(default_factory=list, description="Table of contents")


class Section(BaseModel):
    """Represents a document section (from TOC)."""
    section_id: str = Field(..., description="Section identifier (e.g., '11.4.2')")
    title: str = Field(..., description="Section title")
    page_start: int = Field(..., description="Starting page (PDF index)")
    page_end: int = Field(..., description="Ending page (PDF index)")
    level: int = Field(default=1, description="Section depth level")
    children: list["Section"] = Field(default_factory=list, description="Child sections")


class Chunk(BaseModel):
    """Represents a text chunk for indexing."""
    chunk_id: str = Field(..., description="Deterministic chunk ID")
    doc_id: str = Field(..., description="Parent document ID")
    content: str = Field(..., description="Chunk text content")
    section_id: Optional[str] = Field(None, description="Section ID")
    section_title: Optional[str] = Field(None, description="Section title")
    page_start: int = Field(..., description="Starting page (PDF index)")
    page_end: int = Field(..., description="Ending page (PDF index)")
    chunk_index: int = Field(..., description="Index within section")
    content_hash: str = Field(..., description="Hash of content for verification")


class SearchResult(BaseModel):
    """A single search result."""
    chunk_id: str
    doc_id: str
    content: str
    score: float = Field(..., ge=0.0, le=1.0)
    source: str = Field(..., description="Human-readable citation")
    section_id: Optional[str] = None
    section_title: Optional[str] = None
    page: int
    doc_title: Optional[str] = None


class SearchResponse(BaseModel):
    """Response from spec_search tool."""
    results: list[SearchResult]
    total_found: int
    tokens_estimate: int = Field(..., description="Estimated tokens in results")
    mode: str = Field(..., description="Search mode used")
    query: str = Field(..., description="Original query")


class PageContent(BaseModel):
    """Content of a single page."""
    page_index: int = Field(..., description="PDF page index (0-based)")
    printed_page: Optional[str] = Field(None, description="Printed page number if available")
    content: str = Field(..., description="Page text content")
    has_tables: bool = Field(default=False, description="Whether page contains tables")


class PagesResponse(BaseModel):
    """Response from spec_get_pages tool."""
    doc_id: str
    pages: list[PageContent]


class TOCResponse(BaseModel):
    """Response from spec_get_toc tool."""
    doc_id: str
    title: str
    sections: list[Section]


class DocumentListResponse(BaseModel):
    """Response from spec_list_documents tool."""
    documents: list[Document]
    total_count: int


class ChunkResponse(BaseModel):
    """Response from spec_get_chunk tool."""
    chunk_id: str
    doc_id: str
    content: str
    section_id: Optional[str] = None
    section_title: Optional[str] = None
    page_start: int
    page_end: int
    doc_title: Optional[str] = None
    source: str = Field(..., description="Human-readable citation")


class SectionResponse(BaseModel):
    """Response from spec_get_section tool."""
    doc_id: str
    section_id: str
    section_title: Optional[str] = None
    content: str
    page_start: int
    page_end: int
    total_chars: int
    truncated: bool = Field(default=False, description="Whether content was truncated")


# Update forward references
Section.model_rebuild()
