# Python task preparation

Read `profile.json` in this directory for detection signals and the profile version. Schema version `1`
describes task preparation and the doctor/static entry points. Read `static.md` before running those checks.

## Detection

Treat the application as a Python candidate when `pyproject.toml`, `requirements.txt`, `setup.cfg` or `manage.py`
exists in the application root. The profile has the lowest priority: Drupal, Laravel and Symfony applications are
detected first, so a stray `requirements.txt` never selects this profile. The detection result carries the
`framework` (`django` from `manage.py` or a `django` dependency, `fastapi`, `flask`) or `null`. A library without an
application has nothing to run here: ask which application hosts its QA. If other framework evidence contradicts the
detection, ask which application is in scope.

## Setup prerequisites

Managed profile setup needs Python 3.10+, `python3 -m venv` and Node.js 20+ with npm in the selected runner (local,
or the Compose service that runs the app). The managed tools live in a separate hashed venv in the data folder, never in
the project. Do not install project dependencies merely to manufacture a setup prerequisite; Django checks need the
project's own environment (`.venv`, `venv`, `uv`, Poetry or `READY_CHECK_PYTHON`).

## Requirement questions

Ask only when the task leaves a relevant behavior unclear:

- Which users or permissions may use the changed view, endpoint or command, and what do others see?
- Which fields may the client set, and which must stay server-controlled?
- What must persist after reload, and what happens to existing rows (migration, defaults, backfill)?
- Is the work synchronous, or does it belong in a task queue or background job?
- Which settings differ between environments (`DEBUG`, `ALLOWED_HOSTS`, secrets)?

Record possible migration, settings and dependency concerns as planned review or setup questions. They are not
confirmed defects. Keep task acceptance criteria separate from suggested Python regression checks.
