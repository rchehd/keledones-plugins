Ready Check setup for this project. Use this once when handling installation, verification, or work that needs
Ready Check's project setup. For a request only to view or change settings, handle it in chat and defer this
setup, including the profile and installation questions.

{question}

Commands (run them yourself; show them to the user only if you cannot run commands{fallback}):
- accept: {yes}
- decline: {no}

Each `--selection PROFILE:RUNNER:APPLICATION` is independent. Keep every confirmed selection, including
different profiles in the same directory. If the user corrects a profile, root, or runner, edit that selection.
Resolve conflicting candidates before running either command.
Installation output appears in the chat; finish with its final "Ready Check is ready" or failure line.
After successful installation of all tools, follow the optional Yes/No PhpStorm MCP question in the installed
setup skill's `references/phpstorm.md`. The install choice does not approve the optional connection.
Then answer the user's original message.
