// kilocode_change
export default function Logo({ width = 100, height = 100 }: { width?: number; height?: number }) {
	const iconsBaseUri = (window as any).ICONS_BASE_URI || ""
	return (
		<div
			className="mb-4 mt-4 inline-flex items-center justify-center"
			style={{ width, height }}
			aria-label="SES logo"
			role="img">
			<img src={`${iconsBaseUri}/schmidt-ai-dark.svg`} alt="SES logo" className="h-full w-full object-contain" />
		</div>
	)
}
