# Contributing to Gnothi

## What fits

- Parsing fixes when a client changes its history format, with a synthetic fixture that shows the new shape.
- Better signals, redaction rules or axis templates, with a test.
- Report and skill improvements.

## Privacy

Never commit real session history, reports, digests or excerpts from them. Fixtures are written from scratch and
contain no client code, names, URLs or data.

## How to check a change

```sh
python3 -B scripts/validate-package.py
python3 -B -m unittest discover -s tests -v
claude plugin validate --strict .
```

Scripts use the Python standard library only and must not import network modules; a test enforces it.

## Pull requests

- One change per pull request.
- Raise the version with `python3 -B scripts/bump-version.py X.Y.Z` when users should get the update.
