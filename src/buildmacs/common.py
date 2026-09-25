import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn


def run_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        capture_output=capture_output,
        text=True,
    )


def log(message: str) -> None:
    line = f"==> {message}"

    if sys.stdout.isatty():
        line = f"\033[32m{line}\033[0m"

    print(line, flush=True)


def die(message: str) -> NoReturn:
    line = f"==> {message}"

    if sys.stderr.isatty():
        line = f"\033[31m{line}\033[0m"

    print(line, file=sys.stderr, flush=True)
    sys.exit(1)


def remove_path(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        path.unlink(missing_ok=True)
    else:
        shutil.rmtree(path)
