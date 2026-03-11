import { useMemo } from "react"
import { telemetryClient } from "@/utils/TelemetryClient"
import { vscode } from "@/utils/vscode"
import { TelemetryEventName } from "@roo-code/types"
import { useAppTranslation } from "@/i18n/TranslationContext"
import { useTaskHistory } from "@/schmidtaicoder/hooks/useTaskHistory"
import { useExtensionState } from "@/context/ExtensionStateContext"
import { Sparkles, ArrowRight } from "lucide-react"

const FALLBACK_IDEAS = [
	"Make a spinning, glowing 3D sphere that responds to mouse movements. Make the app work in the browser.",
	"Create a portfolio website for a Python software developer",
	"Create a financial app mockup in the browser. Then test if it works",
	"Create a directory website containing the best AI video generation models currently",
	"Create a CSS gradient generator that exports custom stylesheets and shows a live preview",
	"Generate cards that reveal dynamic content beautifully when hovered over",
	"Create a calming interactive starfield that moves with mouse gestures",
]

export const IdeaSuggestionsBox = () => {
	const { t } = useAppTranslation()
	const { taskHistoryVersion } = useExtensionState()

	// Check if current workspace has any tasks
	const { data } = useTaskHistory(
		{
			workspace: "current",
			sort: "newest",
			favoritesOnly: false,
			pageIndex: 0,
		},
		taskHistoryVersion,
	)
	const hasWorkspaceTasks = (data?.historyItems?.length ?? 0) > 0

	// Show 2 random ideas - memoized to prevent re-shuffling on re-renders
	// Must be called before early return to satisfy React hooks rules
	const shuffledIdeas = useMemo(() => {
		const translatedIdeas = t("kilocode:ideaSuggestionsBox.ideas", { returnObjects: true }) as
			| Record<string, string>
			| string
			| undefined

		const ideas =
			translatedIdeas && typeof translatedIdeas === "object"
				? Object.values(translatedIdeas).filter(
						(idea): idea is string => typeof idea === "string" && idea.length > 0,
					)
				: FALLBACK_IDEAS

		return [...ideas].sort(() => Math.random() - 0.5).slice(0, 2)
	}, [t])

	// Don't show if workspace has tasks
	if (hasWorkspaceTasks) {
		return null
	}

	const handleIdeaClick = (idea: string) => {
		vscode.postMessage({
			type: "newTask",
			text: idea,
			images: [],
		})

		telemetryClient.capture(TelemetryEventName.SUGGESTION_BUTTON_CLICKED, {
			idea,
		})
	}

	return (
		<div className="flex flex-col items-center">
			<div className="w-full p-5 rounded-md border border-vscode-panel-border bg-vscode-input-background">
				<div className="text-center mb-5">
					<div className="inline-flex items-center gap-2 mb-2">
						<Sparkles className="w-4 h-4 text-vscode-foreground" aria-hidden="true" />
						<p className="text-base font-semibold text-vscode-foreground m-0">
							{t("kilocode:ideaSuggestionsBox.newHere")}
						</p>
						<Sparkles className="w-4 h-4 text-vscode-foreground" aria-hidden="true" />
					</div>
					<p className="text-sm text-vscode-descriptionForeground m-0">
						{t("kilocode:ideaSuggestionsBox.tryOneOfThese")}
					</p>
				</div>

				<div className="flex flex-col gap-2.5">
					{shuffledIdeas.map((idea) => (
						<button
							key={idea}
							onClick={() => handleIdeaClick(idea)}
							className="group w-full px-4 py-3 text-left text-sm rounded border border-vscode-panel-border cursor-pointer transition-all duration-200 hover:border-vscode-focusBorder hover:shadow-sm bg-vscode-editor-background">
							<div className="flex items-start gap-3">
								<div
									className="flex-shrink-0 w-7 h-7 rounded flex items-center justify-center transition-colors duration-200 group-hover:bg-vscode-focusBorder"
									style={{
										background: "color-mix(in srgb, var(--vscode-focusBorder) 15%, transparent)",
									}}>
									<ArrowRight
										className="w-4 h-4 text-vscode-foreground transition-colors duration-200 group-hover:text-vscode-button-foreground"
										aria-hidden="true"
									/>
								</div>
								<span className="flex-1 text-vscode-foreground leading-relaxed pt-0.5">{idea}</span>
								<ArrowRight
									className="w-4 h-4 text-vscode-descriptionForeground opacity-0 group-hover:opacity-100 transition-opacity duration-200 mt-1"
									aria-hidden="true"
								/>
							</div>
						</button>
					))}
				</div>
			</div>
		</div>
	)
}
