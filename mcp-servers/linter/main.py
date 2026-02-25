from fastmcp import FastMCP
import sys
import json
import argparse
import websockets
from typing import Any
from datetime import datetime

def parse_arguments():
    parser = argparse.ArgumentParser(description='Linter MCP Server')
    parser.add_argument('--vscode-ws-port', type=int, default=8999, help='WebSocket port for VS Code bridge (default: 8999)')
    return parser.parse_args()

args = parse_arguments()
vscode_ws_port = args.vscode_ws_port

mcp = FastMCP("linter")

_vscode_websocket = None

async def connect_to_vscode_bridge():
    """Connect to the VS Code WebSocket bridge"""
    global _vscode_websocket
    try:
        _vscode_websocket = await websockets.connect(f"ws://localhost:{vscode_ws_port}")
        print(f"Connected to VS Code bridge on port {vscode_ws_port}", file=sys.stderr)
        return True
    except Exception as e:
        print(f"Failed to connect to VS Code bridge: {e}", file=sys.stderr)
        _vscode_websocket = None
        return False

async def send_vscode_request(method: str, params: dict[str, Any] | None = None) -> Any:
    """Send a request to VS Code bridge and get the response"""
    global _vscode_websocket
    
    if not _vscode_websocket:
        if not await connect_to_vscode_bridge():
            raise Exception("VS Code bridge not available")
    
    try:
        request = {
            "id": f"{method}_{datetime.now().timestamp()}",
            "method": method,
            "params": params or {}
        }
        
        await _vscode_websocket.send(json.dumps(request))
        response_data = await _vscode_websocket.recv()
        response = json.loads(response_data)
        
        if "error" in response:
            raise Exception(f"VS Code API error: {response['error']}")
        
        return response.get("result")
        
    except websockets.ConnectionClosed:
        print("WebSocket connection closed, attempting to reconnect...", file=sys.stderr)
        _vscode_websocket = None
        # Retry once
        if await connect_to_vscode_bridge():
            return await send_vscode_request(method, params)
        else:
            raise Exception("Failed to reconnect to VS Code bridge")
    except Exception as e:
        raise Exception(f"WebSocket communication error: {str(e)}")

@mcp.tool()
async def get_diagnostics(file_path: str | None = None) -> str:
    """
    Get linter diagnostics (errors, warnings, etc.) for a specific file or all open files
    
    Args:
        file_path: Path to the file to get diagnostics for (optional, if not provided gets all diagnostics)
    
    Returns:
        JSON string containing diagnostic information
    """
    try:
        params = {}
        if file_path:
            params["filePath"] = file_path
        
        diagnostics = await send_vscode_request("getDiagnostics", params)
        
        if not diagnostics:
            return json.dumps({
                "success": True,
                "diagnostics": [],
                "message": f"No diagnostics found{' for ' + file_path if file_path else ''}"
            }, indent=2)
        
        formatted_diagnostics = []
        for diag in diagnostics:
            formatted_diag = {
                "file": diag.get("file", "unknown"),
                "line": diag.get("line", 0),
                "column": diag.get("column", 0),
                "severity": diag.get("severity", "unknown"),
                "message": diag.get("message", ""),
                "source": diag.get("source", ""),
                "code": diag.get("code", "")
            }
            formatted_diagnostics.append(formatted_diag)
        
        return json.dumps({
            "success": True,
            "diagnostics": formatted_diagnostics,
            "count": len(formatted_diagnostics),
            "message": f"Found {len(formatted_diagnostics)} diagnostic(s){' for ' + file_path if file_path else ''}"
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
            "diagnostics": []
        }, indent=2)

@mcp.tool()
async def get_diagnostics_by_severity(severity: str = "error", file_path: str | None = None) -> str:
    """
    Get diagnostics filtered by severity level
    
    Args:
        severity: Severity level to filter by ("error", "warning", "info", "hint")
        file_path: Path to the file to get diagnostics for (optional)
    
    Returns:
        JSON string containing filtered diagnostic information
    """
    try:
        params = {"severity": severity.lower()}
        if file_path:
            params["filePath"] = file_path
        
        diagnostics = await send_vscode_request("getDiagnosticsBySeverity", params)
        
        formatted_diagnostics = []
        for diag in diagnostics or []:
            formatted_diag = {
                "file": diag.get("file", "unknown"),
                "line": diag.get("line", 0),
                "column": diag.get("column", 0),
                "severity": diag.get("severity", "unknown"),
                "message": diag.get("message", ""),
                "source": diag.get("source", ""),
                "code": diag.get("code", "")
            }
            formatted_diagnostics.append(formatted_diag)
        
        return json.dumps({
            "success": True,
            "diagnostics": formatted_diagnostics,
            "severity_filter": severity,
            "count": len(formatted_diagnostics),
            "message": f"Found {len(formatted_diagnostics)} {severity} diagnostic(s){' for ' + file_path if file_path else ''}"
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
            "diagnostics": []
        }, indent=2)

@mcp.tool()
async def get_workspace_diagnostics_summary() -> str:
    """
    Get a summary of all diagnostics in the workspace
    
    Returns:
        JSON string containing workspace diagnostic summary
    """
    try:
        summary = await send_vscode_request("getWorkspaceDiagnosticsSummary")
        
        return json.dumps({
            "success": True,
            "summary": summary,
            "message": "Workspace diagnostics summary retrieved successfully"
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
            "summary": {}
        }, indent=2)

@mcp.tool()
async def get_active_file_diagnostics() -> str:
    """
    Get diagnostics for the currently active file in VS Code
    
    Returns:
        JSON string containing active file diagnostic information
    """
    try:
        diagnostics = await send_vscode_request("getActiveFileDiagnostics")
        
        if not diagnostics or not diagnostics.get("file"):
            return json.dumps({
                "success": True,
                "diagnostics": [],
                "activeFile": None,
                "message": "No active file or no diagnostics found"
            }, indent=2)
        
        formatted_diagnostics = []
        for diag in diagnostics.get("diagnostics", []):
            formatted_diag = {
                "line": diag.get("line", 0),
                "column": diag.get("column", 0),
                "severity": diag.get("severity", "unknown"),
                "message": diag.get("message", ""),
                "source": diag.get("source", ""),
                "code": diag.get("code", "")
            }
            formatted_diagnostics.append(formatted_diag)
        
        return json.dumps({
            "success": True,
            "activeFile": diagnostics.get("file"),
            "diagnostics": formatted_diagnostics,
            "count": len(formatted_diagnostics),
            "message": f"Found {len(formatted_diagnostics)} diagnostic(s) for active file: {diagnostics.get('file', 'unknown')}"
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
            "activeFile": None,
            "diagnostics": []
        }, indent=2)

@mcp.tool()
async def get_diagnostics_for_files(file_paths: list[str]) -> str:
    """
    Get diagnostics for multiple specific files
    
    Args:
        file_paths: List of file paths to get diagnostics for
    
    Returns:
        JSON string containing diagnostic information for all specified files
    """
    try:
        params = {"filePaths": file_paths}
        
        diagnostics = await send_vscode_request("getDiagnosticsForFiles", params)
        
        formatted_result = {}
        total_count = 0
        
        for file_path, file_diagnostics in (diagnostics or {}).items():
            formatted_diagnostics = []
            for diag in file_diagnostics:
                formatted_diag = {
                    "line": diag.get("line", 0),
                    "column": diag.get("column", 0),
                    "severity": diag.get("severity", "unknown"),
                    "message": diag.get("message", ""),
                    "source": diag.get("source", ""),
                    "code": diag.get("code", "")
                }
                formatted_diagnostics.append(formatted_diag)
            
            formatted_result[file_path] = {
                "diagnostics": formatted_diagnostics,
                "count": len(formatted_diagnostics)
            }
            total_count += len(formatted_diagnostics)
        
        return json.dumps({
            "success": True,
            "files": formatted_result,
            "totalCount": total_count,
            "message": f"Retrieved diagnostics for {len(formatted_result)} file(s), total {total_count} diagnostic(s)"
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
            "files": {}
        }, indent=2)

@mcp.tool()
async def check_bridge_connection() -> str:
    """
    Check if the connection to VS Code bridge is working
    
    Returns:
        JSON string containing connection status
    """
    try:
        result = await send_vscode_request("ping")
        
        return json.dumps({
            "success": True,
            "connected": True,
            "bridge_port": vscode_ws_port,
            "response": result,
            "message": "VS Code bridge connection is working"
        }, indent=2)
        
    except Exception as e:
        return json.dumps({
            "success": False,
            "connected": False,
            "bridge_port": vscode_ws_port,
            "error": str(e),
            "message": "VS Code bridge connection failed"
        }, indent=2)

def main():
    print("Starting Linter MCP Server...", file=sys.stderr)
    print(f"VS Code bridge WebSocket port: {vscode_ws_port}", file=sys.stderr)
    mcp.run(transport="streamable-http")

def __call__():
    """Enables uvx invocation of this module."""
    print("Linter MCP Server starting via __call__...", file=sys.stderr)
    mcp.run(transport="streamable-http")

# Add this for compatibility with uvx
if __name__ in sys.modules:
    sys.modules[__name__].__call__ = __call__

if __name__ == "__main__":
    main()
