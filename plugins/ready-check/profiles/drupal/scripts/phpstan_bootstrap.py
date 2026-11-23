import hashlib
import json
import re
from base64 import b64encode
from pathlib import Path


REDECLARATION = re.compile(
    r"Cannot redeclare (?:function )?(?P<name>[a-zA-Z_][a-zA-Z_0-9]*)\(\)"
    r" \(previously declared in (?P<first>[^\r\n]+):(?P<first_line>\d+)\)"
    r" in (?P<second>[^\r\n]+) on line (?P<second_line>\d+)",
)

DECLARATIONS = r"""
[$script, $first, $second, $name, $firstLine, $secondLine, $skipped] = $argv;
function declarations(string $path): ?array {
    $tokens = PhpToken::tokenize(file_get_contents($path), TOKEN_PARSE);
    $context = [];
    $declarations = [];
    for ($i = 0; isset($tokens[$i]); $i++) {
        $token = $tokens[$i];
        if ($token->isIgnorable()) {
            continue;
        }
        if ($token->is([T_USE, T_DECLARE])) {
            $statement = [];
            do {
                $part = $tokens[$i++];
                if (!$part->isIgnorable()) {
                    $statement[] = $part->text;
                }
            } while (!$part->is(';') && isset($tokens[$i]));
            if ($token->is(T_DECLARE) && !preg_match('/^declare\(strict_types=[01]\);$/', implode('', $statement))) {
                return null;
            }
            $context[] = $statement;
            $i--;
            continue;
        }
        if (!$token->is(T_FUNCTION)) {
            return null;
        }

        $identifier = $i + 1;
        while ($tokens[$identifier]->isIgnorable() || $tokens[$identifier]->text === '&') {
            $identifier++;
        }
        $name = strtolower($tokens[$identifier]->text);
        if (!$tokens[$identifier]->is(T_STRING) || isset($declarations[$name])) {
            return null;
        }
        $doc = null;
        for ($j = $i - 1; $j >= 0 && $tokens[$j]->is([T_WHITESPACE, T_COMMENT, T_DOC_COMMENT]); $j--) {
            if ($tokens[$j]->is(T_DOC_COMMENT)) {
                $doc = $tokens[$j]->text;
                break;
            }
        }
        $definition = '';
        $depth = 0;
        $usesLocation = false;
        for (; isset($tokens[$i]); $i++) {
            $part = $tokens[$i];
            $usesLocation = $usesLocation || $part->is([T_FILE, T_DIR, T_LINE, T_HALT_COMPILER]);
            $definition .= $part->text;
            if ($part->is(['{', T_CURLY_OPEN, T_DOLLAR_OPEN_CURLY_BRACES])) {
                $depth++;
            } elseif ($part->is('}') && --$depth === 0) {
                break;
            }
        }
        $declarations[$name] = ['line' => $token->line, 'usesLocation' => $usesLocation,
                                'definition' => [$context, $doc, $definition]];
    }
    return $declarations;
}
$name = strtolower($name);
$left = declarations($first);
$right = declarations($second);
if (($left[$name]['line'] ?? null) !== (int) $firstLine || ($right[$name]['line'] ?? null) !== (int) $secondLine) {
    exit(1);
}
$shared = array_intersect_key($left, $right);
foreach ($shared as $function => $declaration) {
    $other = $right[$function];
    if ($declaration['usesLocation'] || $other['usesLocation'] || $declaration['definition'] !== $other['definition']) {
        exit(1);
    }
}
$functions = array_fill_keys(array_keys($skipped === '0' ? $left : $right), false);
echo json_encode(array_replace($functions, array_fill_keys(array_keys($shared), true)), JSON_THROW_ON_ERROR);
"""

BOOTSTRAP = r"""<?php declare(strict_types=1);

use mglaman\PHPStanDrupal\Drupal\DrupalAutoloader;
use mglaman\PHPStanDrupal\Drupal\Extension;

if (!defined('DRUPAL_TEST_IN_CHILD_SITE')) {
    define('DRUPAL_TEST_IN_CHILD_SITE', false);
}

$recovery = json_decode(base64_decode('__RECOVERY_SETTINGS__'), true, flags: JSON_THROW_ON_ERROR);

(new class($recovery['skipped']) extends DrupalAutoloader {
    public function __construct(private string $skipped) {}

    protected function loadExtension(Extension $extension): void
    {
        $filename = $extension->getExtensionFilename();
        if ($extension->getType() !== 'theme' || $filename === null ||
            realpath($extension->getAbsolutePath() . DIRECTORY_SEPARATOR . $filename) !== $this->skipped) {
            parent::loadExtension($extension);
        }
    }
})->register($container);

foreach ($recovery['functions'] as $function => $shared) {
    if (!function_exists($function)) {
        if ($shared) {
            throw new RuntimeException("PHPStan recovery could not load {$function}() from the retained theme.");
        }
        continue;
    }
    $file = (new ReflectionFunction($function))->getFileName();
    if (!$shared || $file === false || realpath($file) !== $recovery['retained']) {
        $origin = $file === false ? 'a PHP extension' : $file;
        throw new RuntimeException("PHPStan recovery found an unexpected declaration of {$function}() in {$origin}.");
    }
}
"""


def redeclaration(lint, output):
    code, stdout, stderr = output
    match = REDECLARATION.search((stderr + b"\n" + stdout).decode(errors="replace")) if code == 255 else None
    if match:
        return dict(function=match["name"], exit_code=code,
                    declarations=[dict(path=lint.relative(match[key]), line=int(match[key + "_line"])) for key in ("first", "second")])
    return None


def recovery_files(lint, conflict):
    scope = lint.selected["scope"]
    prefix = lint.project.relative_to(scope["repository"])
    changed = {*scope["changed_files"], *scope.get("uncommitted_outside_task", ())}
    entries = conflict["declarations"]
    candidates = [Path(entry["path"]) for entry in entries]

    for path in candidates:
        source = lint.project / path
        if (path.is_absolute() or ".." in path.parts or path.suffix != ".theme" or path.as_posix() in changed
                or (prefix / path).as_posix() in scope["outside_scope"] or not source.is_file() or source.resolve() != source):
            return None
    if candidates[0] == candidates[1]:
        return None

    runner_paths = [lint.runner.path(path.as_posix()) for path in candidates]
    if any(lint.runner.realpath(path) != path for path in runner_paths):
        return None
    profile_themes = [path for path in candidates if "profiles" in path.parts]
    skipped = profile_themes[0] if len(profile_themes) == 1 else candidates[1]
    skipped_index = candidates.index(skipped)
    expected = fingerprints(lint, runner_paths)
    lines = [str(entry["line"]) for entry in entries]
    code, stdout, _ = lint.runner.exec(["php", "-r", DECLARATIONS, "--", *runner_paths, conflict["function"], *lines, str(skipped_index)])
    if code:
        return None
    functions = json.loads(stdout)
    if not isinstance(functions, dict) or functions.get(conflict["function"].lower()) is not True:
        return None
    settings = dict(skipped=runner_paths[skipped_index], retained=runner_paths[1 - skipped_index], functions=functions)
    return settings, runner_paths, expected


def scoped_bootstrap(lint, config, settings):
    payload = b64encode(json.dumps(settings).encode()).decode("ascii")
    bootstrap = lint.temporary("phpstan-scoped-bootstrap.php", BOOTSTRAP.replace("__RECOVERY_SETTINGS__", payload))
    return lint.temporary("phpstan-scoped.neon", config + f"  bootstrapFiles!:\n    - {json.dumps(bootstrap)}\n"
                          f"  scanFiles:\n    - {json.dumps(settings['skipped'])}\n")


def fingerprints(lint, paths):
    return {
        lint.relative(path): hashlib.sha256(lint.runner.read(path)).hexdigest()
        for path in paths
    }


def handle_report(lint, result, args, paths, generated):
    conflict = redeclaration(lint, result)
    if not conflict:
        lint.parse("phpstan", *result)
        return

    lint.details["bootstrap_conflict"] = conflict
    try:
        recovery = recovery_files(lint, conflict) if generated else None
    except (OSError, ValueError, RuntimeError):
        recovery = None
    if recovery:
        settings, theme_paths, expected = recovery
        config = scoped_bootstrap(lint, generated, settings)
        lint.parse("phpstan", *lint.call([*args[:3], config, *args[4:], *paths]))
        try:
            if fingerprints(lint, theme_paths) != expected:
                lint.incomplete.append("Conflicting Drupal theme files changed during PHPStan recovery")
        except (OSError, ValueError):
            lint.incomplete.append("Cannot verify conflicting Drupal theme files after PHPStan recovery")
        if not lint.incomplete:
            lint.details["bootstrap_recovery"] = dict(scanned_without_loading=lint.relative(settings["skipped"]), sha256=expected)
            return

    locations = " and ".join(f"{item['path']}:{item['line']}" for item in conflict["declarations"])
    lint.incomplete.append(f"PHPStan bootstrap exited {conflict['exit_code']}: Cannot redeclare {conflict['function']}() in {locations}; see log")
