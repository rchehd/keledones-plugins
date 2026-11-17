# Review a generic project

## Always review

- Trace each requirement through the entry point, its callers and the affected tests.
- Verify the changed interfaces across languages, including argument formats, exit codes, error streams, encoding and paths.
- Check the relevant practices for the actual languages and versions in the project.

## Scripts and automation

- Check quoting, subprocess argument handling, error propagation, cleanup and retries. Verify that failures and partial runs preserve data and that filesystem writes stay within the intended scope.
- Review how the command is invoked across the operating systems and shells it supports. Use changed CI and build definitions to confirm prerequisites and verify how the resulting artifacts are consumed.

## Configuration and external systems

- Check parsing, validation, defaults and compatibility with existing inputs. Trace secrets and untrusted values through commands, filesystem paths, URLs, logs and network requests.
- For external writes, review authorization, side effects, failure behavior and repeated execution.
