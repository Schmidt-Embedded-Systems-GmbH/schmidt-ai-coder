// kilocode_change - new file

import { render, screen } from "@/utils/test-utils"
import Logo from "../Logo"

describe("Logo", () => {
	const baseUri = "vscode-resource://test"

	beforeEach(() => {
		;(window as any).ICONS_BASE_URI = baseUri
	})

	afterEach(() => {
		delete (window as any).ICONS_BASE_URI
	})

	it("uses ICONS_BASE_URI for the logo source", () => {
		render(<Logo />)

		const img = screen.getByAltText("SES logo") as HTMLImageElement
		expect(img).toBeInTheDocument()
		expect(img.src).toBe(`${baseUri}/schmidt-ai-dark.svg`)
	})
})
