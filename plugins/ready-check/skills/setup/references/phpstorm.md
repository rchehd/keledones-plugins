# Connect PhpStorm MCP

After successful installation of all Ready Check tools, ask **Connect PhpStorm MCP?** with **Yes** and **No** in
the user's language. A tool that still needs installation or a failed setup does not trigger this offer.
Use the same connection flow if a user later says “Connect PhpStorm MCP” or asks to enable it in settings.
An explicit request can start the flow directly.

On No, finish setup. The project preference defaults to off. On Yes, run
`ready-check.py setup --project <repo> --component phpstorm`. In Cursor, append `--client cursor` so Ready Check
finds the running PhpStorm MCP, checks that it can resolve this Git project and registers it in the project's
local `.cursor/mcp.json`. This opt-in authorizes the project-scoped Cursor configuration update. It preserves
other MCP entries and keeps a newly configured file out of Git through the local exclude file.

Read `registration.status` and give only the next step the result requires.

- `REGISTERED`: Ready Check added or updated the server. Restart Cursor and open a new chat to load it.
  If Cursor asks for approval, enable the server in **Customize → MCPs** for this workspace.
- `ALREADY_REGISTERED`: Reuse the existing registration. If this session lacks the tools, restart Cursor
  and open a new chat to verify that it picked up the config. If Cursor reports that the server is unapproved,
  enable it in **Customize → MCPs** for this workspace.
- `SERVER_UNAVAILABLE`: Ask the user to open this project in PhpStorm and enable its bundled MCP server in
  **Settings → AI → MCP Server**, then retry. If the server is enabled but discovery still fails, accept the
  IDE's local `/stream` URL and retry with `--phpstorm-url <url>`. Ready Check writes the Cursor config.
- `CLIENT_SETUP_REQUIRED`: If the tools are missing, use the IDE's client configuration controls for the
  current client and follow the [JetBrains setup guide](https://www.jetbrains.com/help/phpstorm/mcp-server.html).

On `INCOMPLETE`, report the specific configuration conflict or error. The MCP server is built into PhpStorm
2025.2 and later. If needed, offer the [PhpStorm download page](https://www.jetbrains.com/phpstorm/download/).

Verify one read-only inspection with this client's `lint_files` or `get_file_problems` against an applicable file
in the open project before reporting the connection as verified. Pass the explicit `projectPath` and the
project-relative file path. Registration and project opt-in do not verify
that this chat can call inspections. If the tools are missing, report that inspections are unavailable in this client.

Use `ready-check.py config get phpstormMcp --project <repo>` to read the preference and
`ready-check.py config set phpstormMcp false --project <repo>` to turn off inspections in Ready Check.
