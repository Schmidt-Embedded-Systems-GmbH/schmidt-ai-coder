// kilocode_change - new file
import { describe, it, expect, vi, beforeEach } from "vitest"
import { AidMcpService } from "../AidMcpService"

vi.mock("vscode", () => ({
	window: {
		createOutputChannel: vi.fn().mockReturnValue({
			appendLine: vi.fn(),
			show: vi.fn(),
			dispose: vi.fn(),
		}),
	},
	workspace: {
		workspaceFolders: [],
		createFileSystemWatcher: vi.fn().mockReturnValue({
			onDidChange: vi.fn(),
			onDidCreate: vi.fn(),
			onDidDelete: vi.fn(),
			dispose: vi.fn(),
		}),
		onDidChangeWorkspaceFolders: vi.fn(),
	},
}))

const createMockContext = () =>
	({
		extensionPath: "/tmp/fake-extension",
	}) as any

describe("AidMcpService", () => {
	beforeEach(() => {
		;(AidMcpService as any).instance = undefined
	})

	it("registers MCU Specs server with extended tool timeout", async () => {
		const outputChannel = {
			appendLine: vi.fn(),
			show: vi.fn(),
			dispose: vi.fn(),
		}
		const service = AidMcpService.getInstance(createMockContext(), outputChannel as any)

		const mcpHub = {
			updateServerConnections: vi.fn().mockResolvedValue(undefined),
		}

		const mockProcess = { exitCode: null }

		;(service as any).runningServers = [
			{
				key: "aid-mcu-specs",
				displayName: "MCU Specs",
				port: 8009,
				process: mockProcess,
				outputChannel,
			},
		]

		await (service as any).doRegister(mcpHub)

		expect(mcpHub.updateServerConnections).toHaveBeenCalledWith(
			expect.objectContaining({
				"aid-mcu-specs": expect.objectContaining({
					type: "streamable-http",
					url: "http://localhost:8009/mcp",
					timeout: 1800,
				}),
			}),
			"builtin",
			false,
		)
	})
})
