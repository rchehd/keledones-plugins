# UI design review and evidence

Use this checklist for UI changes that have an agreed design reference. Record the Figma frame and node
or approved export, version when available, component variant, state and corresponding app route.
When a required design reference is unavailable, record the missing evidence and clarify the target.

1. Read the relevant frame in Figma Dev Mode, use available read-only Figma MCP tools, or use an approved
   export. In MCP, select the exact node and use `get_design_context`, `get_screenshot` and, when relevant,
   `get_variable_defs` for its styles and variables.
2. Compare affected components, spacing, typography, and states against the approved reference. Use the
   project's design system and review applicable responsive behavior, keyboard access, focus and labels.
3. In QA, run the matching app revision at the approved viewport, state, theme and locale. Capture
   the actual Playwright screenshot for browser flows or the device screenshot for native design cases.
   Record the observed difference and its impact against the relevant requirement.
4. Use approved screenshots from the same test environment for automated Playwright regressions. Figma
   frames establish design intent. A browser regression uses the approved browser rendering as its baseline.

[Figma Dev Mode](https://help.figma.com/hc/en-us/articles/15023152204951-Navigate-designs-in-Dev-Mode) ·
[Figma MCP tools](https://developers.figma.com/docs/figma-mcp-server/tools-and-prompts/) ·
[Playwright visual comparisons](https://playwright.dev/docs/test-snapshots)
