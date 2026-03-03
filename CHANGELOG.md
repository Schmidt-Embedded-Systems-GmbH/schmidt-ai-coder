# Schmidt AI Coder

## 0.1.0

### Minor Changes

- [#4](https://github.com/Schmidt-Embedded-Systems-GmbH/schmidt-ai-coder/pull/4) [`ed1031a`](https://github.com/Schmidt-Embedded-Systems-GmbH/schmidt-ai-coder/commit/ed1031a64ead02b189b762afd1583ffe5dc630c8) Thanks [@pwilcke](https://github.com/pwilcke)! - Initial release of Schmidt AI Coder - fork of Kilo Code with embedded systems focus

### Patch Changes

- [#6007](https://github.com/Kilo-Org/kilocode/pull/6007) [`39109ca`](https://github.com/Schmidt-Embedded-Systems-GmbH/schmidt-ai-coder/commit/39109ca06d719de2b468e4a73bc9da71bfbc327c) Thanks [@alex-alecu](https://github.com/alex-alecu)! - Show post-completion suggestions after `code` and `orchestrator` tasks to start `review` mode, including an option that clears context and starts a fresh review of uncommitted changes.

- [#5989](https://github.com/Kilo-Org/kilocode/pull/5989) [`7478c67`](https://github.com/Schmidt-Embedded-Systems-GmbH/schmidt-ai-coder/commit/7478c67f577a27d260e28eb83bec4d6a2583a8a8) Thanks [@pedroheyerdahl](https://github.com/pedroheyerdahl)! - Add X-KiloCode-Feature header for microdollar usage tracking

- [#6017](https://github.com/Kilo-Org/kilocode/pull/6017) [`34f7bc0`](https://github.com/Schmidt-Embedded-Systems-GmbH/schmidt-ai-coder/commit/34f7bc05d79081da2ccd03b3736e2bd359e7defa) Thanks [@PeterDaveHello](https://github.com/PeterDaveHello)! - Update Gemini default model metadata for Gemini 3.1 Pro and keep tool calling behavior consistent.

- [#5901](https://github.com/Kilo-Org/kilocode/pull/5901) [`8d7f102`](https://github.com/Schmidt-Embedded-Systems-GmbH/schmidt-ai-coder/commit/8d7f102e77178c6c40fc4a6f80130f041ee038f5) Thanks [@SkipperQ93](https://github.com/SkipperQ93)! - Fix: JetBrains editor initialization when ExtensionHostManager is missing from SystemObjectProvider

- [#5986](https://github.com/Kilo-Org/kilocode/pull/5986) [`fe0c0f0`](https://github.com/Schmidt-Embedded-Systems-GmbH/schmidt-ai-coder/commit/fe0c0f0cf914f5edf12d9683c01f2b53c0592291) Thanks [@imanolmzd-svg](https://github.com/imanolmzd-svg)! - Add promotion sign-up prompt when anonymous users hit the promotional model usage limit

- [#6014](https://github.com/Kilo-Org/kilocode/pull/6014) [`c5d23dd`](https://github.com/Schmidt-Embedded-Systems-GmbH/schmidt-ai-coder/commit/c5d23ddf47959fc1e8cf8207a93c736e7f31b2a7) Thanks [@imanolmzd-svg](https://github.com/imanolmzd-svg)! - Updated promotion warning text and translations across all 22 languages

## 0.0.1

### Initial Release

This is the first release of Schmidt AI Coder, a fork of Kilo Code tailored for embedded systems development.

### New Features

- **CMSIS SVD MCP Server**: Added MCP server for parsing and querying CMSIS SVD (System View Description) files. Enables the AI to understand peripheral registers, fields, and memory-mapped structures for embedded debugging.

- **GDB MCP Server**: Integrated GDB Machine Interface (MI) tools for debugging embedded targets. Supports breakpoints, memory inspection, register viewing, and execution control.

- **Valgrind MCP Server**: Added Valgrind integration for memory debugging and profiling.

- **Embedded Debugger Integration**: MCP servers are now integrated into the embedded debugger workflow with stateless HTTP support and diagnostics channel.
