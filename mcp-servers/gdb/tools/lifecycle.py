"""
GDB Session Lifecycle Tools.

Tools for starting, stopping, and managing GDB sessions.
"""

import os
import shutil
from typing import Any

from fastmcp import FastMCP

from session import SessionManager
from parsing import format_tool_response
from tools._common import tool_handler


def _detect_gdb() -> str:
    """Auto-detect best available GDB. Prefers gdb-multiarch.
    
    Returns:
        Path to GDB executable
    """
    if shutil.which("gdb-multiarch"):
        return "gdb-multiarch"
    if shutil.which("gdb"):
        return "gdb"
    raise FileNotFoundError("No GDB found. Install gdb or gdb-multiarch.")


def register_lifecycle_tools(mcp: FastMCP, session_manager: SessionManager) -> None:
    """Register all lifecycle tools with the MCP server."""
    
    @mcp.tool()
    def gdb_session_list() -> dict[str, Any]:
        """
        List all active GDB session IDs.
        
        Returns:
            Dict with list of session IDs
        """
        sessions = session_manager.list_all()
        return format_tool_response(sessions=sessions, count=len(sessions))
    
    @mcp.tool()
    @tool_handler
    async def gdb_start(
        cwd: str | None = None,
        gdb_path: str | None = None
    ) -> dict[str, Any]:
        """
        Start a new GDB session with MI2 interpreter.
        
        Args:
            cwd: Working directory for the session. 
                 Defaults to workspace root.
            gdb_path: Path to GDB executable. Auto-detects if not specified
                      (prefers gdb-multiarch, falls back to gdb).
        
        Returns:
            Dict containing session_id
        """
        workspace_root = session_manager.workspace_root
        
        # Default to workspace root
        if cwd is None:
            if workspace_root:
                cwd = workspace_root
            else:
                raise ValueError("No cwd specified and no workspace root set")
        elif not os.path.isabs(cwd):
            # Resolve relative paths against workspace root
            if workspace_root:
                cwd = os.path.join(workspace_root, cwd)
            else:
                cwd = os.path.abspath(cwd)
        
        cwd = os.path.abspath(cwd)
        
        # Auto-detect GDB if not specified
        if gdb_path is None:
            gdb_path = _detect_gdb()
        
        session = await session_manager.create(gdb_path=gdb_path, cwd=cwd)
        
        return format_tool_response(session_id=session.session_id)
    
    @mcp.tool()
    @tool_handler
    async def gdb_stop(session_id: str) -> dict[str, Any]:
        """
        Stop a GDB session.
        
        Args:
            session_id: The ID of the GDB session to stop
        
        Returns:
            Dict containing session_id
        """
        await session_manager.stop(session_id)
        return format_tool_response(session_id=session_id)
