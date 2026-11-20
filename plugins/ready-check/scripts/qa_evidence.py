import hashlib
import re


RECORDING = re.compile(
    r"^<!-- qa-recording: (?P<video>[A-Za-z0-9._/-]+) (?P<attempt>[1-9][0-9]*) "
    r"(?P<outcome>PASS|FAIL) (?P<digest>[0-9a-f]{64}) -->$", re.MULTILINE,
)


def capture_attempt(case, video):
    match = re.fullmatch(
        rf"(?P<stem>{re.escape(case)}-attempt-(?P<attempt>[1-9][0-9]*))\.(?P<ext>webm|mp4)"
        r"\.capture/(?P=stem)(?:-[1-9][0-9]*)?\.(?P=ext)", video,
    )
    return int(match["attempt"]) if match else None


def recording_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
