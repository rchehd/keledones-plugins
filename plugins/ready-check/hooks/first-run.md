Ready Check setup for this project. Before answering the user's first message, do this once:

{question}

Commands (run them yourself; show them to the user only if you cannot run commands{fallback}):
- accept: {yes}
- decline: {no}

{language}If the user corrects the project type or runner, change `--profile` / `--runner` in the command.
Installation output appears in the chat; finish with its final "Ready Check is ready" or failure line.
Then answer the user's original message.
