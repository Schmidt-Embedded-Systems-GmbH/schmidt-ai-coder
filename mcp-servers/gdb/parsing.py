"""
GDB MI2 Response Parsing Module.

This module provides utilities for parsing GDB Machine Interface (MI2)
responses, extracting error messages, and cleaning console output.
"""

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class MIResponse:
    """
    Represents a parsed GDB MI2 response.
    
    Attributes:
        raw: The raw response string from GDB
        result_class: The result class (done, running, connected, error, exit)
        result_data: Parsed key-value data from the result record
        console_output: Cleaned console output (from ~ lines)
        is_success: True if command succeeded
        error_message: Error message if command failed
    """
    raw: str
    result_class: str
    result_data: dict[str, Any]
    console_output: str
    is_success: bool
    error_message: str | None = None


def extract_error_message(response: str) -> str:
    """
    Extract error message from GDB MI2 response.
    
    Handles escaped quotes and special characters in error messages.
    
    Args:
        response: Raw GDB response string
        
    Returns:
        Extracted error message or "Unknown error"
    """
    match = re.search(r'msg="((?:[^"\\]|\\.)*)"', response)
    if match:
        error_msg = match.group(1)
        error_msg = error_msg.replace('\\n', '\n')
        error_msg = error_msg.replace('\\"', '"')
        error_msg = error_msg.replace('\\t', '\t')
        error_msg = error_msg.replace('\\\\', '\\')
        return error_msg
    return "Unknown error"


def check_response_status(response: str) -> tuple[bool, str]:
    """
    Check if GDB response indicates success or error.
    
    Args:
        response: Raw GDB response string
        
    Returns:
        Tuple of (is_success, error_message)
    """
    if '^error' in response:
        return False, extract_error_message(response)
    elif '^done' in response:
        return True, ""
    elif '^running' in response:
        return True, ""
    elif '^connected' in response:
        return True, ""
    elif '^exit' in response:
        return True, ""
    else:
        return False, "Unexpected response format"


def parse_console_output(response: str) -> str:
    """
    Parse GDB MI2 console output and extract clean text.
    
    Console output lines start with ~ and contain escaped strings.
    
    Args:
        response: Raw GDB response string
        
    Returns:
        Cleaned console output
    """
    lines = response.split('\n')
    clean_lines = []
    
    for line in lines:
        line = line.strip()
        # Extract console output (lines starting with ~")
        if line.startswith('~"') and line.endswith('"'):
            # Remove the ~" prefix and " suffix, then unescape
            content = line[2:-1]
            content = _unescape_mi_string(content)
            
            # Skip empty lines
            if content.strip():
                clean_lines.append(content)
    
    return '\n'.join(clean_lines)


def _unescape_mi_string(s: str) -> str:
    """Unescape a GDB MI string."""
    s = s.replace('\\n', '\n')
    s = s.replace('\\"', '"')
    s = s.replace('\\t', '\t')
    s = s.replace('\\\\', '\\')
    return s


def parse_mi_response(response: str) -> MIResponse:
    """
    Parse a complete GDB MI2 response into structured data.
    
    Args:
        response: Raw GDB response string
        
    Returns:
        Parsed MIResponse object
    """
    is_success, error_msg = check_response_status(response)
    
    result_class = "unknown"
    if '^done' in response:
        result_class = "done"
    elif '^running' in response:
        result_class = "running"
    elif '^error' in response:
        result_class = "error"
    elif '^connected' in response:
        result_class = "connected"
    elif '^exit' in response:
        result_class = "exit"
    
    console_output = parse_console_output(response)
    result_data = _parse_result_data(response)
    
    return MIResponse(
        raw=response,
        result_class=result_class,
        result_data=result_data,
        console_output=console_output,
        is_success=is_success,
        error_message=error_msg if error_msg else None
    )


def _parse_result_data(response: str) -> dict[str, Any]:
    """
    Parse result data from MI response.
    
    This is a simplified parser that extracts common patterns.
    Full MI parsing would require a proper state machine.
    """
    data = {}
    
    thread_match = re.search(r'thread-id="(\d+)"', response)
    if thread_match:
        data['thread_id'] = thread_match.group(1)
    
    frame_match = re.search(r'frame=\{(.*?)\}', response)
    if frame_match:
        data['frame'] = frame_match.group(1)
    
    # Used by -data-evaluate-expression
    value_match = re.search(r'value="((?:[^"\\]|\\.)*)"', response)
    if value_match:
        data['value'] = _unescape_mi_string(value_match.group(1))
    
    bkpt_match = re.search(r'bkpt=\{(.*?)\}', response)
    if bkpt_match:
        data['breakpoint'] = bkpt_match.group(1)
    
    reason_match = re.search(r'reason="([^"]*)"', response)
    if reason_match:
        data['reason'] = reason_match.group(1)
    
    return data


def extract_program_output(response: str) -> str:
    """
    Extract program output from GDB response.
    
    Program output comes through MI stream records:
    - ~"..." (console stream) - most local program output
    - @"..." (target stream) - async/remote target output
    
    Args:
        response: Raw GDB response string
        
    Returns:
        Extracted program output
    """
    lines = response.split('\n')
    output_lines = []
    in_program_section = False
    
    for line in lines:
        line = line.strip()
        
        if line.startswith('^running') or line.startswith('*running'):
            in_program_section = True
            continue
        
        if line.startswith('*stopped'):
            break
        
        if not in_program_section:
            continue
        
        # Extract console stream output (~"...")
        if line.startswith('~"') and line.endswith('"'):
            content = line[2:-1]
            content = _unescape_mi_string(content)
            # Skip GDB system messages
            if not _is_gdb_system_message(content):
                output_lines.append(content)
        
        # Extract target stream output (@"...")
        elif line.startswith('@"') and line.endswith('"'):
            content = line[2:-1]
            content = _unescape_mi_string(content)
            output_lines.append(content)
    
    return ''.join(output_lines).strip()


def _is_gdb_system_message(text: str) -> bool:
    """Check if text is a GDB system message to filter out."""
    system_patterns = [
        'Reading symbols',
        'Downloading',
        '[New Thread',
        '[Thread ',
        'Using host libthread_db',
        'Thread debugging using',
        '[Inferior ',
        'process ',
    ]
    return any(p in text for p in system_patterns)


def format_tool_response(
    status: str = "ok",
    session_id: str | None = None,
    error: str | None = None,
    **extra
) -> dict[str, Any]:
    """
    Format a standardized tool response.
    
    Status "ok" is implicit - only "failed" status is included in response.
    
    Args:
        status: "ok" (implicit, not included) or "failed" (explicit)
        session_id: The session ID (optional)
        error: Error message if failed (optional)
        **extra: Additional fields to include
        
    Returns:
        Formatted response dictionary
    """
    result = {}
    
    if status == "failed":
        result["status"] = "failed"
        if error:
            result["error"] = error
    
    if session_id is not None:
        result["session_id"] = session_id
    
    result.update(extra)
    
    return result


# =============================================================================
# Structured Parsing for High-Frequency Tools
# These extract clean, minimal structured data from verbose MI responses
# =============================================================================


def parse_breakpoints(response: str) -> list[dict[str, Any]]:
    """
    Parse breakpoint list from MI response into structured data.
    
    Extracts key fields from verbose MI BreakpointTable format.
    
    Args:
        response: Raw MI response from -break-list
        
    Returns:
        List of breakpoint dicts with: number, enabled, addr, func, file, line
    """
    breakpoints = []
    
    # Pattern handles nested braces in bkpt={...} entries
    bkpt_pattern = r'bkpt=\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}'
    
    for match in re.finditer(bkpt_pattern, response):
        bkpt_str = match.group(1)
        bp = {}
        
        number = re.search(r'number="([^"]*)"', bkpt_str)
        if number:
            bp['number'] = number.group(1)
        
        enabled = re.search(r'enabled="([^"]*)"', bkpt_str)
        if enabled:
            bp['enabled'] = enabled.group(1) == 'y'
        
        addr = re.search(r'addr="([^"]*)"', bkpt_str)
        if addr:
            bp['addr'] = addr.group(1)
        
        func = re.search(r'func="([^"]*)"', bkpt_str)
        if func:
            bp['func'] = _unescape_mi_string(func.group(1))
        
        file_match = re.search(r'file="([^"]*)"', bkpt_str)
        if file_match:
            bp['file'] = _unescape_mi_string(file_match.group(1))
        
        line = re.search(r'line="([^"]*)"', bkpt_str)
        if line:
            bp['line'] = int(line.group(1))
        
        bp_type = re.search(r'type="([^"]*)"', bkpt_str)
        if bp_type:
            bp['type'] = bp_type.group(1)
        
        if bp:  # Only add if we extracted something
            breakpoints.append(bp)
    
    return breakpoints


def parse_stack_frames(response: str) -> list[dict[str, Any]]:
    """
    Parse stack frames from MI response into structured data.
    
    Extracts key fields from verbose MI stack format.
    
    Args:
        response: Raw MI response from -stack-list-frames
        
    Returns:
        List of frame dicts with: level, func, file, line, addr
    """
    frames = []
    
    frame_pattern = r'frame=\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}'
    
    for match in re.finditer(frame_pattern, response):
        frame_str = match.group(1)
        frame = {}
        
        level = re.search(r'level="([^"]*)"', frame_str)
        if level:
            frame['level'] = int(level.group(1))
        
        func = re.search(r'func="([^"]*)"', frame_str)
        if func:
            frame['func'] = _unescape_mi_string(func.group(1))
        
        file_match = re.search(r'file="([^"]*)"', frame_str)
        if file_match:
            frame['file'] = _unescape_mi_string(file_match.group(1))
        
        line = re.search(r'line="([^"]*)"', frame_str)
        if line:
            frame['line'] = int(line.group(1))
        
        addr = re.search(r'addr="([^"]*)"', frame_str)
        if addr:
            frame['addr'] = addr.group(1)
        
        if frame:
            frames.append(frame)
    
    return frames


def parse_variables(response: str) -> list[dict[str, Any]]:
    """
    Parse local variables from MI response into structured data.
    
    Args:
        response: Raw MI response from -stack-list-locals
        
    Returns:
        List of variable dicts with: name, type, value
    """
    variables = []
    
    # Match locals=[...] or args=[...]
    # Variables are in format: {name="x",type="int",value="42"}
    # Use robust pattern that handles escaped quotes in values: ((?:[^"\\]|\\.)*)
    var_pattern = r'\{name="((?:[^"\\]|\\.)*)?"(?:,type="((?:[^"\\]|\\.)*)")?(?:,value="((?:[^"\\]|\\.)*)")?\}'
    
    for match in re.finditer(var_pattern, response):
        var = {'name': _unescape_mi_string(match.group(1)) if match.group(1) else ''}
        if match.group(2):
            var['type'] = _unescape_mi_string(match.group(2))
        if match.group(3):
            var['value'] = _unescape_mi_string(match.group(3))
        variables.append(var)
    
    return variables


def parse_memory(response: str) -> dict[str, Any]:
    """
    Parse memory read response into structured data.
    
    Args:
        response: Raw MI response from -data-read-memory
        
    Returns:
        Dict with: addr, next_row, contents (list of hex values)
    """
    result = {}
    
    addr = re.search(r'addr="([^"]*)"', response)
    if addr:
        result['addr'] = addr.group(1)
    
    next_row = re.search(r'next-row="([^"]*)"', response)
    if next_row:
        result['next_row'] = next_row.group(1)
    
    # MI format: data=["0x00","0x01",...]
    data_match = re.search(r'data=\["([^]]+)"\]', response)
    if data_match:
        data_str = data_match.group(0)
        values = re.findall(r'"(0x[0-9a-fA-F]+)"', data_str)
        result['contents'] = values
    
    return result
