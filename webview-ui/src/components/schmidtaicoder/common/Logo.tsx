// kilocode_change
export default function Logo({ width = 100, height = 100 }: { width?: number; height?: number }) {
	return (
		<div
			className="mb-4 mt-4 inline-flex items-center justify-center"
			style={{ width, height }}
			aria-label="SES logo"
			role="img">
			<img src="/ses-logo-no-text.svg" alt="SES logo" className="h-full w-full object-contain" />
		</div>
	)
}
