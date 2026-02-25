"""
GDB Session Management Module.

This module provides the GDBSession dataclass and SessionManager class
for managing GDB debugging sessions with async process I/O.

Design: Synchronous MI mode
- GDB runs in default synchronous mode (not mi-async)
- Execution commands block until the program stops
- Simple and predictable behavior

Container-Built Binaries:
- When container_build_path is set, binaries were built in a container
  but GDB runs on the host. Path substitution is set up so GDB can
  find source files referenced by debug symbols.
"""

import asyncio
import os
import secrets
from dataclasses import dataclass, field


class SessionNotFoundError(Exception):
    """Raised when a session ID is not found."""
    pass


class SessionNotActiveError(Exception):
    """Raised when a session process is no longer active."""
    pass


class SessionNotInitializedError(Exception):
    """Raised when a session is not properly initialized."""
    pass


@dataclass
class GDBSession:
    process: asyncio.subprocess.Process
    session_id: str
    cwd: str
    gdb_path: str
    target: str | None = None
    initialized: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    
    def is_active(self) -> bool:
        return self.process.returncode is None


class SessionManager:
    """
    Manages multiple GDB sessions.
    
    Each session has its own asyncio.Lock to prevent command interleaving.
    When container_build_path is set, path substitution is configured
    automatically so GDB can find source files for container-built binaries.
    """
    
    def __init__(
        self,
        workspace_root: str | None = None,
        container_build_path: str | None = None
    ):
        self._sessions: dict[str, GDBSession] = {}
        self._manager_lock = asyncio.Lock()
        self.workspace_root = workspace_root
        self.container_build_path = container_build_path
    
    async def create(self, gdb_path: str, cwd: str) -> GDBSession:
        """
        Create a new GDB session.
        
        GDB is spawned directly on the host. If container_build_path is set,
        path substitution is configured so GDB can find source files for
        binaries that were built inside a container.
        
        Args:
            gdb_path: Path to GDB executable (e.g., "gdb", "gdb-multiarch", "/usr/bin/gdb").
            cwd: Working directory for the GDB session.
            
        Returns:
            The created GDBSession
            
        Raises:
            FileNotFoundError: If gdb_path doesn't exist or isn't executable
            ValueError: If cwd doesn't exist
        """
        if not os.path.exists(cwd):
            raise ValueError(f"Working directory does not exist: {cwd}")
        
        if not os.path.isdir(cwd):
            raise ValueError(f"Path is not a directory: {cwd}")
        
        session_id = secrets.token_hex(4)
        
        # Merge stderr into stdout to prevent buffer deadlock
        try:
            process = await asyncio.create_subprocess_exec(
                gdb_path,
                "--interpreter=mi2",
                "--quiet",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=cwd
            )
        except FileNotFoundError:
            raise FileNotFoundError(f"GDB executable not found: {gdb_path}")
        except PermissionError:
            raise PermissionError(f"Permission denied executing: {gdb_path}")
        
        session = GDBSession(
            process=process,
            session_id=session_id,
            cwd=cwd,
            gdb_path=gdb_path,
        )
        
        initialized = await self._initialize_session(session)
        if not initialized:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except (ProcessLookupError, asyncio.TimeoutError):
                process.kill()
            raise RuntimeError("Failed to initialize GDB session - no prompt received")
        
        # Set up path substitution for container-built binaries
        # This allows GDB to find source files when debug symbols contain container paths
        if self.container_build_path and self.workspace_root:
            await self._setup_path_substitution(session)
        
        async with self._manager_lock:
            self._sessions[session_id] = session
        
        return session
    
    async def _initialize_session(self, session: GDBSession, timeout: float = 5.0) -> bool:
        """Consume startup messages and wait for the (gdb) prompt."""
        if session.initialized:
            return True
        
        try:
            start_time = asyncio.get_event_loop().time()
            
            while asyncio.get_event_loop().time() - start_time < timeout:
                if not session.is_active():
                    return False
                
                try:
                    data = await asyncio.wait_for(
                        session.process.stdout.readline(),
                        timeout=0.5
                    )
                    if data:
                        line = data.decode('utf-8', errors='replace').strip()
                        if line == "(gdb)":
                            session.initialized = True
                            return True
                except asyncio.TimeoutError:
                    continue
            
            return False
            
        except Exception:
            return False
    
    async def _setup_path_substitution(self, session: GDBSession) -> None:
        """
        Set up path substitution for container-built binaries.
        
        When binaries are built in a container (e.g., at /home/jq) but debugged
        on the host, debug symbols contain container paths. This sets up GDB's
        substitute-path to translate container paths to host paths.
        
        Example:
            Container build: /home/jq/src/main.c
            Host workspace:  /home/user/.../repo/src/main.c
            Substitution:    /home/jq -> /home/user/.../repo
        """
        if not self.container_build_path or not self.workspace_root:
            return
        
        try:
            # set substitute-path <from> <to>
            cmd = f'set substitute-path {self.container_build_path} {self.workspace_root}'
            
            session.process.stdin.write((cmd + '\n').encode('utf-8'))
            await session.process.stdin.drain()
            
            # Can't use send_command here — substitute-path is a CLI command,
            # not MI, so it just prints the (gdb) prompt
            try:
                await asyncio.wait_for(
                    session.process.stdout.readline(),
                    timeout=2.0
                )
            except asyncio.TimeoutError:
                pass  # Best effort
                
        except Exception:
            # Path substitution is nice-to-have, don't fail session creation
            pass
    
    async def get(self, session_id: str) -> GDBSession:
        """
        Get a session by ID.
        
        Args:
            session_id: The session ID to look up
            
        Returns:
            The GDBSession
            
        Raises:
            SessionNotFoundError: If session doesn't exist
            SessionNotActiveError: If session process has terminated
            SessionNotInitializedError: If session isn't initialized
        """
        async with self._manager_lock:
            if session_id not in self._sessions:
                raise SessionNotFoundError(f"Session not found: {session_id}")
            
            session = self._sessions[session_id]
        
        if not session.is_active():
            raise SessionNotActiveError(f"Session is no longer active: {session_id}")
        
        if not session.initialized:
            if not await self._initialize_session(session):
                raise SessionNotInitializedError(f"Session not initialized: {session_id}")
        
        return session
    
    async def stop(self, session_id: str) -> bool:
        """
        Stop a session and clean up resources.
        
        Args:
            session_id: The session ID to stop
            
        Returns:
            True if stopped normally, False if force-killed
            
        Raises:
            SessionNotFoundError: If session doesn't exist
        """
        async with self._manager_lock:
            if session_id not in self._sessions:
                raise SessionNotFoundError(f"Session not found: {session_id}")
            
            session = self._sessions.pop(session_id)
        
        force_killed = False
        
        if session.is_active():
            try:
                async with session.lock:
                    session.process.stdin.write(b"-gdb-exit\n")
                    await session.process.stdin.drain()
                
                await asyncio.wait_for(session.process.wait(), timeout=5.0)
                
            except asyncio.TimeoutError:
                session.process.kill()
                await session.process.wait()
                force_killed = True
                
            except (ProcessLookupError, BrokenPipeError):
                # Process already gone
                pass
        
        return not force_killed
    
    def list_all(self) -> list[str]:
        return list(self._sessions.keys())
    
    async def stop_all(self) -> int:
        """Stop all active sessions. Returns number stopped."""
        session_ids = list(self._sessions.keys())
        count = 0
        for session_id in session_ids:
            try:
                await self.stop(session_id)
                count += 1
            except SessionNotFoundError:
                pass
        return count
