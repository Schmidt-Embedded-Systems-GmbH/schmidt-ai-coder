"""
Utils MCP Server

This MCP server provides lightweight static-analysis and CLI utilities for
debugging C/C++ projects and binaries. It exposes a curated set of safe tools
including grep/ripgrep, strings, addr2line, nm, readelf, and objdump.

Design notes:
- Server remains small and focused (~7 tools max)
- Strongly restricts arguments to avoid arbitrary command execution
- Enforces workspace-root path restrictions (rejects paths outside workspace)
- All subprocess args are built as arrays (never shell strings)
- Timeouts and output truncation are enforced

Security model:
- No raw command strings accepted
- Pattern inputs are sanitized
- Path parameters are validated against workspace root
- Whitelisted options only (e.g., readelf --what parameter)

Tools:
- utils_check_available: Report which CLI tools exist on PATH
- utils_grep: Search files with ripgrep/grep
- utils_strings: Extract printable strings from binaries
- utils_addr2line: Translate addresses to file/line info
- utils_nm: List symbols from object files
- utils_readelf: Display ELF file information
- utils_objdump: Disassemble and inspect binaries
"""

from fastmcp import FastMCP
import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any

mcp = FastMCP("UTILS_MCP")

# ============================================================================
# Configuration
# ============================================================================

DEFAULT_TIMEOUT = 30  # seconds
MAX_OUTPUT_LINES = 500  # default max lines for output
MAX_OUTPUT_BYTES = 64 * 1024  # 64KB max output
MAX_GREP_MATCHES = 100  # default max grep matches

# Workspace root for path validation
_workspace_directory: str | None = None

# ============================================================================
# Tool Registry (Single Source of Truth)
# ============================================================================
# Each tool defines: command, alternative (for macOS), description, optional flag
# This registry is used by utils_check_available() and documents all tools

UTILS_TOOLS: dict[str, dict[str, Any]] = {
    "rg": {
        "description": "ripgrep (fast grep alternative)",
        "optional": True,  # Falls back to grep
    },
    "grep": {
        "description": "standard text search",
    },
    "strings": {
        "description": "extract printable strings from binaries",
    },
    "addr2line": {
        "alternative": "gaddr2line",  # macOS Homebrew binutils
        "description": "convert addresses to file/line info",
    },
    "nm": {
        "description": "list symbols from object files",
    },
    "readelf": {
        "description": "display ELF file information",
        "linux_only": True,  # ELF format is Linux-specific
    },
    "objdump": {
        "alternative": "gobjdump",  # macOS Homebrew binutils
        "description": "disassemble and inspect binaries",
    },
}


def _initialize_workspace() -> None:
    """Initialize workspace from AID_WORKSPACE_ROOT environment variable."""
    global _workspace_directory
    workspace = os.environ.get("AID_WORKSPACE_ROOT")
    if workspace:
        _workspace_directory = os.path.abspath(workspace)
        print(f"Workspace: {_workspace_directory}", file=sys.stderr)


_initialize_workspace()


# ============================================================================
# Helper Functions
# ============================================================================

def _make_result(
    status: str,
    tool: str,
    args: dict[str, Any],
    output: str = "",
    output_truncated: bool = False,
    summary: str | None = None,
    error: str | None = None
) -> str:
    """Create a standardized JSON result."""
    result = {
        "status": status,
        "tool": tool,
        "args": args,
        "outputTruncated": output_truncated,
        "output": output,
    }
    if summary:
        result["summary"] = summary
    if error:
        result["error"] = error
    return json.dumps(result, indent=2)


def _resolve_and_validate_path(path: str) -> tuple[str | None, str | None]:
    """
    Resolve a path and validate it's within the workspace.
    Returns (resolved_path, error_message).
    If error_message is not None, the path is invalid.
    """
    global _workspace_directory
    
    if not path:
        return None, "Path cannot be empty"
    
    # Resolve the path
    if os.path.isabs(path):
        resolved = os.path.abspath(path)
    elif _workspace_directory:
        resolved = os.path.abspath(os.path.join(_workspace_directory, path))
    else:
        resolved = os.path.abspath(path)
    
    # Validate within workspace
    if _workspace_directory:
        # Normalize paths for comparison
        workspace_norm = os.path.normpath(_workspace_directory)
        resolved_norm = os.path.normpath(resolved)
        
        if not resolved_norm.startswith(workspace_norm + os.sep) and resolved_norm != workspace_norm:
            return None, f"Path '{path}' is outside workspace directory"
    
    return resolved, None


def _truncate_output(output: str, max_lines: int = MAX_OUTPUT_LINES, 
                     max_bytes: int = MAX_OUTPUT_BYTES) -> tuple[str, bool]:
    """Truncate output to reasonable size. Returns (output, was_truncated)."""
    if not output:
        return "", False
    
    truncated = False
    
    # Truncate by bytes first
    if len(output.encode('utf-8', errors='replace')) > max_bytes:
        output = output[:max_bytes]
        truncated = True
    
    # Truncate by lines
    lines = output.split('\n')
    if len(lines) > max_lines:
        output = '\n'.join(lines[:max_lines])
        output += f"\n... (truncated, showing {max_lines} of {len(lines)} lines)"
        truncated = True
    elif truncated:
        output += "\n... (truncated by size limit)"
    
    return output, truncated


def _validate_hex_address(addr: str) -> bool:
    """Validate that a string is a valid hex address."""
    # Accept with or without 0x prefix
    pattern = r'^(0x)?[0-9a-fA-F]+$'
    return bool(re.match(pattern, addr.strip()))


def _find_tool(primary: str, fallback: str | None = None) -> str | None:
    """Find a tool on PATH, with optional fallback."""
    path = shutil.which(primary)
    if path:
        return path
    if fallback:
        return shutil.which(fallback)
    return None


def _run_command(
    cmd: list[str],
    timeout: int = DEFAULT_TIMEOUT,
    cwd: str | None = None
) -> tuple[str, str, int, str | None]:
    """
    Run a command and return (stdout, stderr, returncode, error).
    Error is set if the command failed to run (not for non-zero exit codes).
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd
        )
        return result.stdout, result.stderr, result.returncode, None
    except subprocess.TimeoutExpired:
        return "", "", -1, f"Command timed out after {timeout} seconds"
    except FileNotFoundError:
        return "", "", -1, f"Command not found: {cmd[0]}"
    except Exception as e:
        return "", "", -1, f"Error running command: {str(e)}"


# ============================================================================
# MCP Tools
# ============================================================================

@mcp.tool()
def utils_check_available() -> str:
    """
    Check which static analysis CLI tools are available on the system.
    
    Returns a JSON object with availability status for each tool:
    - rg (ripgrep): Fast grep alternative (optional, falls back to grep)
    - grep: Standard text search
    - strings: Extract printable strings from binaries
    - addr2line: Convert addresses to file/line info
    - nm: List symbols from object files
    - readelf: Display ELF file information (Linux only)
    - objdump: Disassemble and inspect binaries
    
    On macOS, some tools may be available via alternatives (e.g., gobjdump, gaddr2line
    from Homebrew binutils).
    """
    import platform
    is_linux = platform.system() == "Linux"
    
    tools: dict[str, dict[str, Any]] = {}
    available_count = 0
    
    for tool_name, tool_info in UTILS_TOOLS.items():
        entry: dict[str, Any] = {
            "available": False,
            "path": None,
            "description": tool_info.get("description", ""),
            "optional": tool_info.get("optional", False),
        }
        
        # Check if tool is Linux-only and we're not on Linux
        if tool_info.get("linux_only") and not is_linux:
            entry["note"] = "Linux only (ELF format)"
            tools[tool_name] = entry
            continue
        
        # Check primary command
        path = shutil.which(tool_name)
        if path:
            entry["available"] = True
            entry["path"] = path
            available_count += 1
        elif tool_info.get("alternative"):
            # Check alternative command (e.g., gobjdump on macOS)
            alt_path = shutil.which(tool_info["alternative"])
            if alt_path:
                entry["available"] = True
                entry["path"] = alt_path
                entry["via_alternative"] = tool_info["alternative"]
                available_count += 1
        
        tools[tool_name] = entry
    
    # Check grep preference
    grep_preference = None
    if tools.get("rg", {}).get("available"):
        grep_preference = "rg"
    elif tools.get("grep", {}).get("available"):
        grep_preference = "grep"
    
    return json.dumps({
        "status": "success",
        "tools": tools,
        "available_count": available_count,
        "total_count": len(UTILS_TOOLS),
        "grep_preference": grep_preference,
        "workspace": _workspace_directory,
        "platform": platform.system(),
        "summary": f"{available_count}/{len(UTILS_TOOLS)} tools available"
    }, indent=2)


@mcp.tool()
def utils_grep(
    pattern: str,
    path: str = ".",
    use_regex: bool = True,
    case_insensitive: bool = False,
    max_matches: int = MAX_GREP_MATCHES,
    file_globs: list[str] | None = None,
    max_lines: int = MAX_OUTPUT_LINES
) -> str:
    """
    Search for text patterns in files using ripgrep (preferred) or grep.
    
    Args:
        pattern: The search pattern. Interpreted as regex by default.
        path: File or directory to search in (relative to workspace, default: ".").
        use_regex: If True, treat pattern as regex. If False, treat as literal string.
        case_insensitive: If True, ignore case when matching.
        max_matches: Maximum number of matches to return (default: 100).
        file_globs: Optional list of glob patterns to filter files (e.g., ["*.c", "*.h"]).
        max_lines: Maximum lines of output (default: 500).
    
    Returns:
        JSON with matches in file:line:content format.
    """
    tool_args = {
        "pattern": pattern,
        "path": path,
        "use_regex": use_regex,
        "case_insensitive": case_insensitive,
        "max_matches": max_matches,
        "file_globs": file_globs
    }
    
    if not pattern:
        return _make_result("error", "utils_grep", tool_args, error="Pattern cannot be empty")
    
    resolved_path, path_error = _resolve_and_validate_path(path)
    if path_error:
        return _make_result("error", "utils_grep", tool_args, error=path_error)
    
    rg_path = shutil.which("rg")
    grep_path = shutil.which("grep")
    
    if not rg_path and not grep_path:
        return _make_result("error", "utils_grep", tool_args, 
                           error="Neither ripgrep (rg) nor grep found on PATH")
    
    # Build command
    if rg_path:
        # Use ripgrep
        cmd = [rg_path, "--line-number", "--no-heading", "--color=never"]
        if not use_regex:
            cmd.append("--fixed-strings")
        if case_insensitive:
            cmd.append("--ignore-case")
        cmd.extend(["--max-count", str(max_matches)])
        
        if file_globs:
            for glob in file_globs:
                # Sanitize glob - only allow safe patterns
                if re.match(r'^[\w\-.*?]+$', glob):
                    cmd.extend(["--glob", glob])
        
        cmd.append(pattern)
        cmd.append(resolved_path)
        tool_used = "ripgrep"
    else:
        # Use grep
        cmd = [grep_path, "-rn", "--color=never"]
        if not use_regex:
            cmd.append("-F")
        if case_insensitive:
            cmd.append("-i")
        cmd.extend(["-m", str(max_matches)])
        
        if file_globs:
            for glob in file_globs:
                if re.match(r'^[\w\-.*?]+$', glob):
                    cmd.extend(["--include", glob])
        
        cmd.append(pattern)
        cmd.append(resolved_path)
        tool_used = "grep"
    
    stdout, stderr, returncode, error = _run_command(cmd)
    
    if error:
        return _make_result("error", "utils_grep", tool_args, error=error)
    
    # grep/rg return 1 when no matches found (not an error)
    if returncode == 1 and not stdout:
        return _make_result("success", "utils_grep", tool_args, 
                           output="", summary="No matches found")
    
    if returncode not in (0, 1):
        return _make_result("error", "utils_grep", tool_args, 
                           error=f"Command failed with code {returncode}: {stderr}")
    
    output, truncated = _truncate_output(stdout, max_lines)
    match_count = len(output.strip().split('\n')) if output.strip() else 0
    
    return _make_result(
        "success", "utils_grep", tool_args,
        output=output,
        output_truncated=truncated,
        summary=f"Found {match_count} matches using {tool_used}"
    )


@mcp.tool()
def utils_strings(
    file: str,
    min_len: int = 4,
    max_lines: int = 200
) -> str:
    """
    Extract printable strings from a binary file.
    
    Args:
        file: Path to the binary file (relative to workspace).
        min_len: Minimum string length to extract (default: 4).
        max_lines: Maximum number of strings to return (default: 200).
    
    Returns:
        JSON with extracted strings, one per line.
    """
    tool_args = {"file": file, "min_len": min_len, "max_lines": max_lines}
    
    resolved_path, path_error = _resolve_and_validate_path(file)
    if path_error:
        return _make_result("error", "utils_strings", tool_args, error=path_error)
    
    if not os.path.isfile(resolved_path):
        return _make_result("error", "utils_strings", tool_args, 
                           error=f"File not found: {file}")
    
    strings_path = shutil.which("strings")
    if not strings_path:
        return _make_result("error", "utils_strings", tool_args, 
                           error="strings command not found on PATH")
    
    min_len = max(1, min(min_len, 100))
    
    # Build command
    cmd = [strings_path, "-n", str(min_len), resolved_path]
    
    stdout, stderr, returncode, error = _run_command(cmd)
    
    if error:
        return _make_result("error", "utils_strings", tool_args, error=error)
    
    if returncode != 0:
        return _make_result("error", "utils_strings", tool_args, 
                           error=f"strings failed with code {returncode}: {stderr}")
    
    output, truncated = _truncate_output(stdout, max_lines)
    string_count = len(output.strip().split('\n')) if output.strip() else 0
    
    return _make_result(
        "success", "utils_strings", tool_args,
        output=output,
        output_truncated=truncated,
        summary=f"Extracted {string_count} strings (min length: {min_len})"
    )


@mcp.tool()
def utils_addr2line(
    binary: str,
    addresses: list[str],
    demangle: bool = True,
    function_names: bool = True
) -> str:
    """
    Translate memory addresses to source file locations.
    
    Args:
        binary: Path to the executable or shared library (relative to workspace, or absolute).
        addresses: List of hex addresses to translate (e.g., ["0x401234", "0x401567"]).
        demangle: If True, demangle C++ symbol names (default: True).
        function_names: If True, include function names in output (default: True).
    
    Returns:
        JSON with file:line information for each address.
    """
    tool_args = {
        "binary": binary,
        "addresses": addresses,
        "demangle": demangle,
        "function_names": function_names
    }
    
    resolved_path, path_error = _resolve_and_validate_path(binary)
    if path_error:
        return _make_result("error", "utils_addr2line", tool_args, error=path_error)
    
    if not os.path.isfile(resolved_path):
        return _make_result("error", "utils_addr2line", tool_args, 
                           error=f"Binary not found: {binary}")
    
    if not addresses:
        return _make_result("error", "utils_addr2line", tool_args, 
                           error="At least one address is required")
    
    validated_addresses = []
    for addr in addresses[:50]:  # Limit to 50 addresses
        addr = addr.strip()
        if not _validate_hex_address(addr):
            return _make_result("error", "utils_addr2line", tool_args, 
                               error=f"Invalid hex address: {addr}")
        validated_addresses.append(addr)
    
    addr2line_path = shutil.which("addr2line")
    if not addr2line_path:
        return _make_result("error", "utils_addr2line", tool_args, 
                           error="addr2line command not found on PATH")
    
    # Build command
    cmd = [addr2line_path, "-e", resolved_path]
    if demangle:
        cmd.append("-C")
    if function_names:
        cmd.append("-f")
    cmd.extend(validated_addresses)
    
    stdout, stderr, returncode, error = _run_command(cmd)
    
    if error:
        return _make_result("error", "utils_addr2line", tool_args, error=error)
    
    if returncode != 0:
        return _make_result("error", "utils_addr2line", tool_args, 
                           error=f"addr2line failed with code {returncode}: {stderr}")
    
    return _make_result(
        "success", "utils_addr2line", tool_args,
        output=stdout,
        summary=f"Resolved {len(validated_addresses)} address(es)"
    )


@mcp.tool()
def utils_nm(
    binary: str,
    demangle: bool = True,
    defined_only: bool = False,
    max_lines: int = MAX_OUTPUT_LINES
) -> str:
    """
    List symbols from object files or binaries.
    
    Args:
        binary: Path to the object file, library, or executable (relative to workspace, or absolute).
        demangle: If True, demangle C++ symbol names (default: True).
        defined_only: If True, only show defined (not undefined) symbols.
        max_lines: Maximum lines of output (default: 500).
    
    Returns:
        JSON with symbol listing (address, type, name).
    """
    tool_args = {
        "binary": binary,
        "demangle": demangle,
        "defined_only": defined_only,
        "max_lines": max_lines
    }
    
    resolved_path, path_error = _resolve_and_validate_path(binary)
    if path_error:
        return _make_result("error", "utils_nm", tool_args, error=path_error)
    
    if not os.path.isfile(resolved_path):
        return _make_result("error", "utils_nm", tool_args, 
                           error=f"Binary not found: {binary}")
    
    nm_path = shutil.which("nm")
    if not nm_path:
        return _make_result("error", "utils_nm", tool_args, 
                           error="nm command not found on PATH")
    
    # Build command
    cmd = [nm_path]
    if demangle:
        cmd.append("-C")
    if defined_only:
        cmd.append("--defined-only")
    cmd.append(resolved_path)
    
    stdout, stderr, returncode, error = _run_command(cmd)
    
    if error:
        return _make_result("error", "utils_nm", tool_args, error=error)
    
    if returncode != 0:
        return _make_result("error", "utils_nm", tool_args, 
                           error=f"nm failed with code {returncode}: {stderr}")
    
    output, truncated = _truncate_output(stdout, max_lines)
    symbol_count = len(output.strip().split('\n')) if output.strip() else 0
    
    return _make_result(
        "success", "utils_nm", tool_args,
        output=output,
        output_truncated=truncated,
        summary=f"Listed {symbol_count} symbols"
    )


@mcp.tool()
def utils_readelf(
    binary: str,
    what: str = "headers",
    max_lines: int = MAX_OUTPUT_LINES
) -> str:
    """
    Display information about ELF format files.
    
    Args:
        binary: Path to the ELF file (relative to workspace, or absolute).
        what: What information to display. One of:
            - "headers": ELF file header (-h)
            - "sections": Section headers (-S)
            - "symbols": Symbol table (-s)
            - "relocs": Relocation entries (-r)
            - "dynamic": Dynamic section (-d)
            - "all": All headers (-a)
        max_lines: Maximum lines of output (default: 500).
    
    Returns:
        JSON with the requested ELF information.
    """
    tool_args = {"binary": binary, "what": what, "max_lines": max_lines}
    
    # Whitelist of allowed 'what' values and their flags
    what_flags = {
        "headers": "-h",
        "sections": "-S",
        "symbols": "-s",
        "relocs": "-r",
        "dynamic": "-d",
        "all": "-a"
    }
    
    what = what.lower()
    if what not in what_flags:
        return _make_result("error", "utils_readelf", tool_args, 
                           error=f"Invalid 'what' parameter: {what}. Must be one of: {', '.join(what_flags.keys())}")
    
    resolved_path, path_error = _resolve_and_validate_path(binary)
    if path_error:
        return _make_result("error", "utils_readelf", tool_args, error=path_error)
    
    if not os.path.isfile(resolved_path):
        return _make_result("error", "utils_readelf", tool_args, 
                           error=f"Binary not found: {binary}")
    
    readelf_path = shutil.which("readelf")
    if not readelf_path:
        return _make_result("error", "utils_readelf", tool_args, 
                           error="readelf command not found on PATH")
    
    # Build command
    cmd = [readelf_path, what_flags[what], resolved_path]
    
    stdout, stderr, returncode, error = _run_command(cmd)
    
    if error:
        return _make_result("error", "utils_readelf", tool_args, error=error)
    
    if returncode != 0:
        return _make_result("error", "utils_readelf", tool_args, 
                           error=f"readelf failed with code {returncode}: {stderr}")
    
    output, truncated = _truncate_output(stdout, max_lines)
    
    return _make_result(
        "success", "utils_readelf", tool_args,
        output=output,
        output_truncated=truncated,
        summary=f"Displayed {what} for {os.path.basename(binary)}"
    )


@mcp.tool()
def utils_objdump(
    binary: str,
    what: str = "disasm",
    function: str | None = None,
    start_addr: str | None = None,
    max_lines: int = MAX_OUTPUT_LINES
) -> str:
    """
    Display information from object files, including disassembly.
    
    Args:
        binary: Path to the binary file (relative to workspace, or absolute).
        what: What information to display. One of:
            - "disasm": Disassemble executable sections (-d)
            - "disasm-all": Disassemble all sections (-D)
            - "syms": Display symbol table (-t)
            - "headers": Display all headers (-x)
            - "source": Disassemble with source (-S, requires debug info)
        function: Optional function name to disassemble (only with disasm modes).
        start_addr: Optional start address for disassembly (hex, e.g., "0x401234").
        max_lines: Maximum lines of output (default: 500).
    
    Returns:
        JSON with the requested objdump output.
    """
    tool_args = {
        "binary": binary,
        "what": what,
        "function": function,
        "start_addr": start_addr,
        "max_lines": max_lines
    }
    
    # Whitelist of allowed 'what' values and their flags
    what_flags = {
        "disasm": "-d",
        "disasm-all": "-D",
        "syms": "-t",
        "headers": "-x",
        "source": "-S"
    }
    
    what = what.lower()
    if what not in what_flags:
        return _make_result("error", "utils_objdump", tool_args, 
                           error=f"Invalid 'what' parameter: {what}. Must be one of: {', '.join(what_flags.keys())}")
    
    resolved_path, path_error = _resolve_and_validate_path(binary)
    if path_error:
        return _make_result("error", "utils_objdump", tool_args, error=path_error)
    
    if not os.path.isfile(resolved_path):
        return _make_result("error", "utils_objdump", tool_args, 
                           error=f"Binary not found: {binary}")
    
    if start_addr:
        if not _validate_hex_address(start_addr):
            return _make_result("error", "utils_objdump", tool_args, 
                               error=f"Invalid hex address: {start_addr}")
    
    objdump_path = shutil.which("objdump")
    if not objdump_path:
        return _make_result("error", "utils_objdump", tool_args, 
                           error="objdump command not found on PATH")
    
    # Build command
    cmd = [objdump_path, what_flags[what]]
    
    # Add optional parameters for disassembly modes
    if what in ("disasm", "disasm-all", "source"):
        if start_addr:
            cmd.extend(["--start-address", start_addr])
        if function:
            # Sanitize function name - only allow valid C/C++ identifiers
            if re.match(r'^[a-zA-Z_][a-zA-Z0-9_:]*$', function):
                cmd.extend(["--disassemble=" + function])
    
    cmd.append(resolved_path)
    
    stdout, stderr, returncode, error = _run_command(cmd)
    
    if error:
        return _make_result("error", "utils_objdump", tool_args, error=error)
    
    if returncode != 0:
        return _make_result("error", "utils_objdump", tool_args, 
                           error=f"objdump failed with code {returncode}: {stderr}")
    
    output, truncated = _truncate_output(stdout, max_lines)
    
    summary_parts = [f"Displayed {what} for {os.path.basename(binary)}"]
    if function:
        summary_parts.append(f"function: {function}")
    if start_addr:
        summary_parts.append(f"from: {start_addr}")
    
    return _make_result(
        "success", "utils_objdump", tool_args,
        output=output,
        output_truncated=truncated,
        summary=", ".join(summary_parts)
    )
