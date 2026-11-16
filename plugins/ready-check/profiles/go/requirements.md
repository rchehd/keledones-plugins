# Go task preparation

Read `profile.json` in this directory for detection signals and the profile version. Schema version `1`
describes task preparation and the doctor/static entry points. Read `static.md` before running those checks.

## Detection

Treat the application as a Go candidate when `go.mod` exists in the application root. A `go.mod` in a subfolder never
selects this profile for the repository: the application folder is chosen like for other profiles. The profile ranks
below the PHP framework profiles (Drupal, Laravel, Symfony) and above Python, so a Go service with a stray
`requirements.txt` is still Go. If other evidence contradicts the detection, ask which application is in scope.

## Setup prerequisites

Managed profile setup needs Go 1.26 or newer and Node.js 20+ with npm in the selected runner (local, or the Compose
service that runs the app). golangci-lint and govulncheck are built with `go install` at pinned versions into a hashed
folder in the data folder, never into the project; `GOTOOLCHAIN=local` is forced, so an older Go is reported as
incompatible and no toolchain is downloaded. Do not run `go mod tidy` or `go get` merely to manufacture a prerequisite.

## Requirement questions

Ask only when the task leaves a relevant behavior unclear:

- Which callers (users, services) may use the changed endpoint or command, and what do others receive?
- Which request fields and sizes are valid, and what is returned for invalid input (status code, body)?
- What must persist, and what happens to existing rows (schema change, backfill)?
- Which operations may block or run long, and what timeout or cancellation applies?
- Which settings differ between environments (listen address, database DSN, secrets)?

Record possible concurrency, resource and dependency concerns as planned review or setup questions. They are not
confirmed defects. Keep task acceptance criteria separate from suggested Go regression checks.
