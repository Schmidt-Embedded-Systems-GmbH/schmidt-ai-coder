"""
GDB MCP Tools Package.

This package contains all the MCP tool implementations for the GDB server.
Each module groups related tools together.
"""

from fastmcp import FastMCP

from session import SessionManager

from tools.lifecycle import register_lifecycle_tools
from tools.target import register_target_tools
from tools.breakpoints import register_breakpoint_tools
from tools.execution import register_execution_tools
from tools.inspection import register_inspection_tools
from tools.memory import register_memory_tools
from tools.remote import register_remote_tools
from tools.command import register_command_tools


def register_all_tools(mcp: FastMCP, session_manager: SessionManager) -> None:
    """
    Register all GDB tools with the MCP server.
    
    Args:
        mcp: The FastMCP server instance
        session_manager: The SessionManager for managing GDB sessions
    """
    register_lifecycle_tools(mcp, session_manager)
    register_target_tools(mcp, session_manager)
    register_breakpoint_tools(mcp, session_manager)
    register_execution_tools(mcp, session_manager)
    register_inspection_tools(mcp, session_manager)
    register_memory_tools(mcp, session_manager)
    register_remote_tools(mcp, session_manager)
    register_command_tools(mcp, session_manager)
