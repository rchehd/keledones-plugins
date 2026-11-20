import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared/core"))
from core_checks import Parser, format_line

CONFIGS = (".php-cs-fixer.php", ".php-cs-fixer.dist.php")
YAML = {".yml", ".yaml"}
DOCTRINE_PARTS = {"Entity", "Document", "migrations"}
DI_BLOCK = re.compile(r"^[ ]*\[(Symfony\\Component\\DependencyInjection\\Exception\\(?!Env)\w+)\][ ]*\n(.*?)\n[ ]*\n", re.M | re.S)
BOOT_ERROR = "bin/console did not boot the application"


def under(path, *roots):
    return Path(path).parts[:1] in [(root,) for root in roots]


def php_applies(paths):
    return any(Path(p).suffix == ".php" for p in paths)


def container_applies(paths):
    return any(Path(p).suffix == ".php" or Path(p).suffix in YAML and under(p, "config") for p in paths)


def yaml_applies(paths):
    return any(Path(p).suffix in YAML and under(p, "config", "translations") for p in paths)


def twig_applies(paths):
    return any(Path(p).suffix == ".twig" for p in paths)


def xliff_applies(paths):
    return any(Path(p).suffix in {".xlf", ".xliff"} for p in paths)


def schema_applies(paths):
    return any(Path(p).suffix == ".php" and DOCTRINE_PARTS & set(Path(p).parts) or
               Path(p).suffix in YAML | {".xml"} and under(p, "config") and "doctrine" in str(p) for p in paths)


def csfixer_config(project, evidence):
    config = next((n for n in CONFIGS if (project / n).is_file()), None)
    return evidence(project, config, "PHP-CS-Fixer, @Symfony ruleset")


def csfixer_report(lint, data):
    reported = False

    for entry in data["files"]:
        reported = True
        fixers = ", ".join(entry.get("appliedFixers", []))
        line = format_line(lint, entry["name"], entry.get("diff"))

        if line is not None:
            lint.add(entry["name"], line, "Style differs from the PHP-CS-Fixer rules" + (": " + fixers if fixers else ""), "error", "csfixer")

    return reported


def lint_report(lint, data):
    reported = False

    if not isinstance(data, list):
        raise ValueError("Expected an array")

    for entry in data:
        if entry.get("valid", True):
            continue
        reported = True

        for item in entry.get("messages") or [entry]:
            lint.add(entry["file"], max(int(item.get("line") or 0), 0), str(item.get("message", "Invalid")), "error", lint.check)

    return reported


PARSERS = {"csfixer": Parser({0, 8}, "{", csfixer_report), "lint": Parser({0, 1}, "[", lint_report)}


def console(lint, *args):
    return lint.call(["php", lint.runner.path("bin/console"), *args, "--no-interaction", "--no-ansi"])


def csfixer_run(lint):
    tool = next(t for t in lint.selected["tools"] if t["name"] == "php-cs-fixer")
    conf = tool["configuration"]
    args = [tool["path"], "check", "--format=json", "--diff", "--using-cache=no", "--no-interaction"]
    args += ["--config", lint.runner.path(conf["path"])] if conf["source"] == "project" else ["--rules=@Symfony"]
    lint.parse("csfixer", *lint.call([*args, "--", *[lint.runner.path(f) for f in lint.files if f.endswith(".php")]]))


def json_lint(command, applies):
    def run(lint):
        files = [lint.runner.path(f) for f in lint.files if applies([f])]
        code, stdout, _ = console(lint, command, *files, "--format=json")
        lint.parse("lint", code, stdout, label=command)

    return run


def unwrap(block):
    text = ""

    for row in block.splitlines():
        text += row.strip() + ("" if len(row.rstrip()) >= len(row) - 2 else " ")

    return text.strip()


def container_run(lint):
    code, stdout, stderr = console(lint, "lint:container", "-v")
    text = (stdout + stderr).decode(errors="replace")

    if code == 0 and "linted successfully" in text:
        return
    error = DI_BLOCK.search(text)

    if not error:
        lint.incomplete.append(f"lint:container did not complete: {BOOT_ERROR} or failed unexpectedly; see log")
        return
    lint.add("config/services.yaml", 0, unwrap(error[2]) or error[1], "error", "container")


def schema_run(lint):
    if not lint.runner.exists(lint.runner.path("vendor/doctrine/orm"), "dir"):
        lint.na = "Doctrine ORM is not installed"
        return
    code, stdout, stderr = console(lint, "doctrine:schema:validate", "--skip-sync")
    text = (stdout + stderr).decode(errors="replace")

    if code == 0 and "mapping files are correct" in text:
        return

    if not re.search(r"^Mapping\n-+$", text, re.M):
        lint.incomplete.append(f"doctrine:schema:validate did not complete: {BOOT_ERROR} or failed unexpectedly; see log")
        return
    messages = re.findall(r"^\s*\[FAIL\]\s*(.+?)\s*$|^\s*\*\s+(.+?)\s*$", text, re.M)
    messages = [a or b for a, b in messages] or re.findall(r'Message: "(.+?)"$', text, re.M) or ["Doctrine mapping is invalid"]

    for message in messages:
        lint.add("src/Entity", 0, message, "warning", "schema")
