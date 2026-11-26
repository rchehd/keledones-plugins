# Report language

Use the language of the current conversation for every human-facing report, plan and result, including
the saved Markdown and the local HTML. Use the user's own messages to resolve it. A slash command,
pasted log, ticket text, repository language, template or client locale alone is insufficient. If the
conversation leaves the language unclear, ask once with the native question tool before writing the
report and use the answer throughout. Honor an explicit language choice in this chat.

Fill templates in that language. Translate every visible title, section heading, list label, table
header, status, empty state, media caption and chart label. For example in a Ukrainian report, use
“Обсяг перевірки”, “Стан вимоги”, “Уточнено” and “Не вибрано” for check selection, clarity, defined and
not selected. Keep file paths, commands, identifiers and exact source or diagnostic quotes as code
where needed. Keep the task metadata keys and canonical values in the report template's hidden
comment and in machine-readable tool inputs. Keep commit and PR/MR drafts in English.

When updating a report written in another language, translate the complete visible report together.
Preserve prior evidence, IDs and metadata. Before sharing any version, check the heading, table
headers, statuses, links and generated labels for stray template or tool text.
