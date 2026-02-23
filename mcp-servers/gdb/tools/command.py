"""
GDB Raw Command Tool.

Provides an escape hatch for sending arbitrary GDB MI commands.
"""

from typing import Any

from fastmcp import FastMCP

from session import SessionManager
from mi import send_command
from parsing import format_tool_response, parse_console_output
from tools._common import tool_handler


def register_command_tools(mcp: FastMCP, session_manager: SessionManager) -> None:
    """Register the raw command tool with the MCP server."""
    
    @mcp.tool()
    @tool_handler
    async def gdb_command(
        session_id: str,
        command: str,
        timeout: float = 10.0,
        verbose: bool = False
    ) -> dict[str, Any]:
        """
        Execute a raw GDB MI or console command.
        
        This is an escape hatch for operations not covered by dedicated tools.
        MI commands start with "-", console commands are sent as-is.
        
        ═══════════════════════════════════════════════════════════════════════
        COOKBOOK: Common Operations via gdb_command
        ═══════════════════════════════════════════════════════════════════════
        
        SYMBOLS & FUNCTIONS:
        - "info functions"              → List all functions
        - "info functions REGEX"        → Search functions by pattern
        - "info variables"              → List global variables
        - "info types"                  → List all types
        - "ptype EXPR"                  → Show type of expression/variable
        - "whatis EXPR"                 → Brief type info
        
        THREADS:
        - "-thread-info"                → List all threads (structured MI)
        - "-thread-select ID"           → Switch to thread ID
        - "thread apply all bt"         → Backtrace all threads
        
        WATCHPOINTS:
        - "watch VAR"                   → Break when VAR is written
        - "rwatch VAR"                  → Break when VAR is read
        - "awatch VAR"                  → Break on read or write
        
        EXECUTION:
        - "-exec-until LOCATION"        → Run until location
        - "-exec-arguments ARGS"        → Set program arguments
        - "signal SIGNAME"              → Send signal to program
        - "handle SIGNAL nostop"        → Configure signal handling
        
        DISASSEMBLY:
        - "disassemble main"            → Disassemble function
        - "disassemble ADDR,+LEN"       → Disassemble from address
        - "-data-disassemble -s ADDR -e ADDR -- 0"  → MI disassembly
        
        MEMORY (advanced):
        - "find /b START, END, BYTE"    → Search memory for byte pattern
        - "x/16xb ADDR"                 → Examine 16 bytes at address
        
        SOURCE:
        - "list"                        → Show current source
        - "list FUNC"                   → Show function source
        - "info line LOCATION"          → Line info for location
        - "info sources"                → List source files
        
        ENVIRONMENT:
        - "set environment VAR=VALUE"   → Set env var for target
        - "show environment"            → Show environment
        - "show args"                   → Show program arguments
        
        ARCHITECTURE:
        - "set architecture ARCH"       → Set target architecture
        - "show architecture"           → Show current architecture
        - "show endian"                 → Show byte order
        
        SHARED LIBRARIES:
        - "info sharedlibrary"          → List loaded libraries
        - "info sharedlibrary PATTERN"  → Filter by pattern
        
        NOTES:
        - MI commands (-xxx) return structured data in mi_result field
        - "shell ..." output bypasses MI and may not appear in output
        
        ═══════════════════════════════════════════════════════════════════════
        
        Args:
            session_id: The GDB session ID
            command: The GDB command (without trailing newline)
            timeout: Max seconds to wait (default: 10)
            verbose: Include raw MI response
        """
        session = await session_manager.get(session_id)
        
        response = await send_command(session, command, timeout=timeout)
        console_output = parse_console_output(response.raw)
        is_mi_command = command.strip().startswith("-")
        
        if response.is_success:
            result = format_tool_response(session_id=session_id)
            if console_output:
                result["output"] = console_output
            # For MI commands, include result_data even without verbose
            if is_mi_command and response.result_data:
                result["mi_result"] = response.result_data
            if verbose:
                result["raw_response"] = response.raw
            return result
        else:
            result = format_tool_response(
                status="failed",
                session_id=session_id,
                error=response.error_message
            )
            if verbose:
                result["raw_response"] = response.raw
            return result
