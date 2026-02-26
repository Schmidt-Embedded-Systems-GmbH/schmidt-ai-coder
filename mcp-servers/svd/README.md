# CMSIS-SVD MCP Server

An MCP server that exposes CMSIS-SVD device metadata to LLM agents for embedded debugging in VS Code.

## Overview

This server provides tools and resources for querying CMSIS-SVD (System View Description) files, enabling AI assistants to understand microcontroller peripherals, registers, and bit fields during debugging sessions.

## Features

- **Load SVD Files**: Parse and cache SVD files for efficient querying
- **Peripheral Discovery**: List and search peripherals by name
- **Register Inspection**: Get detailed register information including fields and enumerated values
- **Field Analysis**: Query individual bit fields with masks and access information
- **Value Decoding**: Decode register values into human-readable field values
- **Value Encoding**: Compute register values from field specifications
- **Markdown Resources**: Human-readable documentation for VS Code context

## Prerequisites

- Python 3.11+
- `uv` package manager (recommended) or pip

## Installation

### Using uv (recommended)

```bash
cd mcp-servers/svd
uv sync
```

### Using pip

```bash
cd mcp-servers/svd
pip install -e .
```

## Usage

### Running the Server

```bash
# Using uv
uv run fastmcp run mcp_cmsis_svd/server.py

# Or directly
python -m mcp_cmsis_svd.server
```

### VS Code Configuration

Add to your `.vscode/mcp.json`:

```json
{
	"servers": {
		"cmsis-svd": {
			"command": "uv",
			"args": ["run", "--directory", "/path/to/mcp-servers/svd", "fastmcp", "run", "mcp_cmsis_svd/server.py"]
		}
	}
}
```

Or with a specific SVD file pre-loaded:

```json
{
	"servers": {
		"cmsis-svd": {
			"command": "uv",
			"args": ["run", "--directory", "/path/to/mcp-servers/svd", "fastmcp", "run", "mcp_cmsis_svd/server.py"],
			"env": {
				"SVD_PATH": "/path/to/your/device.svd"
			}
		}
	}
}
```

## Tools

### Device Management

| Tool                             | Description                  |
| -------------------------------- | ---------------------------- |
| `svd_load(path, strict=False)`   | Load and parse an SVD file   |
| `svd_device_summary(device_id?)` | Get summary of loaded device |

### Peripheral Access

| Tool                                                       | Description            |
| ---------------------------------------------------------- | ---------------------- |
| `svd_list_peripherals(filter?, limit, offset, device_id?)` | List peripherals       |
| `svd_get_peripheral(peripheral, device_id?)`               | Get peripheral details |

### Register Access

| Tool                                                        | Description                      |
| ----------------------------------------------------------- | -------------------------------- |
| `svd_list_registers(peripheral, limit, offset, device_id?)` | List registers                   |
| `svd_get_register(peripheral, register, device_id?)`        | Get register details with fields |

### Field Access

| Tool                                                     | Description       |
| -------------------------------------------------------- | ----------------- |
| `svd_get_field(peripheral, register, field, device_id?)` | Get field details |

### Search & Resolve

| Tool                                               | Description                      |
| -------------------------------------------------- | -------------------------------- |
| `svd_search(query, kind="any", limit, device_id?)` | Search components                |
| `svd_resolve(path, device_id?)`                    | Resolve canonical or dotted path |

### Decode/Encode

| Tool                                                                                     | Description           |
| ---------------------------------------------------------------------------------------- | --------------------- |
| `svd_decode_register_value(peripheral, register, value, device_id?)`                     | Decode register value |
| `svd_encode_register_value(peripheral, register, field_values, base_value?, device_id?)` | Encode field values   |

### Validation

| Tool                              | Description       |
| --------------------------------- | ----------------- |
| `svd_validate(path?, device_id?)` | Validate SVD file |

## Resources

Resources provide markdown-formatted documentation for VS Code's "Add Context" feature:

| Resource URI                                  | Description        |
| --------------------------------------------- | ------------------ |
| `svd://device`                                | Device summary     |
| `svd://peripheral/{name}`                     | Peripheral details |
| `svd://peripheral/{p}/register/{r}`           | Register details   |
| `svd://peripheral/{p}/register/{r}/field/{f}` | Field details      |
| `svd://search?q={query}`                      | Search results     |

## Prompts

User-invoked workflows for common tasks:

| Prompt                                              | Description                             |
| --------------------------------------------------- | --------------------------------------- |
| `svd_explain_register(peripheral, register)`        | Explain a register's purpose and fields |
| `svd_decode_value(peripheral, register, value_hex)` | Decode and explain a register value     |
| `svd_find_related(keyword)`                         | Find components related to a keyword    |

## Canonical Paths

Components are identified by canonical paths:

- **Peripheral**: `PERIPHERAL:<name>` (e.g., `PERIPHERAL:GPIOA`)
- **Register**: `REG:<peripheral>.<register>` (e.g., `REG:GPIOA.MODER`)
- **Field**: `FIELD:<peripheral>.<register>.<field>` (e.g., `FIELD:GPIOA.MODER.MODE0`)

Dotted paths are also supported (e.g., `GPIOA.MODER`).

## Example Workflow

```
1. Load SVD file:
   svd_load(path="/path/to/STM32F407.svd")

2. Find a peripheral:
   svd_search(query="GPIO", kind="peripheral")

3. Get peripheral details:
   svd_get_peripheral(peripheral="GPIOA")

4. List registers:
   svd_list_registers(peripheral="GPIOA")

5. Get register with fields:
   svd_get_register(peripheral="GPIOA", register="MODER")

6. Decode a register value:
   svd_decode_register_value(
     peripheral="GPIOA",
     register="MODER",
     value=0x00000005
   )

7. Encode field values:
   svd_encode_register_value(
     peripheral="GPIOA",
     register="MODER",
     field_values={"MODE0": "Output", "MODE1": "Input"}
   )
```

## Development

### Running Tests

```bash
cd mcp-servers/svd
uv run pytest
```

### Project Structure

```
mcp-servers/svd/
├── mcp_cmsis_svd/
│   ├── __init__.py      # Package init
│   ├── server.py        # FastMCP server entry point
│   ├── svd_store.py     # SVD loading, caching, indexing
│   ├── model.py         # Pydantic models for outputs
│   └── formatters.py    # Markdown formatters for resources
├── tests/
│   ├── test_svd_store.py
│   └── fixtures/
│       └── minimal.svd  # Test SVD file
├── pyproject.toml
└── README.md
```

## Integration with GDB

This SVD server complements the GDB MCP server for embedded debugging:

1. Use **GDB server** to read/write memory and control execution
2. Use **SVD server** to interpret register names and bit fields

Example combined workflow:

```
# Get register address from SVD
svd_resolve(path="GPIOA.ODR")
# Returns: absolute_address=0x40020014

# Read the register via GDB
gdb_eval(session_id="...", expression="*(uint32_t*)0x40020014")
# Returns: 0x00000001

# Decode the value using SVD
svd_decode_register_value(peripheral="GPIOA", register="ODR", value=1)
# Returns: ODR0=1 (Pin 0 is HIGH)
```

## License

This project is part of the Schmidt AI Coder extension.

## References

- [CMSIS-SVD Specification](https://arm-software.github.io/CMSIS_5/SVD/html/index.html)
- [FastMCP Documentation](https://gofastmcp.com)
- [MCP Specification](https://modelcontextprotocol.io)
