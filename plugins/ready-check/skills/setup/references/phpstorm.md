# Connect PhpStorm MCP

After successful installation of all Ready Check tools, ask **Connect PhpStorm MCP?** with **Yes** and **No** in
the user's language. A tool that still needs installation or a failed setup does not trigger this offer.
Use the same connection flow if a user later says “Connect PhpStorm MCP” or asks to enable it in settings.
An explicit request can start the flow directly.

On No, finish setup. The project preference defaults to off. On Yes, run
`ready-check.py setup --project <repo> --component phpstorm`. This records project opt-in separately from
tool installation. Detect whether this client already exposes PhpStorm's `lint_files` or `get_file_problems`.

For a widget request, follow the [saved settings decision](../../qa/references/interactive-ui.md#settings)
and use `--phpstorm-request <request_id>`. A widget notification is a request to check that decision.

If the tools are unavailable, give the [JetBrains MCP setup steps](https://www.jetbrains.com/help/phpstorm/mcp-server.html)
for the current client. In PhpStorm 2025.2+, open the project, enable its bundled MCP server in
**Settings → AI → MCP Server**, and use its client configuration controls. Expose the inspection tools the
integration needs. If the developer has no PhpStorm, provide the
[official download page](https://www.jetbrains.com/phpstorm/download/) as an optional choice.
The plugin saves consent and uses tools advertised by the current client. The developer controls IDE and client configuration.

When an applicable file is available, verify one read-only inspection against the open project before reporting
the connection as verified. An enabled preference does not establish a connection. If configuration requires a
new client session or the IDE is closed, say that the integration is enabled and the connection is pending.

Use `ready-check.py config get phpstormMcp --project <repo>` to read the preference and
`ready-check.py config set phpstormMcp false --project <repo>` to turn it off.
