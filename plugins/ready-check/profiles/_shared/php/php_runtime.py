from pathlib import Path


def is_php(spec, file):
    return Path(str(file)).suffix in spec.php_extensions and not str(file).endswith(tuple(getattr(spec, "template_suffixes", ())))


def php(runner, code, *args, input=None):
    status, stdout, stderr = runner.exec(["php", "-r", code, "--", *map(str, args)], input=input)

    if status:
        raise ValueError(stderr.decode(errors="replace").strip() or "PHP runner operation failed")

    return stdout.decode(encoding="utf-8").strip()
