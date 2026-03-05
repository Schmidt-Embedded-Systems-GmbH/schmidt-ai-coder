"""Embedding client using OpenRouter API."""

import os
from typing import Optional
import httpx

from ..config import settings


class EmbeddingClient:
    """Client for generating embeddings via OpenRouter API."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """Initialize embedding client.
        
        Args:
            api_key: OpenRouter API key (defaults to OPENROUTER_API_KEY env var)
            endpoint: API endpoint (defaults to settings.embedding_endpoint)
            model: Embedding model (defaults to settings.embedding_model)
        """
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OpenRouter API key required (set OPENROUTER_API_KEY env var)")
        
        self.endpoint = endpoint or settings.embedding_endpoint
        self.model = model or settings.embedding_model
        self.dimensions = settings.embedding_dimensions
    
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors (same order as input)
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.endpoint}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": texts,
                    "dimensions": self.dimensions,
                },
            )
            response.raise_for_status()
            data = response.json()
        
        # Extract embeddings in order
        embeddings = []
        for item in sorted(data["data"], key=lambda x: x["index"]):
            embeddings.append(item["embedding"])
        
        return embeddings
    
    async def embed_one(self, text: str) -> list[float]:
        """Generate embedding for a single text.
        
        Args:
            text: Text string to embed
            
        Returns:
            Embedding vector
        """
        embeddings = await self.embed([text])
        return embeddings[0]


# Global client instance
_client: Optional[EmbeddingClient] = None


def get_embedding_client() -> EmbeddingClient:
    """Get or create the global EmbeddingClient instance."""
    global _client
    if _client is None:
        _client = EmbeddingClient()
    return _client
