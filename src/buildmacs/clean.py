from pathlib import Path

from .common import die, log, remove_path


def clean_workspace(workspace: Path, deep: bool) -> None:
    workspace = workspace.expanduser().resolve()
    if not workspace.exists():
        die(f"Workspace does not exist: {workspace}")

    for name in ("prefix", "out", "dist"):
        remove_path(workspace / name)

    source_root = workspace / "src"

    if deep:
        remove_path(source_root)
    elif source_root.is_dir() and not source_root.is_symlink():
        for path in source_root.iterdir():
            if path.is_dir():
                remove_path(path)
            else:
                pass  # This leaves the tarballs alone.

    log("Workspace cleaned.")
