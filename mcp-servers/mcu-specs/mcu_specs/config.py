"""Configuration for MCU Specs MCP Server."""

import os
from pydantic import ConfigDict
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Server configuration from environment variables."""
    
    model_config = ConfigDict(
        env_prefix="MCU_SPECS_",
        env_file=".env",
        extra="ignore",
    )
    
    # Qdrant (Docker)
    qdrant_url: str = "http://localhost:6333"
    
    # Embedding API (OpenRouter)
    # Using text-embedding-3-small: 1536 dims, $0.02/1M tokens, 62.3% MTEB
    # This matches the Qdrant collection vector size (1536)
    embedding_endpoint: str = "https://openrouter.ai/api/v1"
    embedding_api_key: Optional[str] = None
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
    
    # Workspace root (set by VS Code extension)
    workspace_root: Optional[str] = None
    
    @property
    def qdrant_storage_path(self) -> str:
        """Get the Qdrant storage path within the storage directory."""
        return os.path.join(self.storage_path, "qdrant")
    
    @property
    def pdfs_path(self) -> str:
        """Get the PDFs storage path."""
        return os.path.join(self.storage_path, "pdfs")


# Global settings instance
settings = Settings()

# Also check for AID_WORKSPACE_ROOT (set by VS Code extension)
if not settings.workspace_root:
    workspace = os.environ.get("AID_WORKSPACE_ROOT")
    if workspace:
        settings.workspace_root = os.path.abspath(workspace)
