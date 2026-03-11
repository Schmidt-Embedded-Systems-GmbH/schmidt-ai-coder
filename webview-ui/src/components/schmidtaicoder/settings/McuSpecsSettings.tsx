// kilocode_change - new file
import { VSCodeTextField } from "@vscode/webview-ui-toolkit/react"
import { Database, KeyRound, HardDrive, FolderRoot, Cpu, Link2 } from "lucide-react"
import { SectionHeader } from "@/components/settings/SectionHeader"
import { Section } from "@/components/settings/Section"
import { SearchableSetting } from "@/components/settings/SearchableSetting"
import { useAppTranslation } from "@/i18n/TranslationContext"
import type { SetCachedStateField } from "@/components/settings/types"

type Props = {
	mcuSpecsQdrantUrl?: string
	mcuSpecsEmbeddingEndpoint?: string
	mcuSpecsEmbeddingModel?: string
	mcuSpecsStoragePath?: string
	mcuSpecsWorkspaceRoot?: string
	mcuSpecsEmbeddingApiKey?: string
	openRouterApiKey?: string
	setCachedStateField: SetCachedStateField<any>
}

export const McuSpecsSettings = ({
	mcuSpecsQdrantUrl,
	mcuSpecsEmbeddingEndpoint,
	mcuSpecsEmbeddingModel,
	mcuSpecsStoragePath,
	mcuSpecsWorkspaceRoot,
	mcuSpecsEmbeddingApiKey,
	openRouterApiKey,
	setCachedStateField,
}: Props) => {
	const { t } = useAppTranslation()
	const usingFallbackKey = !mcuSpecsEmbeddingApiKey && !!openRouterApiKey

	return (
		<div>
			<SectionHeader description={t("settings:mcuSpecs.description")}>
				{t("settings:sections.mcuSpecs")}
			</SectionHeader>
			<Section>
				<SearchableSetting
					settingId="mcuSpecs-qdrant-url"
					section="mcuSpecs"
					label={t("settings:mcuSpecs.qdrantUrl.label")}>
					<label className="block font-medium mb-1">{t("settings:mcuSpecs.qdrantUrl.label")}</label>
					<VSCodeTextField
						value={mcuSpecsQdrantUrl || ""}
						onInput={(e: any) => setCachedStateField("mcuSpecsQdrantUrl", e.target.value)}
						placeholder={t("settings:mcuSpecs.qdrantUrl.placeholder")}
						className="w-full">
						<div className="flex items-center gap-2 mb-1">
							<Database className="w-4 h-4" />
							{t("settings:mcuSpecs.qdrantUrl.label")}
						</div>
					</VSCodeTextField>
					<div className="text-vscode-descriptionForeground text-sm mt-1">
						{t("settings:mcuSpecs.qdrantUrl.description")}
					</div>
				</SearchableSetting>

				<SearchableSetting
					settingId="mcuSpecs-embedding-api-key"
					section="mcuSpecs"
					label={t("settings:mcuSpecs.embeddingApiKey.label")}>
					<label className="block font-medium mb-1">{t("settings:mcuSpecs.embeddingApiKey.label")}</label>
					<VSCodeTextField
						value={mcuSpecsEmbeddingApiKey || ""}
						onInput={(e: any) => setCachedStateField("mcuSpecsEmbeddingApiKey", e.target.value)}
						placeholder={t("settings:mcuSpecs.embeddingApiKey.placeholder")}
						className="w-full">
						<div className="flex items-center gap-2 mb-1">
							<KeyRound className="w-4 h-4" />
							{t("settings:mcuSpecs.embeddingApiKey.label")}
						</div>
					</VSCodeTextField>
					<div className="text-vscode-descriptionForeground text-sm mt-1">
						{t("settings:mcuSpecs.embeddingApiKey.description")}
					</div>
					{usingFallbackKey && (
						<div className="mt-2 rounded border border-vscode-panel-border bg-vscode-editorInfo-background px-3 py-2 text-sm text-vscode-foreground">
							{t("settings:mcuSpecs.embeddingApiKey.fallbackNotice")}
						</div>
					)}
				</SearchableSetting>

				<SearchableSetting
					settingId="mcuSpecs-embedding-endpoint"
					section="mcuSpecs"
					label={t("settings:mcuSpecs.embeddingEndpoint.label")}>
					<label className="block font-medium mb-1">{t("settings:mcuSpecs.embeddingEndpoint.label")}</label>
					<VSCodeTextField
						value={mcuSpecsEmbeddingEndpoint || ""}
						onInput={(e: any) => setCachedStateField("mcuSpecsEmbeddingEndpoint", e.target.value)}
						placeholder={t("settings:mcuSpecs.embeddingEndpoint.placeholder")}
						className="w-full">
						<div className="flex items-center gap-2 mb-1">
							<Link2 className="w-4 h-4" />
							{t("settings:mcuSpecs.embeddingEndpoint.label")}
						</div>
					</VSCodeTextField>
					<div className="text-vscode-descriptionForeground text-sm mt-1">
						{t("settings:mcuSpecs.embeddingEndpoint.description")}
					</div>
				</SearchableSetting>

				<SearchableSetting
					settingId="mcuSpecs-embedding-model"
					section="mcuSpecs"
					label={t("settings:mcuSpecs.embeddingModel.label")}>
					<label className="block font-medium mb-1">{t("settings:mcuSpecs.embeddingModel.label")}</label>
					<VSCodeTextField
						value={mcuSpecsEmbeddingModel || ""}
						onInput={(e: any) => setCachedStateField("mcuSpecsEmbeddingModel", e.target.value)}
						placeholder={t("settings:mcuSpecs.embeddingModel.placeholder")}
						className="w-full">
						<div className="flex items-center gap-2 mb-1">
							<Cpu className="w-4 h-4" />
							{t("settings:mcuSpecs.embeddingModel.label")}
						</div>
					</VSCodeTextField>
					<div className="text-vscode-descriptionForeground text-sm mt-1">
						{t("settings:mcuSpecs.embeddingModel.description")}
					</div>
				</SearchableSetting>

				<SearchableSetting
					settingId="mcuSpecs-storage-path"
					section="mcuSpecs"
					label={t("settings:mcuSpecs.storagePath.label")}>
					<label className="block font-medium mb-1">{t("settings:mcuSpecs.storagePath.label")}</label>
					<VSCodeTextField
						value={mcuSpecsStoragePath || ""}
						onInput={(e: any) => setCachedStateField("mcuSpecsStoragePath", e.target.value)}
						placeholder={t("settings:mcuSpecs.storagePath.placeholder")}
						className="w-full">
						<div className="flex items-center gap-2 mb-1">
							<HardDrive className="w-4 h-4" />
							{t("settings:mcuSpecs.storagePath.label")}
						</div>
					</VSCodeTextField>
					<div className="text-vscode-descriptionForeground text-sm mt-1">
						{t("settings:mcuSpecs.storagePath.description")}
					</div>
				</SearchableSetting>

				<SearchableSetting
					settingId="mcuSpecs-workspace-root"
					section="mcuSpecs"
					label={t("settings:mcuSpecs.workspaceRoot.label")}>
					<label className="block font-medium mb-1">{t("settings:mcuSpecs.workspaceRoot.label")}</label>
					<VSCodeTextField
						value={mcuSpecsWorkspaceRoot || ""}
						onInput={(e: any) => setCachedStateField("mcuSpecsWorkspaceRoot", e.target.value)}
						placeholder={t("settings:mcuSpecs.workspaceRoot.placeholder")}
						className="w-full">
						<div className="flex items-center gap-2 mb-1">
							<FolderRoot className="w-4 h-4" />
							{t("settings:mcuSpecs.workspaceRoot.label")}
						</div>
					</VSCodeTextField>
					<div className="text-vscode-descriptionForeground text-sm mt-1">
						{t("settings:mcuSpecs.workspaceRoot.description")}
					</div>
				</SearchableSetting>
			</Section>
		</div>
	)
}
