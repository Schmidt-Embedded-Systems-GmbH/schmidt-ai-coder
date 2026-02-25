"""
GDB Breakpoint Tools.

Unified breakpoint management with a single tool that supports
set, list, delete, enable, and disable operations.
"""

from typing import Any

from fastmcp import FastMCP

from session import SessionManager
from mi import send_command
from parsing import format_tool_response, parse_breakpoints
from tools._common import tool_handler


def register_breakpoint_tools(mcp: FastMCP, session_manager: SessionManager) -> None:
    """Register breakpoint tools with the MCP server."""
    
    @mcp.tool()
    @tool_handler
    async def gdb_breakpoint(
        session_id: str,
        action: str,
        location: str | None = None,
        breakpoint_id: str | None = None,
        condition: str | None = None,
        temporary: bool = False,
        pending: bool = False,
        verbose: bool = False
    ) -> dict[str, Any]:
        """
        Manage breakpoints: set, list, delete, enable, disable.
        
        Args:
            session_id: The GDB session ID
            action: "set", "list", "delete", "enable", or "disable"
            location: For set: function name, file:line, or *address
            breakpoint_id: For delete/enable/disable: the breakpoint number
            condition: For set: break only if expression is true
            temporary: For set: auto-delete after first hit
            pending: For set: allow unresolved location (e.g., in shared library)
            verbose: Include raw GDB response
        """
        session = await session_manager.get(session_id)
        action = action.lower()
        
        if action == "set":
            return await _set_breakpoint(session, session_id, location, condition, temporary, pending, verbose)
        elif action == "list":
            return await _list_breakpoints(session, session_id, verbose)
        elif action == "delete":
            return await _delete_breakpoint(session, session_id, breakpoint_id)
        elif action == "enable":
            return await _enable_breakpoint(session, session_id, breakpoint_id)
        elif action == "disable":
            return await _disable_breakpoint(session, session_id, breakpoint_id)
        else:
            return format_tool_response(
                status="failed",
                session_id=session_id,
                error=f"Unknown action: {action}"
            )


async def _set_breakpoint(session, session_id, location, condition, temporary, pending, verbose):
    """Set a breakpoint at the specified location."""
    if not location:
        return format_tool_response(status="failed", session_id=session_id, error="location required")
    
    cmd_parts = ["-break-insert"]
    if temporary:
        cmd_parts.append("-t")
    if pending:
        cmd_parts.append("-f")
    if condition:
        cmd_parts.append(f'-c "{condition}"')
    cmd_parts.append(location)
    
    response = await send_command(session, " ".join(cmd_parts))
    
    if response.is_success:
        result = format_tool_response(session_id=session_id)
        if response.result_data.get("breakpoint"):
            result["breakpoint_info"] = response.result_data["breakpoint"]
        if verbose:
            result["raw_response"] = response.raw
        return result
    else:
        return format_tool_response(status="failed", session_id=session_id, error=response.error_message)


async def _list_breakpoints(session, session_id, verbose):
    """List all breakpoints."""
    response = await send_command(session, "-break-list")
    
    if response.is_success:
        breakpoints = parse_breakpoints(response.raw)
        result = format_tool_response(session_id=session_id, breakpoints=breakpoints)
        if verbose:
            result["raw_response"] = response.raw
        return result
    else:
        return format_tool_response(status="failed", session_id=session_id, error=response.error_message)


async def _delete_breakpoint(session, session_id, breakpoint_id):
    """Delete a breakpoint by ID."""
    if not breakpoint_id:
        return format_tool_response(status="failed", session_id=session_id, error="breakpoint_id required")
    
    response = await send_command(session, f"-break-delete {breakpoint_id}")
    
    if response.is_success:
        return format_tool_response(session_id=session_id)
    else:
        return format_tool_response(status="failed", session_id=session_id, error=response.error_message)


async def _enable_breakpoint(session, session_id, breakpoint_id):
    """Enable a breakpoint by ID."""
    if not breakpoint_id:
        return format_tool_response(status="failed", session_id=session_id, error="breakpoint_id required")
    
    response = await send_command(session, f"-break-enable {breakpoint_id}")
    
    if response.is_success:
        return format_tool_response(session_id=session_id)
    else:
        return format_tool_response(status="failed", session_id=session_id, error=response.error_message)


async def _disable_breakpoint(session, session_id, breakpoint_id):
    """Disable a breakpoint by ID."""
    if not breakpoint_id:
        return format_tool_response(status="failed", session_id=session_id, error="breakpoint_id required")
    
    response = await send_command(session, f"-break-disable {breakpoint_id}")
    
    if response.is_success:
        return format_tool_response(session_id=session_id)
    else:
        return format_tool_response(status="failed", session_id=session_id, error=response.error_message)
