# Schmidt AI Coder

## 0.2.0 (11-03-2026)

### Minor Changes

- MCU Specs MCP server for datasheet ingestion and search
- Qdrant settings UI for MCU Specs configuration
- Agent Manager logo rendering and sizing improvements

## 0.1.0

### Minor Changes

- Initial release of Schmidt AI Coder - fork of Kilo Code with embedded systems focus

### Patch Changes

- Show post-completion suggestions after `code` and `orchestrator` tasks to start `review` mode, including an option that clears context and starts a fresh review of uncommitted changes.
- Add X-KiloCode-Feature header for microdollar usage tracking
- Update Gemini default model metadata for Gemini 3.1 Pro and keep tool calling behavior consistent.
- Fix: JetBrains editor initialization when ExtensionHostManager is missing from SystemObjectProvider
- Add promotion sign-up prompt when anonymous users hit the promotional model usage limit
- Updated promotion warning text and translations across all 22 languages

## 0.0.1

### Initial Release

This is the first release of Schmidt AI Coder, a fork of Kilo Code tailored for embedded systems development.

### New Features

- **CMSIS SVD MCP Server**: Added MCP server for parsing and querying CMSIS SVD (System View Description) files. Enables the AI to understand peripheral registers, fields, and memory-mapped structures for embedded debugging.

- **GDB MCP Server**: Integrated GDB Machine Interface (MI) tools for debugging embedded targets. Supports breakpoints, memory inspection, register viewing, and execution control.

- **Valgrind MCP Server**: Added Valgrind integration for memory debugging and profiling.

- **Embedded Debugger Integration**: MCP servers are now integrated into the embedded debugger workflow with stateless HTTP support and diagnostics channel.
