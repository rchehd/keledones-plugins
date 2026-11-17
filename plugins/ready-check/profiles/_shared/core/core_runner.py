import os
import re
import shlex
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from detect import COMPOSE as COMPOSE_FILES
from process_support import execute, find_command


class Runner:
    def __init__(self, project, config, defaults):
        self.project = project
        self.compose = next((name for name in COMPOSE_FILES if (project / name).is_file()), "")
        automatic = defaults.get("name") or ("ddev" if (project / ".ddev/config.yaml").is_file() else "compose" if self.compose else "local")
        self.name = os.environ.get("LINT_RUNNER") or config.get("runner") or automatic

        if self.name not in {"local", "ddev", "compose"}:
            raise ValueError(f"Unsupported runner: {self.name}")
        container_root = os.environ.get("LINT_CONTAINER_ROOT") or config.get("container_root") or defaults["root"]
        self.service = os.environ.get("LINT_SERVICE") or config.get("service") or self.default_service(defaults["services"])

        if not isinstance(self.service, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", self.service):
            raise ValueError("Invalid Compose service name")
        self.root = str(project) if self.name == "local" else container_root

        if self.name != "local" and (not isinstance(self.root, str) or not PurePosixPath(self.root).is_absolute()):
            raise ValueError("Container root must be an absolute POSIX path")
        self.tools = os.environ.get("LINT_PHPSTAN_TOOLS", "")

        if any("\0" in path or "\n" in path or "\r" in path for path in (self.root, self.tools)):
            raise ValueError("Runner paths cannot contain NUL or newline characters")
        self.cache = {}

    def compose_services(self):
        try:
            text = (self.project / self.compose).read_text(encoding="utf-8") if self.compose else ""
        except (OSError, UnicodeDecodeError):
            return set()
        block = re.search(r"^services:[ \t]*\n((?:[ \t]+\S.*\n?|[ \t]*\n)*)", text, re.M)
        indent = re.search(r"^([ \t]+)\S", block[1], re.M) if block else None

        if not indent:
            return set()
        return set(re.findall(r"^" + re.escape(indent[1]) + r"([A-Za-z0-9_.-]+)[ \t]*:", block[1], re.M))

    def default_service(self, services):
        declared = self.compose_services()
        return next((name for name in services if name in declared), services[0])

    def path(self, *parts):
        return str(Path(self.root).joinpath(*parts)) if self.name == "local" else str(PurePosixPath(self.root).joinpath(*parts))

    def exec(self, argv, timeout=15, input=None, env=None, cwd=None):
        if self.name == "local":
            environment = dict(os.environ)

            for key, value in (env or {}).items():
                if value is None:
                    environment.pop(key, None)
                else:
                    environment[key] = str(value)
            return execute(argv, cwd or self.project, timeout, environment, input)
        arguments = [str(arg) for arg in argv]
        command = shlex.join(arguments)

        if env:
            command = shlex.join(["env", *(part for key, value in env.items() if value is None for part in ("-u", key)),
                                  *(key + "=" + str(value) for key, value in env.items() if value is not None), *arguments])
        return self.run(command, timeout, input, cwd)

    def run(self, command, timeout=15, input=None, cwd=None):
        if self.name == "local":
            raise ValueError("Local commands require argument arrays; shell execution is not used")
        directory = str(cwd or self.root)

        if self.name == "ddev":
            argv = ["ddev", "exec", "--dir", directory, command]
        else:
            if not self.compose:
                raise ValueError("Compose runner selected but no Compose file found")
            argv = ["docker", "compose", "-f", self.compose, "exec", "-T", "-w", directory,
                    self.service, "sh", "-c", command]
        return execute(argv, self.project, timeout=timeout, input=input)

    def available(self):
        return True if self.name == "local" else self.exec(["true"])[0] == 0

    def command_available(self, name):
        if self.name == "local":
            return find_command(name) is not None
        return self.run("command -v " + shlex.quote(name))[0] == 0

    def exists(self, path, kind="file"):
        if self.name == "local":
            local = Path(path)

            if not local.is_absolute():
                local = self.project / local
            return local.is_dir() if kind == "dir" else local.exists() or local.is_symlink()
        flag = "-d" if kind == "dir" else "-e"
        quoted = shlex.quote(str(path))
        return self.run(f"test {flag} {quoted}" + (f" -o -L {quoted}" if kind != "dir" else ""))[0] == 0

    def sh(self, script, *args, input=None):
        status, stdout, stderr = self.exec(["sh", "-c", script, "sh", *map(str, args)], input=input)

        if status:
            raise ValueError(stderr.decode(errors="replace").strip() or "Runner operation failed")
        return stdout

    def read(self, path):
        if self.name == "local":
            return Path(path).read_bytes()
        status, stdout, stderr = self.exec(["sh", "-c", 'test -f "$1" && cat "$1"', "sh", str(path)])

        if status:
            raise OSError(stderr.decode(errors="replace") or f"Cannot read {path}")
        return stdout

    def write(self, path, content, append=False):
        if self.name == "local":
            with Path(path).open("ab" if append else "wb") as stream:
                stream.write(content)
        else:
            self.sh('cat >> "$1"' if append else 'cat > "$1"', path, input=content)

    def mkdir(self, path, parents=False):
        if self.name == "local":
            Path(path).mkdir(parents=parents, exist_ok=parents, mode=0o700)
        elif parents:
            self.sh('umask 077 && mkdir -p -- "$1"', path)
        else:
            self.sh('umask 077 && mkdir -- "$1"', path)

    def unlink(self, path):
        if self.name == "local":
            Path(path).unlink(missing_ok=True)
        else:
            self.sh('rm -f -- "$1"', path)

    def rmdir(self, path):
        if self.name == "local":
            Path(path).rmdir()
        else:
            self.sh('rmdir -- "$1"', path)

    def replace(self, source, target):
        if self.name == "local":
            Path(source).replace(target)
        else:
            self.sh('test ! -d "$2" && mv -f -- "$1" "$2"', source, target)

    def realpath(self, path):
        if self.name == "local":
            return str(Path(path).resolve())
        script = ('p=$1; tail=; while [ ! -e "$p" ] && [ ! -L "$p" ]; do b=$(basename -- "$p"); '
                  '[ "$b" = .. ] || [ "$b" = . ] && exit 1; tail=/$b$tail; n=$(dirname -- "$p"); '
                  '[ "$n" = "$p" ] && exit 1; p=$n; done; real=$(readlink -f -- "$p") && [ -n "$real" ] || exit 1; '
                  'printf "%s%s" "$real" "$tail"')
        return self.sh(script, path).decode().strip()
