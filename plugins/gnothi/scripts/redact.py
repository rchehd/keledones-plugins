from __future__ import annotations

import re
from pathlib import Path

SECRET = "<secret>"
URL = "<url:host-hidden>"
TLDS = "com|net|org|io|dev|ai|co|ua|ru|uk|de|eu|xyz|cloud|tech|online|gov|edu|us|ca|fr|nl|es|jp|cn|br|au|ch|se|fi|cz|sk|tv|gg|ly"
RULES = (
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), SECRET),
    (re.compile(r"\b[a-z][a-z0-9+.-]*://\S+", re.I), URL),
    (re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+"), "<email>"),
    (re.compile(r"(?<![\w@.-])(?:(?i:www\.)[\w-]+(?:\.[\w-]+)+|(?i:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+"
                rf"(?:{TLDS}))(?![\w-]|\.\w)(?:[/:?#]\S*)?"), URL),
    (re.compile(r"((?:password|passwd|passphrase|pass|pwd|secret\w*|token\w*|api[_-]?key\w*)(?![a-z])[\"']?\s*[:=]\s*[\"']?)"
                r"[^\s\"',}]+", re.I), r"\1" + SECRET),
    (re.compile(r"\bBearer\s+\S+", re.I), SECRET),
    (re.compile(r"\b(sk-[\w-]{16,}|sk_(?:live|test)_\w{10,}|gh[pousr]_\w{20,}|github_pat_\w{20,}|glpat-[\w-]{20,}|"
                r"AIza[\w-]{20,}|npm_\w{20,}|hf_\w{20,}|AKIA[0-9A-Z]{16}|xox[abpr]-[\w-]{8,})"), SECRET),
    (re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+"), SECRET),
    (re.compile(r"\b[0-9a-f]{32,}\b", re.I), SECRET),
    (re.compile(r"(?<![\w/+])[A-Za-z0-9+/]{40,}={0,2}"), SECRET),
)


def redact(text):
    text = str(text or "")
    parts = [part for part in re.split(r"[\\/]", str(Path.home())) if part]

    if parts:
        prefix = "" if re.match(r"[A-Za-z]:$", parts[0]) else r"[\\/]"
        text = re.sub(prefix + r"[\\/]".join(map(re.escape, parts)) + r"(?![\w.-])", "~", text, flags=re.I)

    for pattern, replacement in RULES:
        text = pattern.sub(replacement, text)

    return text


def excerpt(text, size=150):
    text = " ".join(redact(text).split())

    if len(text) <= size:
        return text

    cut = text[:size - 1].rsplit(" ", 1)[0] or text[:size - 1]
    return cut.rstrip(" ,.;:") + "…"
