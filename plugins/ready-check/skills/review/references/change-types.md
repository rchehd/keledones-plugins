# Shared review checklists

Select the rows that match the affected behavior, using the diff, callers and the task's acceptance conditions.
Apply them alongside the profile's stack-specific guidance. When a profile item already covers the same
behavior, cite the same evidence and finding ID. Record the affected paths, relevant row, source, result and
reason in the practices/security table. Mark untriggered rows with a reason.

| Change type | Inspect | Evidence or QA handoff |
| --- | --- | --- |
| Public API, command or event contract | Trace changed inputs, outputs, errors and defaults through current and supported older consumers. Check how omitted, invalid or unexpected input reaches validation. For documented interfaces, compare code and contract. | Cite server and consumer paths. Identify the command, request or contract test that proves compatibility and the expected observable result. |
| Authentication, authorization or untrusted input | Follow identity, ownership and role checks at the server, including list and bulk paths. Trace validation, escaping, and sensitive data reaching storage, logs and output. Consult the relevant versioned OWASP ASVS requirements for web or API changes. | Identify an allowed actor and a disallowed role or resource owner. Give the expected response and any state that must remain unchanged. |
| Breaking schema, interface or staged deployment | Trace which versions may coexist. For parallel change, check the expand, migrate and contract steps, including older readers and writers, backfill and rollback or recovery. Check data preservation and the removal condition for compatibility logic. | Identify the versions or fixture state needed to prove migration, continued reads and writes, or recovery. |
| Retryable write, job, callback or integration | Check idempotency scope and lifetime, concurrent duplicates, failure between durable state and external effects, and what happens when the same key is reused with different input. | State the retry or interruption to reproduce and what may happen exactly once, such as a row, payment or message. |
| CI, deployment or distribution | Trace event and ref filters, job and runner access, untrusted inputs, credentials, and artifact producers and consumers. Check what gets uploaded, installed, or promoted and how it is tied to the revision. | Identify the exact job, tested revision and artifact. Include an inspection or installation case if the delivered artifact changed. |

Use the existing code-quality and tests sections for general design, behavior, simplicity and test coverage.
Send each unresolved runtime assertion to QA with its RC ID, target, actor or preconditions, action and expected
observable result. Use a regression label for findings outside the task's requirements.

[Google Code Review Guide](https://google.github.io/eng-practices/review/reviewer/looking-for.html) ·
[OWASP ASVS](https://asvs.owasp.org/) ·
[Parallel Change](https://martinfowler.com/bliki/ParallelChange.html) ·
[AWS Builders' Library on idempotent retries](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/)
