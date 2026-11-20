import argparse
import html
import json
import math
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from string import Template
from uuid import uuid4

from dependency_support import PLUGIN
from git_exclude import git
from project import ensure_excluded, redirected, toplevel
from qa_evidence import RECORDING, capture_attempt, recording_digest
from reports import prepare, require_migrated
from tasks import append


def journal_field(label, value):
    if not value.strip():
        raise ValueError("Action and observed result must both be nonempty")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    longest = max((len(run) for run in re.findall(r"~+", value)), default=0)
    fence = "~" * max(3, longest + 1)
    content = "\n".join(f"  {line}" for line in value.split("\n"))
    return f"  **{label}**\n\n  {fence}\n{content}\n  {fence}\n\n"


def field_pattern(name):
    fence = f"{name}_fence"
    return (rf"  \*\*{name.title()}\*\*\n\n  (?P<{fence}>~{{3,}})\n"
            rf"(?P<{name}>(?:(?!  (?P={fence})\n)  [^\n]*\n)+)  (?P={fence})\n\n")


HEADER = r"^- \S+ · (?P<actor>agent|user|runner)"
STEP_ID = r"  <!-- qa-step:(?P<id>[0-9a-f]{32}) -->\n"
ENTRY = re.compile(
    HEADER + r" · Attempt (?P<attempt>[1-9][0-9]*)\n\n" + field_pattern("action")
    + rf"(?:{field_pattern('expected')})?" + field_pattern("observed") + STEP_ID, re.MULTILINE,
)
LEGACY_ENTRY = re.compile(
    HEADER + r" · (?:Attempt (?P<attempt>[1-9][0-9]*) · )?\*\*(?P<action>[^\n]+)\*\*\n"
    r"(?:  Expected: (?P<expected>[^\n]+)\n)?  Observed: (?P<observed>[^\n]+)\n"
    + rf"(?:{STEP_ID})?", re.MULTILINE,
)
MARKER = re.compile(r"^<!-- qa-video:([0-9a-f]{32}) ([0-9a-f]{64}) ([0-9]+(?:\.[0-9]+)?) -->$", re.MULTILINE)


def evidence_directory(project, task, round_number, case, *, create=False):
    if round_number < 1 or not re.fullmatch(r"QA-[0-9]{3,}", case):
        raise ValueError("Use a positive round number and a scenario ID such as QA-001")
    project = project.resolve(strict=True)
    report = Path(prepare(project, task, dry_run=True)["directory"])
    top = toplevel(project)
    require_migrated(top or project, report)
    report_file = report / "report.md"
    if redirected(report_file) or not report_file.is_file():
        raise ValueError("Prepare the task report before recording QA actions")
    if top:
        ensure_excluded(top)

    folder = report
    for part in ("evidence", f"round-{round_number}"):
        folder = folder / part
        if redirected(folder) or folder.exists() and not folder.is_dir():
            raise ValueError(f"QA evidence requires a real directory: {folder}")
        if create:
            folder.mkdir(mode=0o700, exist_ok=True)
    return report, folder, top


def check_file(path, top):
    if redirected(path) or path.exists() and (not path.is_file() or path.stat().st_nlink > 1):
        raise ValueError(f"QA evidence requires its own regular file: {path}")
    if top and git(top, "check-ignore", "-q", "--", path.relative_to(top).as_posix()) is None:
        raise ValueError(f"QA evidence must be untracked and ignored by Git: {path}")


def record_step(project, task, round_number, case, actor, action, observed, *, attempt=1, expected=None):
    action_block = journal_field("Action", action)
    observed_block = journal_field("Observed", observed)
    expected_block = journal_field("Expected", expected) if expected is not None else ""
    report, folder, top = evidence_directory(project, task, round_number, case, create=True)
    path = folder / f"{case}-steps.md"
    check_file(path, top)

    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    step_id = uuid4().hex
    entry = (f"- {stamp} · {actor} · Attempt {attempt}\n\n"
             f"{action_block}{expected_block}{observed_block}  <!-- qa-step:{step_id} -->\n")
    append(path, entry.encode("utf-8"))
    return dict(path=str(path), evidence=path.relative_to(report).as_posix(), case=case, round=round_number,
                attempt=attempt, step_id=step_id)


def replay_rows(entries, offsets):
    items = []
    for step in entries:
        offset = offsets.get(step["id"])
        marker = ""
        if offset is not None and math.isfinite(float(offset)):
            minutes, seconds = divmod(int(float(offset)), 60)
            marker = f'<button type="button" data-at="{offset}">{minutes:02d}:{seconds:02d}</button>'
        expected = f'<p><strong>Expected</strong> {html.escape(step["expected"])}</p>' if step["expected"] else ""
        items.append(f'<li>{marker}<div><span class="actor">{step["actor"]}</span>'
                     f'<h2>{html.escape(step["action"])}</h2>{expected}'
                     f'<p><strong>Observed</strong> {html.escape(step["observed"])}</p></div></li>')
    return "".join(items)


def validate_video_name(case, video):
    if not re.fullmatch(rf"{re.escape(case)}(?:-[A-Za-z0-9][A-Za-z0-9_-]*)?\.(?:webm|mp4)", video):
        raise ValueError(f"Use a {case} WebM or MP4 filename from this case's round folder")


def check_capture_directory(path, top):
    if redirected(path) or path.exists() and not path.is_dir():
        raise ValueError(f"QA recording requires a real directory: {path}")
    if top:
        relative = path.relative_to(top).as_posix() + "/"
        if git(top, "check-ignore", "-q", "--", relative) is None or git(top, "ls-files", "--", relative) != "":
            raise ValueError(f"The entire QA recording directory must be untracked and ignored by Git: {path}")


def recording_files(folder, case, video, top):
    capture_name, separator, name = video.rpartition("/")
    validate_video_name(case, name)
    if separator:
        if not capture_name.endswith(".capture"):
            raise ValueError("Use a clip from this case's prepared recording directory")
        primary = capture_name.removesuffix(".capture")
        validate_video_name(case, primary)
        stem, ext = primary.rsplit(".", 1)
        if not re.fullmatch(rf"{re.escape(stem)}(?:-[1-9][0-9]*)?\.{ext}", name):
            raise ValueError("Use a clip from this case's prepared recording directory")
    else:
        capture_name = f"{name}.capture"

    capture = folder / capture_name
    if separator or capture.exists() or redirected(capture):
        check_capture_directory(capture, top)
        clip = capture / name
    else:
        clip = folder / name
    journal = folder / f"{case}-steps.md"
    replay = clip.with_name(f"{clip.name}-replay.html")
    for file in (clip, journal, replay):
        check_file(file, top)
    return clip, journal, replay


def prepare_recording(project, task, round_number, case, video, attempt):
    validate_video_name(case, video)
    selector = f"{video}.capture/{video}"
    number = capture_attempt(case, selector)
    if attempt is not None and number != attempt:
        raise ValueError("Use a video filename that identifies the selected attempt")
    report, folder, top = evidence_directory(project, task, round_number, case, create=True)
    capture = folder / f"{video}.capture"
    check_capture_directory(capture, top)
    check_file(folder / f"{case}-steps.md", top)
    if (folder / video).exists():
        raise ValueError("Use a new video filename for each recording attempt")
    try:
        capture.mkdir(mode=0o700)
    except FileExistsError as error:
        raise ValueError("Use a new video filename for each recording attempt") from error
    clip = capture / video
    return dict(path=str(clip), evidence=clip.relative_to(report).as_posix(), directory=str(capture),
                video=selector, case=case, round=round_number, attempt=number or 1)


def attempt_entries(journal, source, attempt):
    matches = sorted((*ENTRY.finditer(source), *LEGACY_ENTRY.finditer(source)), key=lambda entry: entry.start())
    entries = []
    for match in matches:
        if (match["attempt"] or "1") != str(attempt):
            continue
        entry = match.groupdict()
        for field in ("action", "expected", "observed"):
            value = entry[field]
            if value is not None:
                if match.re is ENTRY:
                    entry[field] = "\n".join(line[2:] for line in value[:-1].split("\n"))
                else:
                    entry[field] = html.unescape(re.sub(r"\\([\\\x60*_\[\]])", r"\1", value))
        entries.append(entry)
    if not entries:
        raise ValueError(f"The QA action journal has no recorded steps for attempt {attempt}: {journal}")
    return entries


def finished_recording(folder, case, video, top):
    clip, journal, replay = recording_files(folder, case, video, top)
    if not clip.is_file() or clip.stat().st_size == 0:
        raise ValueError(f"Missing or empty QA recording: {clip}")
    if not journal.is_file():
        raise ValueError(f"Missing QA action journal: {journal}")
    return clip, journal, replay


def finish_recording(project, task, round_number, case, video, attempt, outcome):
    report, folder, top = evidence_directory(project, task, round_number, case)
    clip, journal, _ = finished_recording(folder, case, video, top)
    selector = clip.relative_to(folder).as_posix()
    number = capture_attempt(case, selector)
    if number is None or (attempt is not None and number != attempt):
        raise ValueError("Use the prepared recording path for the selected attempt")
    source = journal.read_text(encoding="utf-8")
    attempt_entries(journal, source, number)
    digest = recording_digest(clip)
    existing = False
    for entry in RECORDING.finditer(source):
        if entry["attempt"] != str(number):
            continue
        if entry["outcome"] != outcome or (entry["video"] == selector and entry["digest"] != digest):
            raise ValueError("This attempt has different recorded evidence or a different outcome")
        existing |= entry["video"] == selector
    if not existing:
        mark = f"<!-- qa-recording: {selector} {number} {outcome} {digest} -->\n"
        append(journal, mark.encode("utf-8"))
    return dict(path=str(clip), evidence=clip.relative_to(report).as_posix(), video=selector,
                case=case, round=round_number, attempt=number, outcome=outcome)


def check_offsets(values, entries):
    known = {entry["id"] for entry in entries}
    offsets = {}
    for value in values:
        ident, _, position = value.partition("=")
        if ident not in known or ident in offsets:
            raise ValueError("Each video offset needs a unique step_id from this QA journal")
        try:
            seconds = float(position)
        except ValueError:
            seconds = -1
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("A video offset must be a finite, nonnegative number of seconds")
        offsets[ident] = f"{abs(seconds):.3f}"
    return offsets


def render_replay(project, task, round_number, case, video, timings=()):
    report, folder, top = evidence_directory(project, task, round_number, case)
    clip, journal, replay = finished_recording(folder, case, video, top)
    attempt = capture_attempt(case, clip.relative_to(folder).as_posix()) or 1
    source = journal.read_text(encoding="utf-8")
    entries = attempt_entries(journal, source, attempt)

    digest = recording_digest(clip)
    offsets = {ident: offset for ident, sha, offset in MARKER.findall(source) if sha == digest}
    additions = check_offsets(timings, entries)
    if additions:
        marks = "".join(f"<!-- qa-video:{ident} {digest} {offset} -->\n" for ident, offset in additions.items())
        append(journal, marks.encode("utf-8"))
        offsets.update(additions)
    rows = replay_rows(entries, offsets)
    template = Template((PLUGIN / "templates/qa-replay.html").read_text(encoding="utf-8"))
    journal_link = ("../" if clip.parent != folder else "") + journal.name
    content = template.substitute(case=case, attempt=attempt, video=clip.name, journal=journal_link, steps=rows)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=replay.parent, prefix=".qa-replay-", delete=False) as stream:
            temporary = Path(stream.name)
            check_file(temporary, top)
            stream.write(content)
        temporary.replace(replay)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return dict(path=str(replay), evidence=replay.relative_to(report).as_posix(), case=case, round=round_number,
                attempt=attempt)


def case_parser(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--task", required=True, help="Task ID from the prepared report")
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--case", required=True)
    return parser


def main():
    parser = case_parser("Record a sanitized action and observed result in a task's QA journal.")
    parser.add_argument("--actor", choices=("agent", "user", "runner"), default="agent")
    parser.add_argument("--action", help="Sanitized action that was executed")
    parser.add_argument("--observed", help="Sanitized result that was observed")
    parser.add_argument("--expected", help="Sanitized result the step was meant to verify")
    parser.add_argument("--attempt", type=int, help="Positive attempt number; actions default to attempt 1")
    video = parser.add_mutually_exclusive_group()
    video.add_argument("--prepare-video", metavar="FILENAME", help="Create a private directory for a new recording attempt")
    video.add_argument("--finish-video", metavar="PATH", help="Record the outcome of a completed clip")
    parser.add_argument("--outcome", choices=("PASS", "FAIL"), help="Observed attempt result for --finish-video")
    args = parser.parse_args()
    output = dict(schema_version=1, action="qa-record", status="INCOMPLETE")
    try:
        if args.attempt is not None and args.attempt < 1:
            raise ValueError("Use a positive attempt number")
        if (args.finish_video is None) != (args.outcome is None):
            raise ValueError("Use --finish-video with --outcome")
        if args.prepare_video is not None or args.finish_video is not None:
            if any(value is not None for value in (args.action, args.observed, args.expected)):
                raise ValueError("Manage the recording and write the journal step in separate commands")
            if args.finish_video is not None:
                result = finish_recording(args.project, args.task, args.round, args.case, args.finish_video,
                                          args.attempt, args.outcome)
            else:
                result = prepare_recording(args.project, args.task, args.round, args.case, args.prepare_video,
                                           args.attempt)
        else:
            if args.action is None or args.observed is None:
                raise ValueError("Recording a journal step requires --action and --observed")
            result = record_step(args.project, args.task, args.round, args.case, args.actor, args.action,
                                 args.observed, attempt=args.attempt or 1, expected=args.expected)
        output.update(result, status="PASS")
    except (OSError, ValueError) as error:
        output["reason"] = str(error)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["status"] == "PASS" else 2


def replay_main():
    parser = case_parser("Build a local player for a QA recording and its action journal.")
    parser.add_argument("--video", required=True, help="Case video path relative to the round evidence folder")
    parser.add_argument("--at", action="append", default=[], metavar="STEP_ID=SECONDS",
                        help="Verified action offset in the finished clip, repeatable")
    args = parser.parse_args()
    output = dict(schema_version=1, action="qa-replay", status="INCOMPLETE")
    try:
        output.update(render_replay(args.project, args.task, args.round, args.case, args.video, args.at), status="PASS")
    except (OSError, ValueError) as error:
        output["reason"] = str(error)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["status"] == "PASS" else 2
