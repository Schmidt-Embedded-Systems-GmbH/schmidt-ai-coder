# Build System MCP Server

This MCP server provides build automation capabilities for C/C++ projects, primarily focusing on `make`-based workflows. It is part of the **AID** system developed for the bachelor's thesis _"KI-Unterstützung bei Debugging-Prozessen mithilfe von MCP-Servern"_.

## Features

- **Makefile Execution**: Run `make` targets with custom arguments and timeouts.
- **Target Analysis**: parsing of available makefile targets (via `make help` or regex parsing).
- **Project Structure**: Works with standard `Makefile` or custom filenames.

## Prerequisites

- **Python 3.12+** (managed via `uv`)
- **GNU Make** installed and in `$PATH`
- A valid `Makefile` in the target directory

## Tools

### `execute_makefile`

Runs a `make` command.

- **target**: The make target (e.g., `all`, `clean`, `test`). Default: default target.
- **directory**: Working directory containing the Makefile.
- **makefile_path**: Optional custom filename (e.g., `Makefile.debug`).
- **extra_args**: Additional flags (e.g., `-j4`, `V=1`).
- **timeout**: Execution timeout in seconds (default: 300).

### `list_makefile_targets`

discovered targets in a Makefile.

- **directory**: Working directory.
- **makefile_path**: Optional custom filename.

## Usage

Start the server using `uv`:

```bash
uv run --with fastmcp fastmcp run build_system/main.py -t http -p 8003
```

## Security

This server executes shell commands (`make`). It should only be used in trusted environments. In the AID system, its access is controlled via the **Tool Policy** (ASK/DO modes).
