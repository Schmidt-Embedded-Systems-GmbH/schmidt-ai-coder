// kilocode_change - new file
//
// WebSocket server that exposes VS Code's diagnostics API to the AID Linter MCP server.
// The linter MCP server (Python) connects here on port 8999 and queries diagnostics
// via a simple JSON request/response protocol over WebSocket.

import * as vscode from "vscode"
import * as path from "path"
import { WebSocketServer, type WebSocket } from "ws"

interface BridgeRequest {
	id: string
	method: string
	params?: Record<string, any>
}

interface BridgeResponse {
	id: string
	result?: any
	error?: string
}

const DEFAULT_PORT = 8999

export class DiagnosticsBridge implements vscode.Disposable {
	private static instance: DiagnosticsBridge | undefined
	private wsServer: WebSocketServer | undefined
	private isRunning = false

	private constructor(
		private readonly port: number,
		private readonly outputChannel: vscode.OutputChannel,
	) {}

	static getInstance(outputChannel: vscode.OutputChannel, port: number = DEFAULT_PORT): DiagnosticsBridge {
		if (!DiagnosticsBridge.instance) {
			DiagnosticsBridge.instance = new DiagnosticsBridge(port, outputChannel)
		}
		return DiagnosticsBridge.instance
	}

	async start(): Promise<boolean> {
		if (this.isRunning) {
			return true
		}

		try {
			this.wsServer = new WebSocketServer({ port: this.port })

			this.wsServer.on("connection", (ws: WebSocket) => {
				this.outputChannel.appendLine("[Diagnostics Bridge] Client connected")

				ws.on("message", async (data: Buffer) => {
					try {
						const request: BridgeRequest = JSON.parse(data.toString())
						const response = await this.handleRequest(request)
						if (ws.readyState === ws.OPEN) {
							ws.send(JSON.stringify(response))
						}
					} catch (error) {
						if (ws.readyState === ws.OPEN) {
							const errorResponse: BridgeResponse = {
								id: "unknown",
								error: `Invalid request: ${error instanceof Error ? error.message : String(error)}`,
							}
							ws.send(JSON.stringify(errorResponse))
						}
					}
				})

				ws.on("close", () => {
					this.outputChannel.appendLine("[Diagnostics Bridge] Client disconnected")
				})

				ws.on("error", (error) => {
					this.outputChannel.appendLine(`[Diagnostics Bridge] Connection error: ${error.message}`)
				})
			})

			this.wsServer.on("error", (error) => {
				this.outputChannel.appendLine(`[Diagnostics Bridge] Server error: ${error.message}`)
				this.isRunning = false
			})

			this.isRunning = true
			this.outputChannel.appendLine(`[Diagnostics Bridge] Started on port ${this.port}`)
			return true
		} catch (error) {
			this.outputChannel.appendLine(
				`[Diagnostics Bridge] Failed to start: ${error instanceof Error ? error.message : String(error)}`,
			)
			this.isRunning = false
			return false
		}
	}

	async stop(): Promise<void> {
		if (!this.isRunning || !this.wsServer) {
			return
		}

		for (const client of this.wsServer.clients) {
			try {
				client.terminate()
			} catch {
				// ignore
			}
		}

		await new Promise<void>((resolve) => {
			this.wsServer!.close(() => resolve())
			setTimeout(resolve, 1000)
		})

		this.isRunning = false
		this.outputChannel.appendLine("[Diagnostics Bridge] Stopped")
	}

	getStatus(): { isRunning: boolean; port: number } {
		return { isRunning: this.isRunning, port: this.port }
	}

	dispose(): void {
		void this.stop()
		DiagnosticsBridge.instance = undefined
	}

	// --- Request handling ---

	private async handleRequest(request: BridgeRequest): Promise<BridgeResponse> {
		try {
			let result: any

			switch (request.method) {
				case "ping":
					result = { status: "pong", timestamp: new Date().toISOString() }
					break
				case "getDiagnostics":
					result = this.getDiagnostics(request.params?.filePath)
					break
				case "getDiagnosticsBySeverity":
					result = this.getDiagnosticsBySeverity(request.params?.severity, request.params?.filePath)
					break
				case "getWorkspaceDiagnosticsSummary":
					result = this.getWorkspaceDiagnosticsSummary()
					break
				case "getActiveFileDiagnostics":
					result = this.getActiveFileDiagnostics()
					break
				case "getDiagnosticsForFiles":
					result = this.getDiagnosticsForFiles(request.params?.filePaths ?? [])
					break
				default:
					throw new Error(`Unknown method: ${request.method}`)
			}

			return { id: request.id, result }
		} catch (error) {
			return {
				id: request.id,
				error: error instanceof Error ? error.message : String(error),
			}
		}
	}

	// --- Diagnostics API wrappers ---

	private getDiagnostics(filePath?: string): any[] {
		const diagnostics: any[] = []

		if (filePath) {
			const resolved = this.resolveFilePath(filePath)
			const uri = vscode.Uri.file(resolved)
			for (const d of vscode.languages.getDiagnostics(uri)) {
				diagnostics.push(this.formatDiagnostic(d, resolved))
			}
		} else {
			for (const [uri, fileDiags] of vscode.languages.getDiagnostics()) {
				for (const d of fileDiags) {
					diagnostics.push(this.formatDiagnostic(d, uri.fsPath))
				}
			}
		}

		return diagnostics
	}

	private getDiagnosticsBySeverity(severity?: string, filePath?: string): any[] {
		const severityMap: Record<string, vscode.DiagnosticSeverity> = {
			error: vscode.DiagnosticSeverity.Error,
			warning: vscode.DiagnosticSeverity.Warning,
			info: vscode.DiagnosticSeverity.Information,
			hint: vscode.DiagnosticSeverity.Hint,
		}

		const target = severityMap[(severity ?? "error").toLowerCase()]
		if (target === undefined) {
			throw new Error(`Invalid severity: ${severity}. Valid: error, warning, info, hint`)
		}

		const all = this.getDiagnostics(filePath)
		return all.filter((d) => d.severity === this.severityString(target))
	}

	private getWorkspaceDiagnosticsSummary(): any {
		const summary = {
			totalFiles: 0,
			totalDiagnostics: 0,
			errors: 0,
			warnings: 0,
			info: 0,
			hints: 0,
			files: [] as any[],
		}

		for (const [uri, fileDiags] of vscode.languages.getDiagnostics()) {
			if (fileDiags.length === 0) {
				continue
			}

			summary.totalFiles++
			summary.totalDiagnostics += fileDiags.length

			const fileStats = {
				file: uri.fsPath,
				diagnosticsCount: fileDiags.length,
				errors: 0,
				warnings: 0,
				info: 0,
				hints: 0,
			}

			for (const d of fileDiags) {
				switch (d.severity) {
					case vscode.DiagnosticSeverity.Error:
						summary.errors++
						fileStats.errors++
						break
					case vscode.DiagnosticSeverity.Warning:
						summary.warnings++
						fileStats.warnings++
						break
					case vscode.DiagnosticSeverity.Information:
						summary.info++
						fileStats.info++
						break
					case vscode.DiagnosticSeverity.Hint:
						summary.hints++
						fileStats.hints++
						break
				}
			}

			summary.files.push(fileStats)
		}

		return summary
	}

	private getActiveFileDiagnostics(): any {
		const editor = vscode.window.activeTextEditor
		if (!editor) {
			return { file: null, diagnostics: [] }
		}

		const uri = editor.document.uri
		const diagnostics = vscode.languages.getDiagnostics(uri).map((d) => this.formatDiagnostic(d, uri.fsPath, false))

		return { file: uri.fsPath, diagnostics }
	}

	private getDiagnosticsForFiles(filePaths: string[]): Record<string, any[]> {
		const result: Record<string, any[]> = {}

		for (const fp of filePaths) {
			try {
				const resolved = this.resolveFilePath(fp)
				const uri = vscode.Uri.file(resolved)
				result[fp] = vscode.languages.getDiagnostics(uri).map((d) => this.formatDiagnostic(d, resolved, false))
			} catch {
				result[fp] = []
			}
		}

		return result
	}

	// --- Helpers ---

	private resolveFilePath(filePath: string): string {
		if (filePath.startsWith("/") || /^[A-Za-z]:/.test(filePath)) {
			return filePath
		}

		const folders = vscode.workspace.workspaceFolders
		if (folders && folders.length > 0) {
			return path.join(folders[0].uri.fsPath, filePath)
		}

		return filePath
	}

	private formatDiagnostic(d: vscode.Diagnostic, filePath: string, includeFile = true): any {
		const formatted: any = {
			line: d.range.start.line,
			column: d.range.start.character,
			endLine: d.range.end.line,
			endColumn: d.range.end.character,
			severity: this.severityString(d.severity),
			message: d.message,
			source: d.source ?? "",
			code: d.code ? String(d.code) : "",
		}

		if (includeFile) {
			formatted.file = filePath
		}

		if (d.relatedInformation && d.relatedInformation.length > 0) {
			formatted.relatedInformation = d.relatedInformation.map((info) => ({
				location: {
					file: info.location.uri.fsPath,
					line: info.location.range.start.line,
					column: info.location.range.start.character,
				},
				message: info.message,
			}))
		}

		if (d.tags && d.tags.length > 0) {
			formatted.tags = d.tags.map((tag) => this.tagString(tag))
		}

		return formatted
	}

	private severityString(severity: vscode.DiagnosticSeverity): string {
		switch (severity) {
			case vscode.DiagnosticSeverity.Error:
				return "error"
			case vscode.DiagnosticSeverity.Warning:
				return "warning"
			case vscode.DiagnosticSeverity.Information:
				return "info"
			case vscode.DiagnosticSeverity.Hint:
				return "hint"
			default:
				return "unknown"
		}
	}

	private tagString(tag: vscode.DiagnosticTag): string {
		switch (tag) {
			case vscode.DiagnosticTag.Unnecessary:
				return "unnecessary"
			case vscode.DiagnosticTag.Deprecated:
				return "deprecated"
			default:
				return "unknown"
		}
	}
}
