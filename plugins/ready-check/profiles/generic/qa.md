# QA for a generic project

Map each requirement to its real entry point. For a CLI or script, check representative inputs and error cases against the documented command using a safe fixture. Verify output, return codes and expected side effects. For a workflow joining languages or tools, exercise the handoff and use the receiving tool to inspect the result.

Use Playwright when a requirement affects a browser flow. For CLI-only work, record whether a browser case applies and use command and artifact evidence for the corresponding requirements.
