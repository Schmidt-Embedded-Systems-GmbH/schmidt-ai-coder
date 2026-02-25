"""
GDB Memory Tools.

Unified memory operations: read and write memory at specified addresses.
"""

from typing import Any

from fastmcp import FastMCP

from session import SessionManager
from mi import send_command
from parsing import format_tool_response, parse_memory
from tools._common import tool_handler


def register_memory_tools(mcp: FastMCP, session_manager: SessionManager) -> None:
    """Register memory tools with the MCP server."""
    
    @mcp.tool()
    @tool_handler
    async def gdb_memory(
        session_id: str,
        action: str,
        address: str,
        count: int = 1,
        value: str | None = None,
        verbose: bool = False
    ) -> dict[str, Any]:
        """
        Read or write memory at a specified address.
        
        Args:
            session_id: The GDB session ID
            action: "read" or "write"
            address: Memory address (e.g., "0x1234", "&variable", "$sp")
            count: For read: number of bytes to read (max 10000)
            value: For write: value to write
            verbose: Include raw GDB response
            
        Note: Read returns hex. For other formats use gdb_command("x/Nfb ADDR").
        """
        session = await session_manager.get(session_id)
        action = action.lower()
        
        if action == "read":
            return await _read_memory(session, session_id, address, count, verbose)
        elif action == "write":
            return await _write_memory(session, session_id, address, value)
        else:
            return format_tool_response(status="failed", session_id=session_id, error=f"Unknown action: {action}")


async def _read_memory(session, session_id, address, count, verbose):
    """Read memory at the specified address (hex format)."""
    if count <= 0 or count > 10000:
        return format_tool_response(status="failed", session_id=session_id, error="Count must be 1-10000")
    
    command = f"-data-read-memory {address} x 1 1 {count}"
    response = await send_command(session, command)
    
    if response.is_success:
        result = format_tool_response(session_id=session_id, data=parse_memory(response.raw))
        if verbose:
            result["raw_response"] = response.raw
        return result
    else:
        error_msg = response.error_message
        if "Cannot access memory" in error_msg or "Unable to read memory" in error_msg:
            error_msg = f"Cannot access memory at {address}"
        return format_tool_response(status="failed", session_id=session_id, error=error_msg)


async def _write_memory(session, session_id, address, value):
    """Write to memory at the specified address."""
    if not value:
        return format_tool_response(status="failed", session_id=session_id, error="value required")
    
    command = f'-interpreter-exec console "set {{int}}{address} = {value}"'
    response = await send_command(session, command)
    
    if response.is_success:
        return format_tool_response(session_id=session_id)
    else:
        return format_tool_response(status="failed", session_id=session_id, error=response.error_message)
