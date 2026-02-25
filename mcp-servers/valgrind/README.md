# Valgrind MCP Server

An MCP server wrapper for **Valgrind Memcheck** to detect memory errors in C/C++ applications. It is part of the **AID** system.

## Features

- **Structured Output**: Parses Valgrind's XML output into clean JSON for LLM consumption.
- **Robustness**: Handles multi-process applications (forks) and merges output.
- **Error Context**: Provides detailed stack traces for leaks, uninitialized memory, and invalid accesses.

## Prerequisites

- **Python 3.12+** (managed via `uv`)
- **Valgrind** (`sudo apt install valgrind`)

## Tools

### `valgrind_memcheck_run`

Executes a binary under Valgrind supervision.

- **executable**: Path to the binary.
- **args**: Command line arguments for the target.
- **cwd**: Working directory.
- **timeout**: Max execution time in seconds.
- **track_origins**: Enable origin tracking (default: true).

### `valgrind_check_available`

Checks if Valgrind is installed and returns the version.

## Usage

Start the server:

```bash
uv run --with fastmcp fastmcp run valgrind/main.py -t http -p 8006
```
