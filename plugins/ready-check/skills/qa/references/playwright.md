# Playwright modes

Use these recipes only after the Ready Check gates and local environment are resolved. Commands below
are examples; replace paths, URL, session name, and element references with observed values. Follow the
current harness's command permissions and any required shell wrapper. No separately installed skill is needed.

## Choose the mode

`visible` uses the bundled `ready-playwright` MCP server (headed); `background` uses the CLI (headless). Read the
choice from the conversation or `scripts/ready-check.py config get browser --project <app>`; with `ask`, offer
both when approving the QA plan. Where MCP is unavailable, visible mode runs the CLI headed (`headless: false`).
Headed mode needs a graphical session on the machine running the browser; a remote server's window is not
visible on the user's computer. Confirm a real launch before claiming visibility.

The plugin ships the MCP server; the client starts it when the plugin is enabled. Its command runs
`node <plugin>/scripts/mcp.mjs`, which starts `scripts/ready-check.py mcp` with the managed browser, an isolated
context and artifacts under `ai/ready-check/tmp/playwright-mcp/`. If the tools are not installed yet, the server
exits with a message naming the install command. QA never edits client configuration.

## Locators and waiting

Prefer what a user perceives: role with accessible name, then label, then visible text, then a test id. Use CSS or
XPath only when nothing else identifies the element, and record why. In MCP use the element references from the
latest snapshot; take a new snapshot after navigation or re-rendering instead of reusing old references. Wait for
an expected element, text or state with a bounded timeout; avoid fixed sleeps and network-idle waits.

## Accessibility (axe)

The browser bundle includes a pinned `axe-core`; no network access is needed.

- **MCP:** the bundled server preloads axe into every page. Run it with the evaluate tool on the changed page:
  `async () => (await axe.run(document.querySelector('<changed component>') || document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] } })).violations.map(v => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.slice(0, 10).map(n => n.target) }))`
- **CLI:** write the script once per run and execute it in the same session:
  `python3 <plugin>/scripts/ready-check.py a11y --output <reports directory>/evidence/axe.js [--include "<css>"]`, then
  `playwright-cli -s=<session> --raw run-code --filename=<reports directory>/evidence/axe.js` (`--raw` prints only the result, not the embedded axe source).

Save the JSON output as evidence. Record impact, rule, affected targets and whether the element is part of the
change. Automated rules cover only part of WCAG; keyboard, focus and reading order still need a manual check.

## CLI

Resolve `playwright-cli` from the current environment, or an explicitly identified existing local executable.
If absent, try the packaged Python entry point `scripts/ready-check.py playwright --version` wrapper from the installed plugin; it selects
the separately prepared managed bundle using `READY_CHECK_DATA_DIR` or the default data root. When usable,
replace `playwright-cli` in the recipes below with `python3 /absolute/plugin/scripts/ready-check.py playwright` (Windows: `py -3` instead of `python3`). The wrapper
keeps the QA report working directory and does not install dependencies.
Record its path and `--version`; inspect `--help` and command-specific help for the installed version.
Do not use `npx` as a discovery step that might download a package. A project Playwright test runner alone
does not prove that this CLI interface is installed. If the executable or browser is absent, record the
actual error and ask about switching mode unless that fallback was already authorized. Installation is separate from QA; see
[setup instructions](../../../dependencies/SETUP.md). QA does not install anything; `check` handles it.

Run commands with the reports directory (`<repo>/ai/ready-check/reports/<branch-slug>/`) as their working directory so default `.playwright-cli`
artifacts do not enter the application or plugin. Create a unique session name per run and role; reuse it
on every command for that role. Use temporary browser profiles rather than attaching to a personal browser.

Create a run-local JSON config such as the following, with a real absolute evidence path and a browser
already installed for this CLI. Select the browser according to project requirements and availability;
Firefox, a persistent profile, and ignoring TLS errors are not universal defaults. Set `headless: false`
when the agreed CLI run should be visible; the example below uses background mode.

```json
{
  "browser": {
    "browserName": "chromium",
    "isolated": true,
    "launchOptions": {"headless": true},
    "contextOptions": {"viewport": {"width": 1280, "height": 800}}
  },
  "outputDir": "/absolute/reports-directory/evidence",
  "outputMode": "file"
}
```

For a known local self-signed certificate, use the project's existing trust setup or resolve the TLS
question with the user; if a run-local `ignoreHTTPSErrors` setting is agreed, record it. Keep config and
output in the reports directory; do not change project or global browser configuration.

```sh
playwright-cli --version
playwright-cli --help
playwright-cli -s=tc-run-member open 'http://localhost:8080' --config=/absolute/reports-directory/pw.json
playwright-cli -s=tc-run-member snapshot
playwright-cli -s=tc-run-member fill e12 'Ready Check sample'
playwright-cli -s=tc-run-member click e15
playwright-cli -s=tc-run-member snapshot
playwright-cli -s=tc-run-member console error
playwright-cli -s=tc-run-member requests
playwright-cli -s=tc-run-member screenshot --filename=/absolute/reports-directory/browser/QA-001.png
playwright-cli -s=tc-run-member resize 375 812
playwright-cli -s=tc-run-member close
```

Read the saved snapshot before choosing refs; `e12` and `e15` above are illustrative. Refresh refs after
navigation or DOM changes. Read output/log files returned by the CLI and link relevant evidence to the
scenario. Use request details only when needed; headers and bodies may contain authentication material.
When runtime waits or assertions need Playwright code, inspect `run-code --help` and save a small probe
beside the report. Verify the current page and exact expected state; a successful snippet is not enough.

Do not run `install`, `install-browser`, package managers, global `close-all`, or `kill-all` during QA.
Close the named sessions created by this run; preserve unrelated sessions. If a named session fails to
close, record it for cleanup rather than stopping other browsers.

CLI reference: [Microsoft Playwright CLI](https://github.com/microsoft/playwright-cli).

## Official Playwright MCP

When MCP is selected (or an authorized fallback), discover the official Microsoft Playwright MCP tools
connected to the current harness, normally the bundled `ready-playwright`. Record the
connection identity, browser mode and any fallback reason. If the connection's origin or configuration is
unclear, resolve it before use. Do not substitute an unrelated browser integration, start another harness,
install a server, or edit MCP settings during `/check`.

Read the available tool schemas; names, fields, and enabled capabilities vary by server version. Typical
capabilities map as follows; use the actual schema rather than assuming these identifiers are available:

| Purpose | Typical tool |
| --- | --- |
| Navigate and inspect | `browser_navigate`, `browser_snapshot` |
| Act through the UI | `browser_click`, `browser_fill_form`, `browser_press_key`, `browser_select_option` |
| Console and requests | `browser_console_messages`, `browser_network_requests` |
| Capture UI and viewport | `browser_take_screenshot`, `browser_resize` |
| End the run-owned browser | `browser_close` |

Confirm an isolated test context is available before login. Tabs normally share authentication; if separate
role contexts are unavailable, explicitly log out/in and verify actor identity between cases. A shared
personal session is not a substitute for the required test role. Record the browser identity and relevant
configuration from the connection or browser observations; do not claim an unknown version was verified.

MCP may save automatic artifacts to its configured output directory (for Ready Check's server,
`ai/ready-check/tmp/playwright-mcp/`), while explicit relative filenames can resolve against its workspace root.
Copy artifacts the report cites from there into `<reports directory>/evidence/`. Verify output routing before requesting file-producing actions. Use
absolute paths under `<reports directory>/evidence/` when supported, or inline tool output saved beside the report. If the
server cannot keep required artifacts under `ai/ready-check/`, resolve setup or mark the affected
evidence `INCOMPLETE`; do not silently contaminate the checked diff. Do not change the server configuration.

Check real navigation, UI, console, network, and persistence just as for CLI. Missing observability needed
for a requirement remains a coverage gap. Changing transport is not permission to lower the QA criteria.
If neither transport can execute required browser cases, save `INCOMPLETE` and the concrete setup need.

MCP reference: [Microsoft Playwright MCP](https://github.com/microsoft/playwright-mcp).
