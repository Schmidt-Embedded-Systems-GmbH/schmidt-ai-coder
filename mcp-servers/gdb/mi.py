"""
GDB Machine Interface (MI) Transport Module.

This module provides async I/O for communicating with GDB via the MI2 protocol.
It handles command sending, response reading with timeouts, and proper locking
to prevent command interleaving.

Design: Simple and synchronous
- Single unified send_command API
- GDB runs in synchronous mode (execution commands block until stop)
- Prompt-aware response reading
- On timeout, drain buffer to keep session usable
"""

import asyncio

from session import GDBSession
from parsing import MIResponse, parse_mi_response


class CommandTimeoutError(Exception):
    """Raised when a GDB command times out."""
    pass


class CommandError(Exception):
    """Raised when a GDB command fails."""
    pass


# The GDB prompt marker used as a delimiter for response completion
PROMPT = "(gdb)"


class MITransport:
    """
    Handles communication with GDB via the MI2 protocol.
    
    Uses async I/O and proper locking to prevent command interleaving
    when multiple tools access the same session concurrently.
    """
    
    def __init__(self, session: GDBSession):
        self.session = session
    
    async def send_command(
        self,
        command: str,
        timeout: float = 30.0,
        wait_for_stop: bool = False
    ) -> MIResponse:
        """
        Send a command to GDB and wait for response.
        
        Args:
            command: The MI command to send (without trailing newline)
            timeout: Maximum time to wait for response in seconds
            wait_for_stop: If True, wait for *stopped notification (for execution commands)
            
        Returns:
            Parsed MIResponse
            
        Raises:
            CommandTimeoutError: If response doesn't arrive within timeout
            CommandError: If the command fails
        """
        async with self.session.lock:
            return await self._send_command_locked(command, timeout, wait_for_stop)
    
    async def _send_command_locked(
        self,
        command: str,
        timeout: float,
        wait_for_stop: bool
    ) -> MIResponse:
        """Send command while holding the session lock."""
        process = self.session.process
        
        if not self.session.is_active():
            raise CommandError("GDB process is no longer active")
        
        cmd_bytes = f"{command}\n".encode('utf-8')
        process.stdin.write(cmd_bytes)
        await process.stdin.drain()
        
        try:
            response = await asyncio.wait_for(
                self._read_response(wait_for_stop),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            # On timeout, drain buffer to keep session usable for non-execution commands
            await self._drain_buffer()
            raise CommandTimeoutError(
                f"Command timed out after {timeout}s: {command}"
            )
        
        return parse_mi_response(response)
    
    async def _drain_buffer(self) -> None:
        """Drain pending output after a timeout so subsequent commands don't read stale data."""
        process = self.session.process
        
        if not self.session.is_active():
            return
        
        try:
            # Read until no more output (short timeout per read)
            while True:
                try:
                    await asyncio.wait_for(
                        process.stdout.readline(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    # No more output
                    break
        except Exception:
            pass
    
    async def _read_response(self, wait_for_stop: bool = False) -> str:
        """
        Read a complete GDB MI2 response.
        
        In synchronous mode (default), GDB blocks on execution commands
        until the program stops, then sends all output together.
        
        Termination logic:
        - Non-execution (wait_for_stop=False):
          Read until we have a result record (^...) AND see the (gdb) prompt.
        - Execution (wait_for_stop=True):
          Read until we see (*stopped OR ^error) AND then the (gdb) prompt.
        """
        response_lines = []
        process = self.session.process
        
        saw_result = False      # Saw a result record (^...)
        saw_stop = False        # Saw *stopped
        saw_error = False       # Saw ^error
        
        while True:
            if not self.session.is_active():
                break
            
            try:
                line_bytes = await process.stdout.readline()
                if not line_bytes:
                    break
                
                line = line_bytes.decode('utf-8', errors='replace').strip()
                
                if line == PROMPT:
                    if not wait_for_stop:
                        # Non-execution: exit on result + prompt
                        if saw_result:
                            break
                        continue
                    else:
                        # Execution: exit on (stop or error) + prompt
                        if saw_stop or saw_error:
                            break
                        # In sync mode, if we got result but no stop yet, keep reading
                        continue
                
                # Collect non-prompt lines
                if line:
                    response_lines.append(line)
                    
                    if line.startswith('^'):
                        saw_result = True
                        if line.startswith('^error'):
                            saw_error = True
                    elif line.startswith('*stopped'):
                        saw_stop = True
                        
            except Exception:
                break
        
        return '\n'.join(response_lines)


async def send_command(
    session: GDBSession,
    command: str,
    timeout: float = 30.0,
    wait_for_stop: bool = False
) -> MIResponse:
    """
    Convenience function to send a command to a session.
    
    Args:
        session: The GDBSession to use
        command: The MI command to send
        timeout: Maximum time to wait (default 30s)
        wait_for_stop: If True, wait for *stopped (for execution commands)
        
    Returns:
        Parsed MIResponse
    """
    transport = MITransport(session)
    return await transport.send_command(command, timeout=timeout, wait_for_stop=wait_for_stop)
