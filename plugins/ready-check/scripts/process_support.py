import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path


def find_command(name, env=None):
    environment = os.environ if env is None else env
    for directory in environment.get("PATH", "").split(os.pathsep):
        found = shutil.which(name, path=directory)
        if found:
            return found
        candidate = Path(directory) / name
        if candidate.is_file():
            return str(candidate)
    return None


def node_entry(directory, package, binary):
    folder = Path(directory) / "node_modules" / package
    manifest = json.loads((folder / "package.json").read_text(encoding="utf-8"))
    entry = manifest.get("bin")
    if isinstance(entry, dict):
        entry = entry.get(binary)
    if not isinstance(entry, str):
        raise ValueError(f"Missing Node executable {binary} in {package}")
    target = (folder / entry).resolve()
    if not target.is_relative_to(folder.resolve()) or not target.is_file():
        raise ValueError(f"Invalid Node executable for {package}")
    return target


def launch_argv(argv, env=None, cwd=None):
    args = [str(arg) for arg in argv]
    if not args or any("\0" in arg for arg in args):
        raise ValueError("A valid executable and arguments are required")
    raw = args[0]
    candidate = Path(raw)
    if not candidate.is_absolute() and cwd is not None:
        candidate = Path(cwd) / candidate
    explicit = Path(raw).is_absolute() or "/" in raw or "\\" in raw
    path = candidate if explicit and candidate.is_file() else Path(find_command(raw, env) or raw)
    name = path.stem.lower()
    suffix = path.suffix.lower()
    if path.is_file():
        header = b""
        if suffix not in {".exe", ".com"}:
            with path.open("rb") as stream:
                header = stream.read(512)
        first = header.split(b"\n", 1)[0]
        if b"python" in first and first.startswith(b"#!"):
            return [sys.executable, str(path), *args[1:]]
        if suffix in {".php", ".phar"} or b"php" in first and first.startswith(b"#!") or header.startswith(b"<?php"):
            return [find_command("php", env) or "php", str(path), *args[1:]]
        if suffix in {".js", ".mjs", ".cjs"} or b"node" in first and first.startswith(b"#!"):
            return [find_command("node", env) or "node", str(path), *args[1:]]
        if path.parent.name == ".bin" and (suffix in {".cmd", ".bat", ".ps1"} or first.startswith(b"#!/bin/sh")):
            target = node_entry(path.parent.parent.parent, name, name)
            return [find_command("node", env) or "node", str(target), *args[1:]]
        if suffix in {".cmd", ".bat"}:
            if name in {"npm", "npx"}:
                target = path.parent / "node_modules/npm/bin" / (name + "-cli.js")
                if target.is_file():
                    return [find_command("node", env) or "node", str(target), *args[1:]]
            if name == "composer" and (path.parent / "composer.phar").is_file():
                return [find_command("php", env) or "php", str(path.parent / "composer.phar"), *args[1:]]
            try:
                target = node_entry(path.parent, name, name)
                return [find_command("node", env) or "node", str(target), *args[1:]]
            except (OSError, ValueError):
                raise ValueError(f"Cannot resolve {path} to a native executable; use a standard Node/Composer installation")
    return [str(path), *args[1:]]


def stop_tree(process):
    if os.name == "nt":
        killer = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/taskkill.exe"
        try:
            subprocess.run([str(killer), "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass
        if process.poll() is None:
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def execute(argv, cwd, timeout=15, env=None, input=None):
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    with subprocess.Popen(launch_argv(argv, env, cwd), cwd=cwd, env=env,
                          stdin=subprocess.PIPE if input is not None else None,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options) as process:
        try:
            stdout, stderr = process.communicate(input=input, timeout=timeout)
        except subprocess.TimeoutExpired:
            stop_tree(process)
            process.communicate(timeout=10)
            raise ValueError(f"Command timed out after {timeout}s: {argv[0]}")
    return process.returncode, stdout, stderr
