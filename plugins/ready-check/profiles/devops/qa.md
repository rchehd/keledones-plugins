# DevOps QA

Configuration validation is static evidence. For changed job, deployment or artifact behavior, verify the
affected scenario against the designated test environment or an existing run at the tested revision. Record
the run, trigger or ref, exact job and relevant evidence. Inspect the artifact and try the documented consumer
install path when packaging changes. Provider UI, job logs or the project's existing CLI or API can provide
evidence.

For Compose or DDEV, use health and dependency checks for the affected services after approved startup or
preparation. For Nginx, verify actual HTTP behavior for affected routes, redirects and proxy headers. Include
an authorization or error case where the task changes that behavior. Use browser QA for browser-facing flows.
