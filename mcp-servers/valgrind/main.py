"""
Valgrind MCP Server

This MCP server provides controlled access to Valgrind memory analysis tools.
It exposes functionality to check for memory leaks, uninitialized memory access,
and other memory-related issues in compiled executables.

Design notes:
- Valgrind is a SINGLE-SHOT tool, not an interactive session like GDB
- Each valgrind invocation runs a program to completion and reports findings
- No session management is needed (unlike GDB MCP server)
- We use Valgrind's stable XML output format for reliable parsing
  (see: https://valgrind.org/docs/manual/manual-core.html)

Robustness considerations:
- XML output is Valgrind's documented stable format for tool consumption
- We use --child-silent-after-fork=yes to handle forking programs
- We use %p in xml-file path to handle multi-process output correctly
- We use -q (quiet) to minimize text output when using XML mode
- Error counting sums occurrences (not max) per Valgrind's protocol
- In XML mode, leak-check is effectively forced to "full" by Valgrind
- XML parse failures are surfaced, not silently treated as "no errors"

Tools:
- valgrind_check_available: Check if Valgrind is installed and get version info
- valgrind_memcheck_run: Run Valgrind memcheck on an executable with structured output
"""

from fastmcp import FastMCP
import sys
import subprocess
import os
import re
import json
import glob
import xml.etree.ElementTree as ET
from typing import Any
from dataclasses import dataclass, asdict, field
import tempfile
import shutil

mcp = FastMCP("VALGRIND_MCP")

# ============================================================================
# Configuration
# ============================================================================

MAX_ERRORS_DEFAULT = 10  # Maximum number of detailed errors to return
MAX_RAW_OUTPUT_LINES = 100  # Maximum lines of raw output to include
MAX_STACK_FRAMES = 5  # Maximum stack frames per error
MAX_RAW_OUTPUT_BYTES = 8192  # Maximum bytes of raw output

# Workspace root for resolving relative paths
_workspace_directory: str | None = None


def _initialize_workspace() -> None:
    """Initialize workspace from AID_WORKSPACE_ROOT environment variable."""
    global _workspace_directory
    workspace = os.environ.get("AID_WORKSPACE_ROOT")
    if workspace:
        _workspace_directory = os.path.abspath(workspace)
        print(f"Workspace: {_workspace_directory}", file=sys.stderr)


_initialize_workspace()


# Explicit mapping from Valgrind leak kinds to LeakSummary fields
# This avoids substring matching and makes the schema explicit
LEAK_KIND_FIELDS: dict[str, tuple[str, str]] = {
    "Leak_DefinitelyLost": ("definitely_lost_bytes", "definitely_lost_blocks"),
    "Leak_IndirectlyLost": ("indirectly_lost_bytes", "indirectly_lost_blocks"),
    "Leak_PossiblyLost": ("possibly_lost_bytes", "possibly_lost_blocks"),
    "Leak_StillReachable": ("still_reachable_bytes", "still_reachable_blocks"),
}

# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class StackFrame:
    """A single frame in a stack trace from Valgrind XML output"""
    instruction_pointer: str | None = None
    function: str | None = None
    file: str | None = None
    line: int | None = None
    directory: str | None = None
    object_file: str | None = None


@dataclass
class ValgrindError:
    """A structured Valgrind error parsed from XML output"""
    unique_id: str | None = None
    kind: str = "Unknown"
    message: str = ""
    stack_frames: list[StackFrame] = field(default_factory=list)
    auxiliary_message: str | None = None
    auxiliary_stack: list[StackFrame] = field(default_factory=list)


@dataclass
class LeakSummary:
    """Summary of memory leak information from Valgrind XML"""
    definitely_lost_bytes: int = 0
    definitely_lost_blocks: int = 0
    indirectly_lost_bytes: int = 0
    indirectly_lost_blocks: int = 0
    possibly_lost_bytes: int = 0
    possibly_lost_blocks: int = 0
    still_reachable_bytes: int = 0
    still_reachable_blocks: int = 0


@dataclass
class ErrorCounts:
    """Separate counts for memcheck errors vs leak errors.
    
    - contexts: number of distinct error/leak entries (unique issues)
    - occurrences: total times these errors occurred (from errorcounts)
    """
    memcheck_contexts: int = 0
    memcheck_occurrences: int = 0
    leak_contexts: int = 0
    leak_occurrences: int = 0


@dataclass
class ParseResult:
    """Result from parsing a single XML file"""
    memcheck_errors: list[ValgrindError] = field(default_factory=list)
    leak_errors: list[ValgrindError] = field(default_factory=list)
    leak_summary: LeakSummary = field(default_factory=LeakSummary)
    counts: ErrorCounts = field(default_factory=ErrorCounts)
    parse_error: str | None = None  # Non-None if parsing failed


# ============================================================================
# Helper Functions
# ============================================================================

def safe_int(value: str | None, default: int = 0) -> int:
    """Safely parse an integer from string, returning default on failure."""
    if value is None:
        return default
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return default


def make_result(
    status: str,
    summary: str,
    exit_code: int | None = None,
    counts: ErrorCounts | None = None,
    memcheck_errors: list[dict] | None = None,
    leak_errors: list[dict] | None = None,
    leaks_summary: dict | None = None,
    effective_leak_check: str | None = None,
    xml_parse_errors: list[str] | None = None,
    raw_output: str | None = None,
    command: str | None = None
) -> str:
    """Create a standardized JSON result for memcheck_run.
    
    Centralizes the response structure to avoid repetition and ensure consistency.
    """
    counts = counts or ErrorCounts()
    return json.dumps({
        "status": status,
        "exit_code": exit_code,
        "summary": summary,
        "memcheck_error_contexts": counts.memcheck_contexts,
        "memcheck_error_occurrences": counts.memcheck_occurrences,
        "leak_contexts": counts.leak_contexts,
        "leak_occurrences": counts.leak_occurrences,
        "memcheck_errors": memcheck_errors or [],
        "leak_errors": leak_errors or [],
        "leaks_summary": leaks_summary,
        "effective_leak_check": effective_leak_check,
        "xml_parse_errors": xml_parse_errors,
        "raw_output_truncated": raw_output,
        "command": command
    }, indent=2)


def find_valgrind_path() -> str | None:
    """Find the path to the valgrind executable using shutil.which (no subprocess)."""
    return shutil.which('valgrind')


def parse_valgrind_version(version_output: str) -> str | None:
    """Extract version number from valgrind --version output."""
    match = re.search(r'valgrind-(\d+\.\d+(?:\.\d+)?)', version_output)
    return match.group(1) if match else None


def truncate_output(output: str, max_lines: int = MAX_RAW_OUTPUT_LINES, 
                    max_bytes: int = MAX_RAW_OUTPUT_BYTES) -> str:
    """Truncate output to reasonable size for model consumption."""
    if not output:
        return ""
    
    truncated = False
    
    if len(output) > max_bytes:
        output = output[:max_bytes]
        truncated = True
    
    lines = output.split('\n')
    original_lines = len(lines)
    if len(lines) > max_lines:
        output = '\n'.join(lines[:max_lines])
        output += f"\n... (truncated, showing {max_lines} of {original_lines} lines)"
    elif truncated:
        output += "\n... (truncated by size limit)"
    
    return output


def serialize_error(error: ValgrindError) -> dict[str, Any]:
    """Serialize a ValgrindError to a dict, omitting None values for cleaner output."""
    result: dict[str, Any] = {"kind": error.kind, "message": error.message}
    
    if error.unique_id:
        result["id"] = error.unique_id
    if error.stack_frames:
        result["stack"] = [
            {k: v for k, v in asdict(frame).items() if v is not None}
            for frame in error.stack_frames
        ]
    if error.auxiliary_message:
        result["auxiliary_message"] = error.auxiliary_message
    if error.auxiliary_stack:
        result["auxiliary_stack"] = [
            {k: v for k, v in asdict(frame).items() if v is not None}
            for frame in error.auxiliary_stack
        ]
    
    return result


def build_human_summary(counts: ErrorCounts, leak_summary: LeakSummary, 
                        exit_code: int | None, parse_errors: list[str]) -> str:
    """Build a concise human-readable summary of findings."""
    parts = []
    
    if parse_errors:
        parts.append(f"WARNING: {len(parse_errors)} XML file(s) failed to parse.")
    
    # Memcheck errors
    if counts.memcheck_contexts == 0:
        parts.append("No memory errors detected.")
    elif counts.memcheck_contexts == counts.memcheck_occurrences:
        parts.append(f"Found {counts.memcheck_contexts} memory error(s).")
    else:
        parts.append(f"Found {counts.memcheck_contexts} unique memory error(s) "
                     f"({counts.memcheck_occurrences} total occurrences).")
    
    # Leak summary
    total_leaked = (leak_summary.definitely_lost_bytes + 
                    leak_summary.indirectly_lost_bytes +
                    leak_summary.possibly_lost_bytes)
    
    if total_leaked > 0:
        leak_parts = []
        if leak_summary.definitely_lost_bytes > 0:
            leak_parts.append(f"{leak_summary.definitely_lost_bytes:,} definitely lost")
        if leak_summary.indirectly_lost_bytes > 0:
            leak_parts.append(f"{leak_summary.indirectly_lost_bytes:,} indirectly lost")
        if leak_summary.possibly_lost_bytes > 0:
            leak_parts.append(f"{leak_summary.possibly_lost_bytes:,} possibly lost")
        parts.append("Leaks: " + ", ".join(leak_parts) + " bytes.")
    elif counts.leak_contexts > 0:
        parts.append(f"Found {counts.leak_contexts} leak report(s).")
    else:
        parts.append("No memory leaks detected.")
    
    if exit_code is not None:
        parts.append(f"Program exited with code {exit_code}.")
    
    return " ".join(parts)


# ============================================================================
# XML Parsing
# ============================================================================

def parse_stack_frames_from_xml(stack_elem: ET.Element, max_frames: int) -> list[StackFrame]:
    """Parse stack frames from a Valgrind XML <stack> element.
    
    Uses Valgrind's documented XML schema which is stable.
    See: https://valgrind.org/docs/manual/mc-manual.html#mc-manual.xmlformat
    """
    frames = []
    for frame in stack_elem.findall('frame'):
        if len(frames) >= max_frames:
            break
        frames.append(StackFrame(
            instruction_pointer=frame.findtext('ip'),
            function=frame.findtext('fn'),
            file=frame.findtext('file'),
            line=safe_int(frame.findtext('line')) or None,
            directory=frame.findtext('dir'),
            object_file=frame.findtext('obj')
        ))
    return frames


def parse_valgrind_xml(xml_content: str, max_errors: int) -> ParseResult:
    """Parse Valgrind's XML output format.
    
    Valgrind's XML output is a documented, stable format designed for tool consumption.
    See: https://www.cs.cmu.edu/afs/cs.cmu.edu/project/cmt-40/Nice/RuleRefinement/bin/valgrind-3.2.0/docs/internals/xml-output.txt
    
    Key design decisions:
    - Separate memcheck errors from leak errors (different categories)
    - Error occurrences = SUM of errorcounts (not max)
    - Leak summary aggregated from Leak_* error kinds using explicit mapping
    - Parse failures are returned, not silently ignored
    """
    result = ParseResult()
    
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        result.parse_error = f"XML parse error: {e}"
        return result
    
    # Build mapping of unique_id -> kind for occurrence counting
    unique_id_to_kind: dict[str, str] = {}
    all_errors = root.findall('.//error')
    
    for error_elem in all_errors:
        kind = error_elem.findtext('kind', 'Unknown')
        unique_id = error_elem.findtext('unique')
        is_leak = kind.startswith('Leak_')
        
        if unique_id:
            unique_id_to_kind[unique_id] = kind
        
        # Parse error message
        what = error_elem.findtext('what')
        if not what:
            xwhat = error_elem.find('xwhat')
            what = xwhat.findtext('text', '') if xwhat is not None else ''
        
        # Parse stacks
        all_stacks = error_elem.findall('stack')
        main_stack = parse_stack_frames_from_xml(all_stacks[0], MAX_STACK_FRAMES) if all_stacks else []
        aux_stack = parse_stack_frames_from_xml(all_stacks[1], MAX_STACK_FRAMES) if len(all_stacks) > 1 else []
        
        error = ValgrindError(
            unique_id=unique_id,
            kind=kind,
            message=what,
            stack_frames=main_stack,
            auxiliary_message=error_elem.findtext('auxwhat'),
            auxiliary_stack=aux_stack
        )
        
        if is_leak:
            # Aggregate leak statistics using explicit kind mapping
            xwhat = error_elem.find('xwhat')
            if xwhat is not None and kind in LEAK_KIND_FIELDS:
                bytes_field, blocks_field = LEAK_KIND_FIELDS[kind]
                bytes_val = safe_int(xwhat.findtext('leakedbytes'))
                blocks_val = safe_int(xwhat.findtext('leakedblocks'))
                setattr(result.leak_summary, bytes_field, 
                        getattr(result.leak_summary, bytes_field) + bytes_val)
                setattr(result.leak_summary, blocks_field, 
                        getattr(result.leak_summary, blocks_field) + blocks_val)
            
            if len(result.leak_errors) < max_errors:
                result.leak_errors.append(error)
        else:
            if len(result.memcheck_errors) < max_errors:
                result.memcheck_errors.append(error)
    
    # Count contexts
    result.counts.memcheck_contexts = sum(1 for e in all_errors 
                                          if not e.findtext('kind', '').startswith('Leak_'))
    result.counts.leak_contexts = sum(1 for e in all_errors 
                                      if e.findtext('kind', '').startswith('Leak_'))
    
    # Count occurrences from <errorcounts> - SUM the counts, split by category
    errorcounts = root.find('.//errorcounts')
    if errorcounts is not None:
        memcheck_occ, leak_occ = 0, 0
        for pair in errorcounts.findall('pair'):
            unique_text = pair.findtext('unique')
            count = safe_int(pair.findtext('count'))
            if count > 0:
                kind = unique_id_to_kind.get(unique_text, '')
                if kind.startswith('Leak_'):
                    leak_occ += count
                else:
                    memcheck_occ += count
        
        result.counts.memcheck_occurrences = memcheck_occ or result.counts.memcheck_contexts
        result.counts.leak_occurrences = leak_occ or result.counts.leak_contexts
    else:
        result.counts.memcheck_occurrences = result.counts.memcheck_contexts
        result.counts.leak_occurrences = result.counts.leak_contexts
    
    return result


def merge_xml_results(xml_files: list[str], max_errors: int) -> tuple[
    list[ValgrindError], list[ValgrindError], LeakSummary, ErrorCounts, list[str]
]:
    """Merge results from multiple XML files (for multi-process programs).
    
    When a program forks, Valgrind with --xml-file=%p creates separate XML files
    for each process. This function merges all results into unified output.
    """
    all_memcheck: list[ValgrindError] = []
    all_leaks: list[ValgrindError] = []
    combined_summary = LeakSummary()
    combined_counts = ErrorCounts()
    parse_errors: list[str] = []
    
    for xml_file in xml_files:
        try:
            with open(xml_file, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            if not content.strip():
                parse_errors.append(f"{os.path.basename(xml_file)}: empty file")
                continue
            
            result = parse_valgrind_xml(content, max_errors)
            
            if result.parse_error:
                parse_errors.append(f"{os.path.basename(xml_file)}: {result.parse_error}")
                continue
            
            # Merge errors (respecting limits)
            remaining = max_errors - len(all_memcheck)
            if remaining > 0:
                all_memcheck.extend(result.memcheck_errors[:remaining])
            
            remaining = max_errors - len(all_leaks)
            if remaining > 0:
                all_leaks.extend(result.leak_errors[:remaining])
            
            # Aggregate leak summary
            for fld in ['definitely_lost_bytes', 'definitely_lost_blocks',
                          'indirectly_lost_bytes', 'indirectly_lost_blocks',
                          'possibly_lost_bytes', 'possibly_lost_blocks',
                          'still_reachable_bytes', 'still_reachable_blocks']:
                setattr(combined_summary, fld,
                        getattr(combined_summary, fld) + getattr(result.leak_summary, fld))
            
            # Aggregate counts
            combined_counts.memcheck_contexts += result.counts.memcheck_contexts
            combined_counts.memcheck_occurrences += result.counts.memcheck_occurrences
            combined_counts.leak_contexts += result.counts.leak_contexts
            combined_counts.leak_occurrences += result.counts.leak_occurrences
            
        except Exception as e:
            parse_errors.append(f"{os.path.basename(xml_file)}: {str(e)}")
    
    return all_memcheck, all_leaks, combined_summary, combined_counts, parse_errors


# ============================================================================
# MCP Tools
# ============================================================================

@mcp.tool()
def valgrind_check_available() -> str:
    """
    Check if Valgrind is available on the system.
    
    Returns a JSON object with:
    - available: boolean indicating if valgrind is installed and working
    - version: version string (e.g., "3.22.0")
    - path: absolute path to valgrind executable
    - message: human-readable status message
    """
    result = {
        "available": False,
        "version": None,
        "path": None,
        "message": ""
    }
    
    try:
        path = find_valgrind_path()
        if not path:
            result["message"] = "Valgrind not found in PATH"
            return json.dumps(result, indent=2)
        
        result["path"] = path
        
        version_result = subprocess.run(
            [path, '--version'], capture_output=True, text=True, timeout=10
        )
        
        if version_result.returncode == 0:
            result["available"] = True
            result["version"] = parse_valgrind_version(version_result.stdout) or version_result.stdout.strip()
            result["message"] = f"Valgrind {result['version']} is available"
        else:
            result["message"] = f"Valgrind found at {path} but --version failed"
    
    except subprocess.TimeoutExpired:
        result["message"] = "Timeout while checking valgrind availability"
    except Exception as e:
        result["message"] = f"Error checking valgrind: {str(e)}"
    
    return json.dumps(result, indent=2)


@mcp.tool()
def valgrind_memcheck_run(
    executable: str,
    args: list[str] | None = None,
    cwd: str | None = None,
    timeout_sec: int = 60,
    max_errors: int = MAX_ERRORS_DEFAULT,
    track_origins: bool = True,
    show_reachable: bool = False,
    trace_children: bool = False
) -> str:
    """
    Run Valgrind memcheck on an executable and return structured results.
    
    Memcheck detects memory errors including:
    - Invalid reads/writes (buffer overflows, use-after-free)
    - Memory leaks (definitely lost, possibly lost, indirectly lost)
    - Use of uninitialized values
    - Invalid frees (double-free, mismatched free)
    - Overlapping source/destination in memcpy/strcpy
    
    Valgrind runs the program to completion, then reports all issues found.
    This is a single-shot analysis.
    
    Args:
        executable: Path to the executable to analyze. Can be:
                    - Absolute path (e.g., "/path/to/app")
                    - Relative path (e.g., "build/app") - resolved relative to 
                      workspace root, or 'cwd' if specified.
        args: Command-line arguments to pass to the executable.
              Example: ["--input", "data.txt", "-v"]
        cwd: Working directory for execution. If omitted, defaults to workspace root.
        timeout_sec: Maximum seconds to wait for program completion (default: 60).
                     Increase for long-running programs. Returns "timeout" status
                     if exceeded.
        max_errors: Maximum detailed errors to return per category (default: 10).
                    Helps limit output size. Total error count is still reported.
        track_origins: When True (default), Valgrind tracks where uninitialized
                       values originated. This is slower but provides much more
                       useful debugging info (shows the allocation site, not just
                       the use site). Set False for faster analysis if you only
                       care about leaks.
        show_reachable: When True, reports "still reachable" memory as leaks.
                        Still-reachable memory is not freed but is still pointed
                        to at exit (not a true leak). Usually False (default) is
                        correct. Set True to audit all allocations.
        trace_children: When True, Valgrind follows child processes created via
                        fork/exec. Useful for test runners that spawn the actual
                        test binary. Default is False.
    
    Returns:
        JSON with:
        - status: "success", "partial", "error", or "timeout"
        - summary: Human-readable one-line summary
        - memcheck_errors: Array of memory errors (invalid read/write, etc.)
        - leak_errors: Array of leak reports with stack traces
        - leaks_summary: Bytes/blocks lost by category
        - exit_code: Program's exit code
    
    Note: Leak-check is always "full" in XML mode (Valgrind behavior).
    """
    global _workspace_directory
    args = args or []
    
    # Resolve executable path
    if not os.path.isabs(executable):
        # Relative path - resolve using cwd if provided, else workspace root
        if cwd:
            executable = os.path.join(cwd, executable)
        elif _workspace_directory:
            executable = os.path.join(_workspace_directory, executable)
        else:
            return make_result(
                "error",
                f"Relative executable path '{executable}' requires 'cwd' parameter "
                "or AID_WORKSPACE_ROOT to be set. Provide an absolute path or specify cwd."
            )
    
    # Determine working directory
    if cwd:
        work_dir = cwd
    elif _workspace_directory:
        work_dir = _workspace_directory
    else:
        work_dir = os.path.dirname(executable) or os.getcwd()
    
    # Validate executable exists and is runnable
    if not os.path.exists(executable):
        return make_result("error", f"Executable not found: {executable}")
    
    if not os.access(executable, os.X_OK):
        return make_result("error", f"File is not executable: {executable}")
    
    valgrind_path = find_valgrind_path()
    if not valgrind_path:
        return make_result("error", "Valgrind not found. Install with: sudo apt install valgrind")
    
    command_str = ""
    host_temp_dir = None
    
    try:
        # Create temp dir for XML output
        host_temp_dir = tempfile.mkdtemp(prefix='valgrind_')
        xml_pattern = os.path.join(host_temp_dir, 'valgrind_%p.xml')
        
        # Build valgrind command
        cmd = [
            valgrind_path, '--tool=memcheck', '-q',
            '--xml=yes', f'--xml-file={xml_pattern}',
            '--child-silent-after-fork=yes',
            f'--num-callers={MAX_STACK_FRAMES + 5}',
            '--error-limit=yes',
        ]
        
        if track_origins:
            cmd.append('--track-origins=yes')
        if show_reachable:
            cmd.append('--show-reachable=yes')
        if trace_children:
            cmd.append('--trace-children=yes')
        
        cmd.append(executable)
        cmd.extend(args)
        command_str = ' '.join(cmd)
        
        # Run valgrind locally
        result = subprocess.run(
            cmd, cwd=work_dir, capture_output=True, text=True, timeout=timeout_sec
        )
        
        # Find XML files
        xml_files = glob.glob(os.path.join(host_temp_dir, 'valgrind_*.xml'))
        if not xml_files:
            xml_files = glob.glob(os.path.join(host_temp_dir, '*.xml'))
        
        if not xml_files:
            return make_result(
                "error", "Valgrind produced no XML output files",
                exit_code=result.returncode,
                effective_leak_check="full (forced by XML mode)",
                raw_output=truncate_output(result.stderr) if result.stderr else None,
                command=command_str
            )
        
        # Parse and merge results
        memcheck_errors, leak_errors, leak_summary, counts, parse_errors = merge_xml_results(
            xml_files, max_errors
        )
        
        # Determine status
        if parse_errors and len(parse_errors) == len(xml_files):
            status = "error"
        elif parse_errors:
            status = "partial"
        else:
            status = "success"
        
        summary = build_human_summary(counts, leak_summary, result.returncode, parse_errors)
        
        return make_result(
            status, summary,
            exit_code=result.returncode,
            counts=counts,
            memcheck_errors=[serialize_error(e) for e in memcheck_errors],
            leak_errors=[serialize_error(e) for e in leak_errors],
            leaks_summary=asdict(leak_summary),
            effective_leak_check="full (forced by XML mode)",
            xml_parse_errors=parse_errors if parse_errors else None,
            raw_output=truncate_output(result.stderr) if result.stderr else None,
            command=command_str
        )
        
    except subprocess.TimeoutExpired:
        return make_result(
            "timeout", f"Execution timed out after {timeout_sec} seconds",
            command=command_str if command_str else None
        )
    
    except Exception as e:
        return make_result(
            "error", f"Error running valgrind: {str(e)}",
            command=command_str if command_str else None
        )
    
    finally:
        # Cleanup temp directory
        if host_temp_dir and os.path.exists(host_temp_dir):
            try:
                shutil.rmtree(host_temp_dir)
            except Exception:
                pass
