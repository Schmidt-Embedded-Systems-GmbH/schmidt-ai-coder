// kilocode_change - new file
//
// Manages the lifecycle of bundled AID MCP servers (Python/FastMCP processes)
// and registers them with McpHub as builtin servers.

import * as vscode from "vscode"
import * as path from "path"
import * as fs from "fs"
import { spawn, type ChildProcess } from "child_process"
import { McpHub, type McpSource } from "../mcp/McpHub"
import { McpServerManager } from "../mcp/McpServerManager"
import { ClineProvider } from "../../core/webview/ClineProvider"

interface AidServerDefinition {
	key: string
	displayName: string
	description: string
	defaultPort: number
	folderName: string
	requiresWorkspace: boolean
	startupArgs?: (port: number) => string[]
	toolTimeout?: number // in seconds (McpHub schema max: 3600)
}

const AID_MCP_SERVERS: AidServerDefinition[] = [
	{
		key: "aid-gdb",
		displayName: "GDB",
		description: "Interactive debugging via GDB/MI2",
		defaultPort: 8002,
		folderName: "gdb",
		requiresWorkspace: false,
		toolTimeout: 120,
	},
	{
		key: "aid-build-system",
		displayName: "Build System",
		description: "Makefile execution and target discovery",
		defaultPort: 8003,
		folderName: "build_system",
		requiresWorkspace: false,
	},
	{
		key: "aid-valgrind",
		displayName: "Valgrind",
		description: "Memory analysis with Valgrind Memcheck",
		defaultPort: 8006,
		folderName: "valgrind",
		requiresWorkspace: false,
		toolTimeout: 120,
	},
	{
		key: "aid-utils",
		displayName: "Utils",
		description: "Static binary inspection (nm, readelf, objdump, strings, addr2line)",
		defaultPort: 8007,
		folderName: "utils",
		requiresWorkspace: false,
	},
	{
		key: "aid-linter",
		displayName: "Linter",
		description: "VS Code diagnostics bridge",
		defaultPort: 8005,
		folderName: "linter",
		requiresWorkspace: false,
		startupArgs: (port: number) => [
			"run",
			"--frozen",
			"fastmcp",
			"run",
			"main.py",
			"-t",
			"http",
			"-p",
			port.toString(),
			"--",
			"--vscode-ws-port",
			"8999",
		],
	},
]

function getDefaultStartupArgs(port: number): string[] {
	return ["run", "--frozen", "fastmcp", "run", "main.py", "-t", "http", "-p", port.toString()]
}

interface RunningServer {
	key: string
	displayName: string
	port: number
	process: ChildProcess
	outputChannel: vscode.OutputChannel
}

const BUILTIN_SOURCE: McpSource = "builtin"
const SERVER_STARTUP_DELAY_MS = 3000

export class AidMcpService implements vscode.Disposable {
	private static instance: AidMcpService | undefined
	private runningServers: RunningServer[] = []
	private outputChannels = new Map<string, vscode.OutputChannel>()
	private disposed = false

	private constructor(
		private readonly context: vscode.ExtensionContext,
		private readonly outputChannel: vscode.OutputChannel,
	) {}

	static getInstance(context: vscode.ExtensionContext, outputChannel: vscode.OutputChannel): AidMcpService {
		if (!AidMcpService.instance) {
			AidMcpService.instance = new AidMcpService(context, outputChannel)
		}
		return AidMcpService.instance
	}

	/**
	 * Start all AID MCP servers and register them with McpHub.
	 * Non-blocking — spawns servers in the background.
	 */
	async startServers(provider: ClineProvider): Promise<void> {
		if (this.disposed) {
			return
		}

		const uvAvailable = await this.checkUvAvailable()
		if (!uvAvailable) {
			this.outputChannel.appendLine(
				"[AID MCP] 'uv' is not installed. AID MCP servers require 'uv' (Python package manager). " +
					"Install it from https://docs.astral.sh/uv/getting-started/installation/",
			)
			return
		}

		const mcpServersPath = this.getMcpServersPath()
		if (!mcpServersPath) {
			this.outputChannel.appendLine("[AID MCP] Could not locate bundled MCP servers directory")
			return
		}

		const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? null
		this.outputChannel.appendLine(`[AID MCP] Starting servers from ${mcpServersPath}`)

		for (const def of AID_MCP_SERVERS) {
			if (def.requiresWorkspace && !workspaceRoot) {
				this.outputChannel.appendLine(`[AID MCP] Skipping ${def.displayName}: no workspace folder open`)
				continue
			}

			try {
				await this.spawnServer(def, mcpServersPath, workspaceRoot)
			} catch (error) {
				this.outputChannel.appendLine(
					`[AID MCP] Failed to start ${def.displayName}: ${error instanceof Error ? error.message : String(error)}`,
				)
			}
		}

		// Give servers time to start, then register with McpHub
		setTimeout(() => {
			void this.registerWithMcpHub(provider)
		}, SERVER_STARTUP_DELAY_MS)
	}

	/**
	 * Stop all AID MCP servers and unregister from McpHub.
	 */
	async stopServers(provider?: ClineProvider): Promise<void> {
		this.outputChannel.appendLine(`[AID MCP] Stopping ${this.runningServers.length} servers...`)

		// Unregister from McpHub first
		if (provider) {
			try {
				const hub = provider.getMcpHub()
				if (hub) {
					await hub.updateServerConnections({}, BUILTIN_SOURCE, false)
				}
			} catch (error) {
				this.outputChannel.appendLine(
					`[AID MCP] Error unregistering from McpHub: ${error instanceof Error ? error.message : String(error)}`,
				)
			}
		}

		const stopPromises = this.runningServers.map(async (server) => {
			try {
				if (server.process.exitCode === null) {
					server.process.kill("SIGTERM")

					const exited = await this.waitForExit(server.process, 1500)
					if (!exited && server.process.exitCode === null) {
						server.process.kill("SIGKILL")
					}
				}
				this.outputChannel.appendLine(`[AID MCP] Stopped ${server.displayName}`)
			} catch (error) {
				this.outputChannel.appendLine(
					`[AID MCP] Error stopping ${server.displayName}: ${error instanceof Error ? error.message : String(error)}`,
				)
			}
		})

		await Promise.allSettled(stopPromises)
		this.runningServers = []
	}

	/**
	 * Get status of all AID MCP servers.
	 */
	getStatus(): string {
		if (this.runningServers.length === 0) {
			return "No AID MCP servers running"
		}

		const lines = [`AID MCP Server Status (${this.runningServers.length} running):`]
		for (const server of this.runningServers) {
			const alive = server.process.exitCode === null
			lines.push(`  ${server.displayName} (port ${server.port}): ${alive ? "Running" : "Stopped"}`)
		}
		return lines.join("\n")
	}

	dispose(): void {
		this.disposed = true
		void this.stopServers()

		for (const channel of this.outputChannels.values()) {
			channel.dispose()
		}
		this.outputChannels.clear()

		AidMcpService.instance = undefined
	}

	// --- Private ---

	private async checkUvAvailable(): Promise<boolean> {
		return new Promise((resolve) => {
			const proc = spawn("uv", ["--version"], { stdio: "pipe" })
			proc.on("error", () => resolve(false))
			proc.on("close", (code: number | null) => resolve(code === 0))
		})
	}

	private getMcpServersPath(): string | null {
		// In dev mode, use the mcp-servers/ source directly
		const devPath = path.join(this.context.extensionPath, "..", "mcp-servers")
		if (fs.existsSync(devPath)) {
			return devPath
		}

		// In production, use bundled servers in dist/
		const prodPath = path.join(this.context.extensionPath, "dist", "aid-mcp-servers")
		if (fs.existsSync(prodPath)) {
			return prodPath
		}

		return null
	}

	private async spawnServer(
		def: AidServerDefinition,
		mcpServersPath: string,
		workspaceRoot: string | null,
	): Promise<void> {
		const port = def.defaultPort
		const args = def.startupArgs ? def.startupArgs(port) : getDefaultStartupArgs(port)
		const workingDir = path.join(mcpServersPath, def.folderName)

		const outputChannel = this.getOrCreateOutputChannel(def.key, def.displayName)

		const timestamp = new Date().toLocaleTimeString()
		outputChannel.appendLine(`\n=== [${timestamp}] Starting ${def.displayName} ===`)
		outputChannel.appendLine(`Command: uv ${args.join(" ")}`)
		outputChannel.appendLine(`Working directory: ${workingDir}`)

		const env: Record<string, string | undefined> = { ...process.env }
		if (workspaceRoot) {
			env.AID_WORKSPACE_ROOT = workspaceRoot
		}
		env.FASTMCP_STATELESS_HTTP = "true"

		const child = spawn("uv", args, {
			cwd: workingDir,
			stdio: ["pipe", "pipe", "pipe"],
			detached: false,
			env,
		})

		const server: RunningServer = {
			key: def.key,
			displayName: def.displayName,
			port,
			process: child,
			outputChannel,
		}

		this.runningServers.push(server)

		child.stdout?.on("data", (data: Buffer) => {
			outputChannel.appendLine(`[stdout] ${data.toString().trim()}`)
		})

		child.stderr?.on("data", (data: Buffer) => {
			outputChannel.appendLine(`[stderr] ${data.toString().trim()}`)
		})

		child.on("exit", (code: number | null, signal: string | null) => {
			const ts = new Date().toLocaleTimeString()
			outputChannel.appendLine(`[${ts}] Process exited (code=${code}, signal=${signal})`)
			const idx = this.runningServers.findIndex((s) => s.key === def.key)
			if (idx > -1) {
				this.runningServers.splice(idx, 1)
			}
		})

		child.on("error", (error: Error) => {
			outputChannel.appendLine(`[error] ${error.message}`)
		})

		this.outputChannel.appendLine(`[AID MCP] Started ${def.displayName} on port ${port}`)
	}

	private async registerWithMcpHub(provider: ClineProvider): Promise<void> {
		if (this.disposed || this.runningServers.length === 0) {
			return
		}

		try {
			const hub = provider.getMcpHub()
			if (!hub) {
				// McpHub may not be initialized yet — try via McpServerManager
				const hubFromManager = await McpServerManager.getInstance(this.context, provider)
				await this.doRegister(hubFromManager)
			} else {
				await this.doRegister(hub)
			}
		} catch (error) {
			this.outputChannel.appendLine(
				`[AID MCP] Failed to register with McpHub: ${error instanceof Error ? error.message : String(error)}`,
			)
		}
	}

	private async doRegister(hub: McpHub): Promise<void> {
		const servers: Record<string, any> = {}

		for (const running of this.runningServers) {
			if (running.process.exitCode !== null) {
				continue // skip dead processes
			}

			const def = AID_MCP_SERVERS.find((d) => d.key === running.key)
			servers[running.key] = {
				type: "streamable-http" as const,
				url: `http://localhost:${running.port}/mcp`,
				disabled: false,
				...(def?.toolTimeout !== undefined && { timeout: def.toolTimeout }),
			}
		}

		if (Object.keys(servers).length === 0) {
			this.outputChannel.appendLine("[AID MCP] No live servers to register")
			return
		}

		this.outputChannel.appendLine(`[AID MCP] Registering ${Object.keys(servers).length} servers with McpHub...`)
		await hub.updateServerConnections(servers, BUILTIN_SOURCE, false)
		this.outputChannel.appendLine("[AID MCP] Registration complete")
	}

	private getOrCreateOutputChannel(key: string, displayName: string): vscode.OutputChannel {
		const existing = this.outputChannels.get(key)
		if (existing) {
			return existing
		}

		const channel = vscode.window.createOutputChannel(`AID: ${displayName} MCP`)
		this.outputChannels.set(key, channel)
		return channel
	}

	private waitForExit(child: ChildProcess, timeoutMs: number): Promise<boolean> {
		return new Promise((resolve) => {
			if (child.exitCode !== null) {
				resolve(true)
				return
			}
			const timeout = setTimeout(() => resolve(false), timeoutMs)
			child.once("exit", () => {
				clearTimeout(timeout)
				resolve(true)
			})
		})
	}
}
