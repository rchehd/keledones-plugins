Ready Check setup for this project. Before answering the user's first message, do this once:

{question}

Commands (run them yourself; show them to the user only if you cannot run commands{fallback}):
- accept: {yes}
- decline: {no}

{language}Each `--selection PROFILE:RUNNER:APPLICATION` is independent. Keep every confirmed selection, including
different profiles in the same directory. If the user corrects a profile, root, or runner, edit that selection.
Resolve conflicting candidates before running either command.
Installation output appears in the chat; finish with its final "Ready Check is ready" or failure line.
Then answer the user's original message.
