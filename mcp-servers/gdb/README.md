# GDB MCP Server

A modular GDB debugging server for the **AID** system. It exposes GDB's Machine Interface (MI2) via structured MCP tools, enabling agents to control debug sessions, inspect state, and manipulate execution.

## Features

- **Session Management**: Handle multiple independent GDB sessions.
- **MI2 Protocol**: Uses robust machine-readable communication with GDB (not text parsing).
- **Unified Breakpoints**: Set, list, and manage breakpoints programmatically.
- **Remote Debugging**: Support for J-Link, OpenOCD, and other remote targets.

## Prerequisites

- **Python 3.12+** (managed via `uv`)
- **GDB**: `gdb-multiarch` (recommended) or standard `gdb`.

## Tools

### Session & Lifecycle

- `gdb_start(cwd, gdb_path)`: Start a new session. Returns `session_id`.
- `gdb_stop(session_id)`: Terminate a session.
- `gdb_session_list()`: List active sessions.

### Execution Control

- `gdb_load(session_id, executable)`: Load a binary.
- `gdb_run(session_id, args)`: Start execution.
- `gdb_continue(session_id)`, `gdb_step`, `gdb_next`, `gdb_finish`.
- **Note**: Execution commands block until the target stops (breakpoint or signal).

### Inspection & State

- `gdb_eval(session_id, expression)`: Evaluate C/C++ expressions.
- `gdb_backtrace(session_id)`: Get stack trace.
- `gdb_locals(session_id)`, `gdb_registers(session_id)`.
- `gdb_memory(session_id, action, address)`: Read/Write raw memory.

### Breakpoints

- `gdb_breakpoint(session_id, action, location)`: `set`, `delete`, `enable`, `disable`.

## Usage

Start the server:

```bash
uv run --with fastmcp fastmcp run gdb/main.py -t http -p 8002
```

## Limitations

- **Stateful**: Agents must maintain the `session_id`.
- **Blocking**: Long-running commands will block the agent until GDB returns control (paused).
