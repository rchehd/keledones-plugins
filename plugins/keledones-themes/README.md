# Keledones themes

Looks for the Claude desktop and mobile apps. The terminal and editor integrations draw no themes.

| Look | Light mode | Dark mode |
| --- | --- | --- |
| `keledones` (default) | Warm cream surfaces, ink text, blue-green `#1F5673` accent, gold `#D99A43`, a faint bird watermark in the middle | Deep blue-green `#14303F` surfaces, cream text, sky `#9CCBDD` accent, the same bird watermark |
| `graphite` | White and light gray, blue `#3574F0` accent | Graphite gray `#1E1F22` / `#2B2D30`, blue accent, IDE-like code colors |

Install from the Keledones catalog:

```sh
claude plugin marketplace add rchehd/keledones
claude plugin install keledones-themes@keledones
```

| Command | Effect |
| --- | --- |
| `/look keledones` | The Keledones look |
| `/look graphite` | The Graphite look |
| `/look off` | The app's default look again |
| `/look` | Shows the current look and the available ones |

The choice is kept for later sessions. A look changes both modes; switch the app to dark mode to see its dark half.
To add a look, add a palette to `hooks/looks.ts`. `hooks/make-colors.js` is the palette helper from Claude Code's
plugin-authoring skill, kept unchanged.
