"""
GDB Remote Debugging Tools.

Tools for connecting to remote targets (GDB server, J-Link, OpenOCD, etc.),
sending monitor commands, and resetting targets.
"""

from typing import Any

from fastmcp import FastMCP

from session import SessionManager
from mi import send_command
from parsing import format_tool_response, parse_console_output
from tools._common import tool_handler


def register_remote_tools(mcp: FastMCP, session_manager: SessionManager) -> None:
    """Register remote debugging tools with the MCP server."""
    
    @mcp.tool()
    @tool_handler
    async def gdb_remote_connect(
        session_id: str,
        target: str,
        verbose: bool = False
    ) -> dict[str, Any]:
        """
        Connect to a remote debug server (J-Link, OpenOCD, QEMU, etc.).
        
        Args:
            session_id: The GDB session ID
            target: Host:port (e.g., "localhost:2331" for J-Link, "localhost:3333" for OpenOCD)
            verbose: Include raw GDB response
        """
        session = await session_manager.get(session_id)
        
        command = f"-target-select remote {target}"
        response = await send_command(session, command, timeout=15.0)
        
        is_connected = response.result_class in ("done", "connected") and response.is_success
        
        if is_connected:
            info_response = await send_command(session, "info target")
            result = format_tool_response(session_id=session_id)
            if info_response.is_success:
                result["target_info"] = parse_console_output(info_response.raw)
            if verbose:
                result["raw_response"] = response.raw
            return result
        else:
            return format_tool_response(
                status="failed",
                session_id=session_id,
                error=response.error_message or "Connection failed"
            )
    
    @mcp.tool()
    @tool_handler
    async def gdb_remote_disconnect(session_id: str) -> dict[str, Any]:
        """
        Disconnect from the current remote target.
        
        Args:
            session_id: The GDB session ID
        """
        session = await session_manager.get(session_id)
        
        response = await send_command(session, "-target-disconnect")
        
        if response.is_success:
            return format_tool_response(session_id=session_id)
        else:
            return format_tool_response(status="failed", session_id=session_id, error=response.error_message)
    
    @mcp.tool()
    @tool_handler
    async def gdb_monitor(
        session_id: str,
        command: str,
        verbose: bool = False
    ) -> dict[str, Any]:
        """
        Send a monitor command to the debug probe (probe-specific).
        
        Common commands: "reset", "halt", "go", "help"
        J-Link: "reset", "halt", "go", "regs"
        OpenOCD: "reset halt", "flash write_image", "targets"
        
        Args:
            session_id: The GDB session ID
            command: The monitor command (probe-specific)
            verbose: Include raw GDB response
        """
        session = await session_manager.get(session_id)
        
        gdb_command = f'-interpreter-exec console "monitor {command}"'
        response = await send_command(session, gdb_command)
        
        if response.is_success:
            result = format_tool_response(
                session_id=session_id,
                output=parse_console_output(response.raw)
            )
            if verbose:
                result["raw_response"] = response.raw
            return result
        else:
            return format_tool_response(status="failed", session_id=session_id, error=response.error_message)
    
    @mcp.tool()
    @tool_handler
    async def gdb_reset(
        session_id: str,
        mode: str = "halt",
        verbose: bool = False
    ) -> dict[str, Any]:
        """
        Reset the remote target (sends "monitor reset <mode>").
        
        Args:
            session_id: The GDB session ID
            mode: "halt" (stop after reset), "init", or "run" (continue after reset)
            verbose: Include raw GDB response
        """
        session = await session_manager.get(session_id)
        
        command = f'-interpreter-exec console "monitor reset {mode}"'
        response = await send_command(session, command)
        
        if response.is_success:
            result = format_tool_response(
                session_id=session_id,
                output=parse_console_output(response.raw)
            )
            if verbose:
                result["raw_response"] = response.raw
            return result
        else:
            return format_tool_response(
                status="failed",
                session_id=session_id,
                error=response.error_message or "Reset failed. Try gdb_monitor with probe-specific syntax."
            )
