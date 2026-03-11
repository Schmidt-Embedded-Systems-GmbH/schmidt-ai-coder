import { render, screen, fireEvent, waitFor } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import { useTaskHistory } from "@/schmidtaicoder/hooks/useTaskHistory"
import { useExtensionState } from "@/context/ExtensionStateContext"
import { vscode } from "@/utils/vscode"

vi.mock("@/schmidtaicoder/hooks/useTaskHistory")
vi.mock("@/context/ExtensionStateContext")
vi.mock("@/utils/vscode", () => ({
	vscode: {
		postMessage: vi.fn(),
	},
}))
vi.mock("@/i18n/TranslationContext", () => ({
	useAppTranslation: () => ({
		t: (key: string, options?: any) => {
			if (key === "kilocode:ideaSuggestionsBox.newHere") return "New here?"
			if (key === "kilocode:ideaSuggestionsBox.tryOneOfThese") return "Try one of these ideas to get started:"
			if (key === "kilocode:ideaSuggestionsBox.ideas" && options?.returnObjects) {
				return {
					idea1: "Create a portfolio website",
					idea2: "Build a todo app",
					idea3: "Make a calculator",
				}
			}
			return key
		},
	}),
}))

import { IdeaSuggestionsBox } from "../IdeaSuggestionsBox"

describe("IdeaSuggestionsBox", () => {
	beforeEach(() => {
		vi.clearAllMocks()
		vi.mocked(useExtensionState).mockReturnValue({
			taskHistoryVersion: 1,
		} as any)
	})

	it("should render when workspace has no tasks", () => {
		vi.mocked(useTaskHistory).mockReturnValue({
			data: { historyItems: [] },
		} as any)

		render(<IdeaSuggestionsBox />)

		expect(screen.getByText("New here?")).toBeInTheDocument()
		expect(screen.getByText("Try one of these ideas to get started:")).toBeInTheDocument()
	})

	it("should not render when workspace has tasks", () => {
		vi.mocked(useTaskHistory).mockReturnValue({
			data: { historyItems: [{ id: "1" }] },
		} as any)

		const { container } = render(<IdeaSuggestionsBox />)

		expect(container.firstChild).toBeNull()
	})

	it("should display suggestion buttons", () => {
		vi.mocked(useTaskHistory).mockReturnValue({
			data: { historyItems: [] },
		} as any)

		render(<IdeaSuggestionsBox />)

		const buttons = screen.getAllByRole("button")
		expect(buttons.length).toBeGreaterThan(0)
	})

	it("should execute task immediately when suggestion is clicked", async () => {
		vi.mocked(useTaskHistory).mockReturnValue({
			data: { historyItems: [] },
		} as any)

		render(<IdeaSuggestionsBox />)

		const buttons = screen.getAllByRole("button")
		fireEvent.click(buttons[0])

		await waitFor(() => {
			expect(vscode.postMessage).toHaveBeenCalledWith(
				expect.objectContaining({
					type: "newTask",
					text: expect.any(String),
					images: [],
				}),
			)
		})
	})

	it("should display exactly 2 suggestion buttons", () => {
		vi.mocked(useTaskHistory).mockReturnValue({
			data: { historyItems: [] },
		} as any)

		render(<IdeaSuggestionsBox />)

		const buttons = screen.getAllByRole("button")
		expect(buttons).toHaveLength(2)
	})

	it("should not render a lightbulb icon in suggestion cards", () => {
		vi.mocked(useTaskHistory).mockReturnValue({
			data: { historyItems: [] },
		} as any)

		const { container } = render(<IdeaSuggestionsBox />)

		expect(container.querySelector("svg.lucide-lightbulb")).not.toBeInTheDocument()
	})
})
