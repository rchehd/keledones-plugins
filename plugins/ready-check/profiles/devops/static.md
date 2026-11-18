# DevOps static checks

The profile detects common CI, Docker Compose, DDEV, Dockerfile and Nginx paths. It defaults to the local host,
independently of an application profile using DDEV or Compose. Use the intended tools and runtime for the
repository. This profile uses installed tools and its setup does not download a bundle.

| Inputs | Static validation |
| --- | --- |
| GitHub Actions workflows | `actionlint` checks changed workflows using the project's config and available integrations. |
| Docker Compose | `docker compose config --quiet` validates the selected ordered stack. |
| DDEV | `ddev utility configyaml --full-yaml` resolves application config and config overrides. `yamllint` checks changed service override syntax. |
| Nginx | `nginx -t -q` checks the selected entry config in a prepared runtime with its includes and files. |
| GitLab CI | `yamllint` checks the pipeline and conventional local CI includes under `.gitlab/ci/`. Add a result from GitLab CI Lint for the effective config, relevant ref and includes. |
| Dockerfiles | Use the project's existing linter or a supported BuildKit check. Record its result along with the shared diff check. |

For GitLab, use the intended GitLab project's validation entry point. Record its result and the ref or revision
that covers the change. The static CLI performs local syntax validation. The check skill includes the
effective pipeline validation as a required project check when a task changes GitLab pipeline behavior.
Get authorization for any remote operation that sends a local config to the provider.

When DDEV service overrides change, include the effective stack as a required project check. Use
`ddev utility compose-config` in the intended test environment or an isolated fixture. The command
regenerates DDEV's Compose files. Confirm the current overrides are present in the result and use redacted
evidence in the task report.

Compose uses `COMPOSE_FILE` on the host when set, or an available default file and override. For a custom file
set or separate variants, put the intended ordered files in the application's `.ready-check.json` and check
each affected variant. Use the project's interpolation inputs in the selected environment. A changed file
outside the effective stack or missing interpolation input needs clarification. Compose, DDEV and Nginx
evidence records command status without copying their configuration output.

```json
{
  "devops": {
    "compose_files": ["compose.yaml", "compose.dev.yaml"],
    "nginx_config": "nginx/nginx.conf",
    "nginx_prefix": "nginx"
  }
}
```

`nginx_config` defaults to `nginx.conf` and `nginx_prefix` to the application root. Use application-relative paths.
Resolve Nginx includes, log directories and certificates in the intended environment before running the check.
Read the local command output when a checker cannot validate the configuration. Save only redacted excerpts.

[actionlint usage](https://github.com/rhysd/actionlint/blob/main/docs/usage.md) ·
[Compose config](https://docs.docker.com/reference/cli/docker/compose/config/) ·
[DDEV utilities](https://docs.ddev.com/en/stable/users/usage/commands/) ·
[Nginx parameters](https://nginx.org/en/docs/switches.html) ·
[GitLab CI Lint](https://docs.gitlab.com/ci/yaml/lint/) ·
[BuildKit checks](https://docs.docker.com/reference/build-checks/)
