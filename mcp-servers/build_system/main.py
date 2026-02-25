from fastmcp import FastMCP
import sys
import subprocess
import os

mcp = FastMCP("build_system")

# ============================================================================
# Workspace Configuration
# ============================================================================

_workspace_directory: str | None = None


def _initialize_workspace() -> None:
    """Initialize workspace from AID_WORKSPACE_ROOT environment variable."""
    global _workspace_directory
    workspace = os.environ.get("AID_WORKSPACE_ROOT")
    if workspace:
        _workspace_directory = os.path.abspath(workspace)
        print(f"Workspace: {_workspace_directory}", file=sys.stderr)


# Initialize at module load
_initialize_workspace()


def _run_command(
    cmd: list[str],
    cwd: str | None = None,
    timeout: int = 300,
    capture_output: bool = True
) -> subprocess.CompletedProcess:
    """Run a command locally.
    
    Args:
        cmd: Command and arguments as a list
        cwd: Working directory (host path)
        timeout: Timeout in seconds
        capture_output: Whether to capture stdout/stderr
        
    Returns:
        CompletedProcess with the result
    """
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=capture_output,
        text=True,
        timeout=timeout
    )


def _resolve_directory(directory: str | None) -> str:
    """Resolve working directory: uses workspace root as default, resolves relative paths."""
    if directory:
        if os.path.isabs(directory):
            return directory
        elif _workspace_directory:
            return os.path.join(_workspace_directory, directory)
        else:
            return os.path.abspath(directory)
    elif _workspace_directory:
        return _workspace_directory
    else:
        return os.getcwd()


def _validate_path_within_workspace(resolved_path: str) -> str | None:
    """Return error message if path is outside workspace, None if OK."""
    if not _workspace_directory:
        return None  # Can't validate without workspace
    
    workspace_norm = os.path.normpath(_workspace_directory)
    resolved_norm = os.path.normpath(resolved_path)
    
    if not resolved_norm.startswith(workspace_norm + os.sep) and resolved_norm != workspace_norm:
        return f"Path '{resolved_path}' is outside workspace directory '{_workspace_directory}'"
    
    return None

@mcp.tool()
async def build_exec(
    command: list[str],
    cwd: str | None = None,
    timeout_sec: int = 300
) -> str:
    """
    Execute an arbitrary command in the build environment.
    
    This is a generic tool for running build scripts, test commands, or any
    shell command in the workspace.
    
    Args:
        command: Command and arguments as a list (e.g., ["bash", "/home/run.sh"]
                 or ["./configure", "--prefix=/usr"]).
        cwd: Working directory (host path). Defaults to workspace root.
        timeout_sec: Timeout in seconds (default: 300 seconds / 5 minutes).
    
    Returns:
        Command output including stdout, stderr, and exit status.
    
    Examples:
        - Run a test script: ["bash", "/home/test-run.sh"]
        - Build with cmake: ["cmake", "--build", ".", "--parallel", "4"]
        - Run tests: ["ctest", "--output-on-failure"]
    """
    try:
        if not command:
            return "Error: Command list cannot be empty."
        
        work_dir = _resolve_directory(cwd)
        validation_error = _validate_path_within_workspace(work_dir)
        if validation_error:
            return f"Error: {validation_error}"
        
        if not os.path.exists(work_dir):
            return f"Error: Directory '{work_dir}' does not exist."
        if not os.path.isdir(work_dir):
            return f"Error: '{work_dir}' is not a directory."
        
        result = _run_command(command, cwd=work_dir, timeout=timeout_sec)
        
        response = f"Command executed: {' '.join(command)}\n"
        response += f"Working directory: {work_dir}\n"
        response += f"Exit code: {result.returncode}\n\n"
        
        if result.stdout:
            response += "STDOUT:\n"
            response += result.stdout
            response += "\n"
        
        if result.stderr:
            response += "STDERR:\n"
            response += result.stderr
            response += "\n"
        
        if result.returncode == 0:
            response += "Command completed successfully!"
        else:
            response += f"Command failed with exit code {result.returncode}"
        
        return response
        
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout_sec} seconds. Command: {' '.join(command)}"
    except FileNotFoundError as e:
        return f"Error: Command not found: {e}"
    except PermissionError:
        return f"Error: No permission to execute command in directory '{work_dir}'."
    except Exception as e:
        return f"Error executing command: {str(e)}"


@mcp.tool()
async def execute_makefile(target: str | None = None, directory: str | None = None, 
                          makefile_path: str | None = None, extra_args: str | None = None,
                          timeout: int = 300) -> str:
    """
    Execute a Makefile with optional target and directory specification.
    
    Args:
        target: The make target to execute (e.g., 'build', 'clean', 'install'). 
                If None, runs the default target.
        directory: Directory containing the Makefile. If omitted, defaults to workspace root.
                   Relative paths are resolved relative to workspace root.
        makefile_path: Path to a specific Makefile (e.g., 'Makefile.debug'). 
                       If None, uses 'Makefile'.
        extra_args: Additional arguments to pass to make (e.g., '-j4', 'V=1').
        timeout: Timeout in seconds for the make command (default: 300 seconds / 5 minutes).
    
    Returns:
        Build output including stdout, stderr, and exit status.
    """
    try:
        work_dir = _resolve_directory(directory)
        validation_error = _validate_path_within_workspace(work_dir)
        if validation_error:
            return f"Error: {validation_error}"
        
        if not os.path.exists(work_dir):
            return f"Error: Directory '{work_dir}' does not exist."
        
        if not os.path.isdir(work_dir):
            return f"Error: '{work_dir}' is not a directory."
        
        if makefile_path:
            makefile_full_path = os.path.join(work_dir, makefile_path)
            if not os.path.exists(makefile_full_path):
                return f"Error: Makefile '{makefile_path}' not found in directory '{work_dir}'."
        else:
            default_makefile = os.path.join(work_dir, 'Makefile')
            if not os.path.exists(default_makefile):
                return f"Error: No Makefile found in directory '{work_dir}'."
        
        cmd = ['make']
        
        if makefile_path:
            cmd.extend(['-f', makefile_path])
        
        if target:
            cmd.append(target)
        
        if extra_args:
            cmd.extend(extra_args.split())
        
        result = _run_command(cmd, cwd=work_dir, timeout=timeout)
        
        response = f"Make command executed: {' '.join(cmd)}\n"
        response += f"Working directory: {work_dir}\n"
        response += f"Exit code: {result.returncode}\n\n"
        
        if result.stdout:
            response += "STDOUT:\n"
            response += result.stdout
            response += "\n"
        
        if result.stderr:
            response += "STDERR:\n"
            response += result.stderr
            response += "\n"
        
        if result.returncode == 0:
            response += "Build completed successfully!"
        else:
            response += f"Build failed with exit code {result.returncode}"
        
        return response
        
    except subprocess.TimeoutExpired:
        return f"Error: Make command timed out after {timeout} seconds. Command: {' '.join(cmd)}"
    except FileNotFoundError:
        return "Error: 'make' command not found. Please ensure make is installed and available in PATH."
    except PermissionError:
        return f"Error: No permission to execute make in directory '{work_dir}'."
    except Exception as e:
        return f"Error executing make command: {str(e)}"


@mcp.tool()
async def list_makefile_targets(directory: str | None = None, makefile_path: str | None = None) -> str:
    """
    List available targets in a Makefile.
    
    Args:
        directory: Directory containing the Makefile. If omitted, defaults to workspace root.
                   Relative paths are resolved relative to workspace root.
        makefile_path: Path to a specific Makefile (e.g., 'Makefile.debug'). 
                       If None, uses 'Makefile'.
    
    Returns:
        List of available make targets.
    """
    import re
    
    try:
        work_dir = _resolve_directory(directory)
        validation_error = _validate_path_within_workspace(work_dir)
        if validation_error:
            return f"Error: {validation_error}"
        
        if not os.path.exists(work_dir):
            return f"Error: Directory '{work_dir}' does not exist."
        
        if not os.path.isdir(work_dir):
            return f"Error: '{work_dir}' is not a directory."
        
        if makefile_path:
            makefile_full_path = os.path.join(work_dir, makefile_path)
            if not os.path.exists(makefile_full_path):
                return f"Error: Makefile '{makefile_path}' not found in directory '{work_dir}'."
        else:
            default_makefile = os.path.join(work_dir, 'Makefile')
            if not os.path.exists(default_makefile):
                return f"Error: No Makefile found in directory '{work_dir}'."
        
        cmd = ['make', '-n', 'help']
        if makefile_path:
            cmd.extend(['-f', makefile_path])
        
        result = _run_command(cmd, cwd=work_dir, timeout=30)
        
        if result.returncode == 0 and result.stdout.strip():
            return f"Available targets in Makefile (from 'help' target):\n\n{result.stdout}"
        
        # If help target doesn't exist, try to read and parse the Makefile
        makefile_to_read = makefile_path if makefile_path else 'Makefile'
        makefile_full_path = os.path.join(work_dir, makefile_to_read)
        try:
            with open(makefile_full_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
        except Exception as e:
            return f"Error reading Makefile '{makefile_to_read}': {str(e)}"
        
        # Simple parsing to find targets (lines that start with word characters followed by :)
        target_pattern = r'^([a-zA-Z0-9_.-]+)\s*:'
        targets = re.findall(target_pattern, content, re.MULTILINE)
        
        if targets:
            unique_targets = sorted(list(set(targets)))
            return f"Available targets in {makefile_to_read}:\n\n" + "\n".join(f"* {target}" for target in unique_targets)
        else:
            return f"No targets found in {makefile_to_read}. The file might be empty or use a different format."
        
    except subprocess.TimeoutExpired:
        return "Error: Command timed out while trying to list targets."
    except FileNotFoundError:
        return "Error: 'make' command not found. Please ensure make is installed and available in PATH."
    except Exception as e:
        return f"Error listing make targets: {str(e)}"
