import os
from argparse import ArgumentParser
from pathlib import Path
from time import perf_counter

from .app import BuildOptions, build_app, build_terminal
from .clean import clean_workspace
from .common import log
from .deps import build_deps


def add_workspace_option(command: ArgumentParser) -> None:
    command.add_argument(
        "-w",
        "--workspace",
        type=Path,
        metavar="DIR",
        default=Path("buildmacs-work"),
        help="workspace directory (default: './buildmacs-work')",
    )


def add_macos_target_option(command: ArgumentParser) -> None:
    command.add_argument(
        "--macos-target",
        metavar="VERSION",
        help="minimum macOS version to support",
    )


def add_build_options(command: ArgumentParser, default_jobs: int) -> None:
    add_workspace_option(command)
    add_macos_target_option(command)
    command.add_argument(
        "--jobs",
        type=int,
        default=default_jobs,
        help=f"parallel make job limit (default: {default_jobs})",
    )
    command.add_argument(
        "--branch", default="emacs-31", help="Emacs branch (default: emacs-31)"
    )


def main(argv: list[str] | None = None) -> None:
    default_jobs = max(1, min((os.cpu_count() or 1) - 1, 8))

    parser = ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    deps_cmd = commands.add_parser("deps", help="download and build dependencies")
    add_workspace_option(deps_cmd)
    add_macos_target_option(deps_cmd)
    deps_cmd.add_argument(
        "--jobs",
        type=int,
        default=default_jobs,
        help=f"parallel make job limit (default: {default_jobs})",
    )
    deps_cmd.add_argument(
        "--dl-jobs",
        type=int,
        default=4,
        help="parallel tarball download limit (default: 4)",
    )

    app_cmd = commands.add_parser("app", help="build Emacs (app bundle)")
    add_build_options(app_cmd, default_jobs)

    terminal_cmd = commands.add_parser("terminal", help="build Emacs (terminal-only)")
    add_build_options(terminal_cmd, default_jobs)

    clean_cmd = commands.add_parser("clean", help="remove workspace build outputs")
    add_workspace_option(clean_cmd)
    clean_cmd.add_argument(
        "--deep",
        action="store_true",
        help="also remove downloaded tarballs and the src/ directory",
    )

    args = parser.parse_args(argv)

    started = perf_counter()

    if args.command == "deps":
        build_deps(args.workspace, args.jobs, args.dl_jobs, args.macos_target)
    elif args.command == "clean":
        clean_workspace(args.workspace, args.deep)
    else:
        options = BuildOptions(
            args.workspace, args.jobs, args.branch, args.macos_target
        )
        if args.command == "app":
            build_app(options)
        else:
            build_terminal(options)

    log(f"Finished in {perf_counter() - started:.1f}s.")
