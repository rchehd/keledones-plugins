# DevOps review

Apply the areas triggered by changed paths and record the actual tool or provider version where relevant.

| Change | Review |
| --- | --- |
| GitHub Actions or GitLab CI | Trace events, branch and environment conditions, job dependencies and permissions. Check how untrusted input reaches shell commands and whether secrets or privileged runners are available to untrusted jobs. |
| Compose, DDEV or Dockerfile | Compare the resolved stack for affected variants. Check interpolation, build context, exposed services and ports, health checks, secrets, and persistent volume behavior. |
| Nginx | Trace effective includes, host selection and location precedence. Check redirects, proxy headers, access control, timeout and upload limits. |
| Deployment or artifacts | Verify rollback and retry behavior, provenance, expected files and the consumer install path. |

[GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use) ·
[GitLab pipeline security](https://docs.gitlab.com/ci/pipeline_security/) ·
[Compose file reference](https://docs.docker.com/reference/compose-file/)
