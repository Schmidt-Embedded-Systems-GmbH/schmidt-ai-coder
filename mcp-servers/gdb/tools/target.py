"""
GDB Target Tools.

Tools for loading executables, attaching to processes, and loading core dumps.
"""

import os
from typing import Any

from fastmcp import FastMCP

from session import SessionManager
from mi import send_command
from parsing import format_tool_response
from tools._common import tool_handler


def register_target_tools(mcp: FastMCP, session_manager: SessionManager) -> None:
    """Register all target tools with the MCP server."""
    
    @mcp.tool()
    @tool_handler
    async def gdb_load(
        session_id: str,
        executable: str
    ) -> dict[str, Any]:
        """
        Load an executable file into a GDB session.
        
        Args:
            session_id: The GDB session ID
            executable: Path to executable (relative to session cwd or absolute)
        """
        session = await session_manager.get(session_id)
        
        if os.path.isabs(executable):
            exe_path = executable
        else:
            exe_path = os.path.join(session.cwd, executable)
        
        exe_path = os.path.normpath(os.path.abspath(exe_path))
        
        if not os.path.exists(exe_path):
            return format_tool_response(status="failed", session_id=session_id, error=f"Not found: {exe_path}")
        
        if not os.path.isfile(exe_path):
            return format_tool_response(status="failed", session_id=session_id, error=f"Not a file: {exe_path}")
        
        response = await send_command(session, f'-file-exec-and-symbols "{exe_path}"')
        
        if response.is_success:
            session.target = exe_path
            return format_tool_response(session_id=session_id)
        else:
            return format_tool_response(status="failed", session_id=session_id, error=response.error_message)
    
    @mcp.tool()
    @tool_handler
    async def gdb_attach(
        session_id: str,
        pid: int
    ) -> dict[str, Any]:
        """
        Attach to a running process by PID.
        
        Args:
            session_id: The GDB session ID
            pid: Process ID to attach to
        """
        session = await session_manager.get(session_id)
        
        response = await send_command(session, f"-target-attach {pid}")
        
        if response.is_success:
            session.target = f"pid:{pid}"
            return format_tool_response(session_id=session_id)
        else:
            return format_tool_response(status="failed", session_id=session_id, error=response.error_message)
    
    @mcp.tool()
    @tool_handler
    async def gdb_detach(session_id: str) -> dict[str, Any]:
        """
        Detach from the currently attached process.
        
        Args:
            session_id: The GDB session ID
        """
        session = await session_manager.get(session_id)
        
        response = await send_command(session, "-target-detach")
        
        if response.is_success:
            return format_tool_response(session_id=session_id)
        else:
            return format_tool_response(status="failed", session_id=session_id, error=response.error_message)
    
    @mcp.tool()
    @tool_handler
    async def gdb_core_dump(
        session_id: str,
        core_file: str
    ) -> dict[str, Any]:
        """
        Load a core dump file for post-mortem debugging.
        
        Args:
            session_id: The GDB session ID
            core_file: Path to core dump (relative to session cwd or absolute)
        """
        session = await session_manager.get(session_id)
        
        if os.path.isabs(core_file):
            core_path = core_file
        else:
            core_path = os.path.join(session.cwd, core_file)
        
        core_path = os.path.normpath(os.path.abspath(core_path))
        
        if not os.path.exists(core_path):
            return format_tool_response(status="failed", session_id=session_id, error=f"Not found: {core_path}")
        
        if not os.path.isfile(core_path):
            return format_tool_response(status="failed", session_id=session_id, error=f"Not a file: {core_path}")
        
        response = await send_command(session, f'-target-select core "{core_path}"')
        
        if response.is_success:
            return format_tool_response(session_id=session_id)
        else:
            return format_tool_response(status="failed", session_id=session_id, error=response.error_message)
