# mcp-cmsis-svd - CMSIS-SVD MCP Server for embedded debugging
#
# This package provides an MCP server that exposes CMSIS-SVD device metadata
# to LLM agents for embedded debugging in VS Code.

__version__ = "0.1.0"

from mcp_cmsis_svd.server import mcp

__all__ = ["mcp", "__version__"]