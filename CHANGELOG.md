# Schmidt AI Coder

## 0.0.1

### Initial Release

This is the first release of Schmidt AI Coder, a fork of Kilo Code tailored for embedded systems development.

### New Features

- **CMSIS SVD MCP Server**: Added MCP server for parsing and querying CMSIS SVD (System View Description) files. Enables the AI to understand peripheral registers, fields, and memory-mapped structures for embedded debugging.

- **GDB MCP Server**: Integrated GDB Machine Interface (MI) tools for debugging embedded targets. Supports breakpoints, memory inspection, register viewing, and execution control.

- **Valgrind MCP Server**: Added Valgrind integration for memory debugging and profiling.

- **Embedded Debugger Integration**: MCP servers are now integrated into the embedded debugger workflow with stateless HTTP support and diagnostics channel.
