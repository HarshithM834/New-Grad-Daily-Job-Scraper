# CareerOps interface contract

## Product and audience
A working operations console for students and early-career job seekers. Every surface must help users discover, triage, track or export real opportunities. The dashboard is not a SaaS marketing landing page.

## Visual direction
Editorial clarity meets developer tooling. Warm neutral surfaces (`#f8f9fb` and white), precise cool dividers (`#dce1e7`), ink (`#151e2b`), and one purposeful sea-green (`#176d68`) for navigation focus and action. No purple gradients, glow effects, glass panels, emoji icons or gratuitous metric tiles.

## Information architecture
Five stable areas: Overview, Job Explorer, Application Pipeline, System Health, Output Destinations. The job table is the primary screen. Source provenance, direct application link status, unresolved listings and last-run telemetry must never be replaced with fake data or hard-coded metrics.

## Components
Use React + Tailwind with owned shadcn-style Button, Card, Badge and Input sources. Use Radix primitives for keyboard-accessible Select, Dialog, Switch. A single border radius vocabulary (5 / 8 / 12 px) is sufficient. Use 11-13px dense metadata typography only where legible. Focus rings must be visible. Tabular numbers use tabular digits.

## UX safeguards
- No fake success banners or fabricated counters.
- Export and Save buttons act on real API operations; failures are reported clearly.
- Disabled states whenever an operation is busy.
- Escape user-supplied text via React rendering; reject non-http(s) outbound links.
- Keep secrets outside source control; never show webhook authentication tokens in the browser.
- Prefer actual empty states to decorative placeholder data.
- Respect reduced-motion preferences; ensure controls work with keyboard.
- Test both desktop and mobile at 375, 768, 1280 widths before claiming polished.

## Reference approach
shadcn/ui and Radix are implementation references; anti-slop, no-slop-ui, avoid-ai-design, and Anti-AI-UI are design/audit influences. No unreviewed code from those repositories is vendored into this project.