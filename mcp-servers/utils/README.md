# Utils MCP Server

A lightweight set of static analysis and CLI utility tools for the **AID** system. It provides safe wrappers around common binary inspection tools.

## Tools

### Binary Inspection

- `utils_nm(file, args?)`: List symbols from object files.
- `utils_readelf(file, args?)`: Display ELF file information (headers, sections).
- `utils_objdump(file, args?)`: Disassemble binaries.
- `utils_addr2line(file, address)`: Map addresses to source lines (requires debug symbols).
- `utils_strings(file)`: Extract printable strings.

### Search

- `utils_grep(pattern, path, ...)`: Search text in files using `ripgrep` (preferred) or `grep`.
- `utils_check_available()`: Check which tools are installed on the system.
