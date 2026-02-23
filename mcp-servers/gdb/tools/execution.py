"""
GDB Execution Control Tools.

Tools for controlling program execution: run, continue, step, next, finish.

Design: Simple and synchronous
- GDB runs in default synchronous mode
- Execution commands block until the program stops (breakpoint, exit, crash)
- On timeout, a warning is returned suggesting to restart the session
- Recovery from timeout: gdb_stop + gdb_start fresh
"""

from typing import Any

from fastmcp import FastMCP

from session import SessionManager
from mi import send_command
from parsing import format_tool_response, extract_program_output
from tools._common import tool_handler


def register_execution_tools(mcp: FastMCP, session_manager: SessionManager) -> None:
    """Register all execution control tools with the MCP server."""
    
    @mcp.tool()
    @tool_handler
    async def gdb_run(
        session_id: str,
        args: str | None = None,
        timeout: float = 15.0,
        verbose: bool = False
    ) -> dict[str, Any]:
        """
        Start program execution and wait for it to stop.
        
        Runs until breakpoint, exit, or crash. Set breakpoints first!
        
        Args:
            session_id: The GDB session ID
            args: Command-line arguments for the program
            timeout: Max seconds to wait (default: 15)
            verbose: Include raw GDB response
            
        Note: On timeout, session may be stuck. Use gdb_stop + gdb_start to recover.
        """
        session = await session_manager.get(session_id)
        
        if args:
            await send_command(session, f"-exec-arguments {args}")
        
        response = await send_command(
            session,
            "-exec-run",
            timeout=timeout,
            wait_for_stop=True
        )
        
        program_output = extract_program_output(response.raw)
        
        if response.is_success or response.result_class == "running":
            result = format_tool_response(session_id=session_id)
            if response.result_data.get("reason"):
                result["stop_reason"] = response.result_data["reason"]
            if program_output:
                result["output"] = program_output
            if verbose:
                result["raw_response"] = response.raw
            return result
        else:
            return format_tool_response(status="failed", session_id=session_id, error=response.error_message)
    
    @mcp.tool()
    @tool_handler
    async def gdb_continue(
        session_id: str,
        timeout: float = 15.0,
        verbose: bool = False
    ) -> dict[str, Any]:
        """
        Continue execution until next breakpoint or program end.
        
        Args:
            session_id: The GDB session ID
            timeout: Max seconds to wait (default: 15)
            verbose: Include raw GDB response
            
        Note: On timeout, session may be stuck. Use gdb_stop + gdb_start to recover.
        """
        session = await session_manager.get(session_id)
        
        response = await send_command(
            session,
            "-exec-continue",
            timeout=timeout,
            wait_for_stop=True
        )
        program_output = extract_program_output(response.raw)
        
        if response.is_success or response.result_class == "running":
            result = format_tool_response(session_id=session_id)
            if response.result_data.get("reason"):
                result["stop_reason"] = response.result_data["reason"]
            if program_output:
                result["output"] = program_output
            if verbose:
                result["raw_response"] = response.raw
            return result
        else:
            return format_tool_response(status="failed", session_id=session_id, error=response.error_message)
    
    @mcp.tool()
    @tool_handler
    async def gdb_step(
        session_id: str,
        count: int = 1,
        timeout: float = 10.0,
        verbose: bool = False
    ) -> dict[str, Any]:
        """
        Step into: execute one source line, entering function calls.
        
        Args:
            session_id: The GDB session ID
            count: Number of lines to step (default: 1)
            timeout: Max seconds to wait (default: 10)
            verbose: Include raw GDB response
        """
        session = await session_manager.get(session_id)
        
        command = f"-exec-step {count}" if count > 1 else "-exec-step"
        response = await send_command(
            session,
            command,
            timeout=timeout,
            wait_for_stop=True
        )
        
        if response.is_success or response.result_class == "running":
            result = format_tool_response(session_id=session_id)
            if response.result_data.get("reason"):
                result["stop_reason"] = response.result_data["reason"]
            if verbose:
                result["raw_response"] = response.raw
            return result
        else:
            return format_tool_response(status="failed", session_id=session_id, error=response.error_message)
    
    @mcp.tool()
    @tool_handler
    async def gdb_next(
        session_id: str,
        count: int = 1,
        timeout: float = 10.0,
        verbose: bool = False
    ) -> dict[str, Any]:
        """
        Step over: execute one source line, skipping over function calls.
        
        Args:
            session_id: The GDB session ID
            count: Number of lines to step (default: 1)
            timeout: Max seconds to wait (default: 10)
            verbose: Include raw GDB response
        """
        session = await session_manager.get(session_id)
        
        command = f"-exec-next {count}" if count > 1 else "-exec-next"
        response = await send_command(
            session,
            command,
            timeout=timeout,
            wait_for_stop=True
        )
        
        if response.is_success or response.result_class == "running":
            result = format_tool_response(session_id=session_id)
            if response.result_data.get("reason"):
                result["stop_reason"] = response.result_data["reason"]
            if verbose:
                result["raw_response"] = response.raw
            return result
        else:
            return format_tool_response(status="failed", session_id=session_id, error=response.error_message)
    
    @mcp.tool()
    @tool_handler
    async def gdb_finish(
        session_id: str,
        timeout: float = 15.0,
        verbose: bool = False
    ) -> dict[str, Any]:
        """
        Step out: execute until current function returns.
        
        Returns the function's return value in the response.
        
        Args:
            session_id: The GDB session ID
            timeout: Max seconds to wait (default: 15)
            verbose: Include raw GDB response
        """
        session = await session_manager.get(session_id)
        
        response = await send_command(
            session,
            "-exec-finish",
            timeout=timeout,
            wait_for_stop=True
        )
        
        if response.is_success or response.result_class == "running":
            result = format_tool_response(session_id=session_id)
            if response.result_data.get("value"):
                result["return_value"] = response.result_data["value"]
            if verbose:
                result["raw_response"] = response.raw
            return result
        else:
            return format_tool_response(status="failed", session_id=session_id, error=response.error_message)
