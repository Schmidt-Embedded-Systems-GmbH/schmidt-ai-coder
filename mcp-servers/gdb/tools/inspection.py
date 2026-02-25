"""
GDB Inspection Tools.

Tools for inspecting program state: print variables, backtrace, locals, registers.
"""

import re
from typing import Any

from fastmcp import FastMCP

from session import SessionManager
from mi import send_command
from parsing import format_tool_response, parse_console_output, parse_stack_frames, parse_variables
from tools._common import tool_handler


def register_inspection_tools(mcp: FastMCP, session_manager: SessionManager) -> None:
    """Register all inspection tools with the MCP server."""
    
    @mcp.tool()
    @tool_handler
    async def gdb_print(
        session_id: str,
        expression: str,
        verbose: bool = False
    ) -> dict[str, Any]:
        """
        Evaluate a variable or expression (e.g., "x", "arr[0]", "a + b", "*ptr").
        
        Args:
            session_id: The GDB session ID
            expression: Variable name or expression to evaluate
            verbose: Include raw GDB response
        """
        session = await session_manager.get(session_id)
        
        # Escape and quote expression for MI (handles spaces, casts, etc.)
        escaped = expression.replace('\\', '\\\\').replace('"', '\\"')
        response = await send_command(session, f'-data-evaluate-expression "{escaped}"')
        
        if response.is_success:
            result = format_tool_response(
                session_id=session_id,
                value=response.result_data.get("value")
            )
            if verbose:
                result["raw_response"] = response.raw
            return result
        else:
            return format_tool_response(status="failed", session_id=session_id, error=response.error_message)
    
    @mcp.tool()
    @tool_handler
    async def gdb_backtrace(
        session_id: str,
        full: bool = False,
        verbose: bool = False
    ) -> dict[str, Any]:
        """
        Show call stack (which functions called which, with file/line info).
        
        Args:
            session_id: The GDB session ID
            full: Also include local variables and arguments for each frame
            verbose: Include raw GDB response
        """
        session = await session_manager.get(session_id)
        
        frames_response = await send_command(session, "-stack-list-frames")
        
        if not frames_response.is_success:
            return format_tool_response(status="failed", session_id=session_id, error=frames_response.error_message)
        
        frames = parse_stack_frames(frames_response.raw)
        result = format_tool_response(session_id=session_id, frames=frames)
        
        if full:
            locals_response = await send_command(session, "-stack-list-locals --simple-values")
            if locals_response.is_success:
                result["locals"] = parse_variables(locals_response.raw)
            
            args_response = await send_command(session, "-stack-list-arguments 1")
            if args_response.is_success:
                result["arguments"] = parse_variables(args_response.raw)
        
        if verbose:
            result["raw_response"] = frames_response.raw
        
        return result
    
    @mcp.tool()
    @tool_handler
    async def gdb_locals(
        session_id: str,
        frame: int = 0,
        verbose: bool = False
    ) -> dict[str, Any]:
        """
        List local variables and function arguments in current frame.
        
        Args:
            session_id: The GDB session ID
            frame: Stack frame number (0 = current, 1 = caller, etc.)
            verbose: Include raw GDB response
        """
        session = await session_manager.get(session_id)
        
        if frame == 0:
            locals_cmd = "-stack-list-locals --simple-values"
            args_cmd = "-stack-list-arguments 1"
        else:
            # Get current thread ID first (required when specifying --frame)
            thread_response = await send_command(session, "-thread-info")
            thread_id = thread_response.result_data.get("thread_id", "1")
            
            locals_cmd = f"-stack-list-locals --thread {thread_id} --frame {frame} --simple-values"
            args_cmd = f"-stack-list-arguments --thread {thread_id} --frame {frame} 1"
        
        locals_response = await send_command(session, locals_cmd)
        args_response = await send_command(session, args_cmd)
        
        if locals_response.is_success:
            result = format_tool_response(
                session_id=session_id,
                locals=parse_variables(locals_response.raw),
                arguments=parse_variables(args_response.raw) if args_response.is_success else []
            )
            if verbose:
                result["raw_response"] = locals_response.raw
            return result
        else:
            return format_tool_response(status="failed", session_id=session_id, error=locals_response.error_message)
    
    @mcp.tool()
    @tool_handler
    async def gdb_registers(
        session_id: str,
        names: str | None = None,
        verbose: bool = False
    ) -> dict[str, Any]:
        """
        Show CPU register values.
        
        Args:
            session_id: The GDB session ID
            names: Space-separated register names (e.g., "pc sp r0"), or omit for all
            verbose: Include raw GDB response
        """
        session = await session_manager.get(session_id)
        
        command = f"info registers {names}" if names else "info registers"
        response = await send_command(session, command)
        
        if response.is_success:
            result = format_tool_response(
                session_id=session_id,
                registers=parse_console_output(response.raw)
            )
            if verbose:
                result["raw_response"] = response.raw
            return result
        else:
            return format_tool_response(status="failed", session_id=session_id, error=response.error_message)
    
    @mcp.tool()
    @tool_handler
    async def gdb_status(
        session_id: str,
        verbose: bool = False
    ) -> dict[str, Any]:
        """
        Get session overview: loaded target, current location, thread count.
        
        Args:
            session_id: The GDB session ID
            verbose: Include raw GDB responses
        """
        session = await session_manager.get(session_id)
        
        result = format_tool_response(
            session_id=session_id,
            target=session.target,
            cwd=session.cwd,
            active=session.is_active()
        )
        
        raw_responses = {}
        
        try:
            frame_response = await send_command(session, "-stack-info-frame")
            if frame_response.is_success:
                frames = parse_stack_frames(frame_response.raw)
                if frames:
                    result["current_frame"] = frames[0]
                if verbose:
                    raw_responses["frame"] = frame_response.raw
        except Exception:
            pass
        
        try:
            thread_response = await send_command(session, "-thread-info")
            if thread_response.is_success:
                match = re.search(r'number-of-threads="(\d+)"', thread_response.raw)
                if match:
                    result["thread_count"] = int(match.group(1))
                if verbose:
                    raw_responses["threads"] = thread_response.raw
        except Exception:
            pass
        
        if verbose and raw_responses:
            result["raw_responses"] = raw_responses
        
        return result
