"""
GDB MCP Server - Main Entry Point.

A modular GDB debugging server using the Model Context Protocol (MCP).
Provides tools for debugging via GDB's Machine Interface (MI2).

Usage:
    uv run --frozen fastmcp run main.py -t http -p 8002
    
The workspace root is obtained from AID_WORKSPACE_ROOT environment variable,
set by VS Code extension when spawning MCP server processes.

Container-Built Binaries (Evaluation Mode):
    When AID_CONTAINER_BUILD_PATH is set, GDB runs on the host but the binaries
    were built in a container. This requires path substitution so GDB can find
    source files. The container path is substituted with AID_WORKSPACE_ROOT.
    
    Environment variables:
    - AID_CONTAINER_BUILD_PATH: The container path where binaries were built
      (e.g., /home/jq). This will be substituted with AID_WORKSPACE_ROOT.
"""

import atexit
import asyncio
import os
import sys

# Ensure the gdb package directory is in the path for absolute imports
_package_dir = os.path.dirname(os.path.abspath(__file__))
if _package_dir not in sys.path:
    sys.path.insert(0, _package_dir)

from fastmcp import FastMCP

from session import SessionManager
from tools import register_all_tools


# --- Workspace Initialization ---

def _initialize_workspace() -> str | None:
    """Initialize workspace from AID_WORKSPACE_ROOT. Returns absolute path or None."""
    workspace = os.environ.get("AID_WORKSPACE_ROOT")
    if workspace:
        abs_path = os.path.abspath(workspace)
        print(f"Workspace: {abs_path}", file=sys.stderr)
        return abs_path
    return None


def _initialize_container_build_path() -> str | None:
    """Initialize container build path for debug symbol path substitution.
    
    When binaries are built in a container but debugged on the host,
    debug symbols contain container paths. This path will be substituted
    with AID_WORKSPACE_ROOT so GDB can find source files.
    
    Returns:
        Container build path or None if not set.
    """
    build_path = os.environ.get("AID_CONTAINER_BUILD_PATH")
    if build_path:
        print(f"Container build path (for symbol substitution): {build_path}", file=sys.stderr)
    return build_path


_workspace_root = _initialize_workspace()
_container_build_path = _initialize_container_build_path()


# --- MCP Server Setup ---

mcp = FastMCP("gdb")

session_manager = SessionManager(
    workspace_root=_workspace_root,
    container_build_path=_container_build_path
)

register_all_tools(mcp, session_manager)


# --- Cleanup ---

def _cleanup():
    """Clean up all sessions on exit."""
    try:
        loop = asyncio.new_event_loop()
        loop.run_until_complete(session_manager.stop_all())
        loop.close()
    except Exception:
        pass


atexit.register(_cleanup)
