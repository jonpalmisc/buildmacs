import os
import re
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from .common import die, log, remove_path, run_command
from .deps import ensure_deps_present
from .patch import apply_relocatable_patch, fix_ncurses_darwin


@dataclass(frozen=True, slots=True)
class BuildOptions:
    workspace: Path
    jobs: int
    branch: str
    macos_target: str | None = None


EMACS_REPO = "https://github.com/emacs-mirror/emacs.git"

COMMON_CONFIGURE_FLAGS = (
    "--disable-gc-mark-trace",
    "--enable-link-time-optimization",
    "--without-all",
    "--with-file-notification=kqueue",
    "--with-modules",
    "--with-small-ja-dic",
    "--with-threads",
    "--with-xml2",
    "--with-zlib",
)
APP_CONFIGURE_FLAGS = (
    *COMMON_CONFIGURE_FLAGS,
    "--with-native-image-api",
    "--with-ns",
    "--with-toolkit-scroll-bars",
)
TERMINAL_CONFIGURE_FLAGS = (
    *COMMON_CONFIGURE_FLAGS,
    "--enable-locallisppath=no",
    "--without-ns",
)


def run_output(command: list[str], cwd: Path) -> str:
    return run_command(command, cwd=cwd, capture_output=True).stdout.strip()


def prep_emacs_source(source: Path, branch: str) -> None:
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)

        log(f"Cloning Emacs... ({branch})")
        run_command(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--branch",
                branch,
                EMACS_REPO,
                str(source),
            ],
        )
        return

    if not (source / ".git").exists():
        die(f"Emacs source path is not a Git checkout: {source}")

    current_branch = run_output(["git", "branch", "--show-current"], source)
    if current_branch != branch:
        die(
            f"Emacs checkout is on {current_branch or 'a detached HEAD'}, "
            f"not {branch}; "
            "switch branches or replace the checkout manually."
        )
    log(f"Using existing Emacs checkout @ '{branch}'.")


def emacs_build_env(
    prefix: Path, deployment_target: str | None = None
) -> dict[str, str]:
    env = os.environ.copy()

    env["PATH"] = f"{prefix / 'bin'}:{env.get('PATH', '')}"
    pkgconfig_dirs = f"{prefix / 'lib/pkgconfig'}:{prefix / 'share/pkgconfig'}"
    env["PKG_CONFIG_PATH"] = pkgconfig_dirs
    env["PKG_CONFIG_LIBDIR"] = pkgconfig_dirs
    env["CPPFLAGS"] = f"-I{prefix / 'include'}"
    env["LDFLAGS"] = f"-L{prefix / 'lib'}"
    env["CC"] = "/usr/bin/clang"
    env["CXX"] = "/usr/bin/clang++"
    env["OBJC"] = "/usr/bin/clang"
    env["OBJCXX"] = "/usr/bin/clang++"
    env["PKG_CONFIG"] = "pkg-config --static"

    if deployment_target is not None:
        env["MACOSX_DEPLOYMENT_TARGET"] = deployment_target

    return env


def build_emacs(
    options: BuildOptions, terminal: bool
) -> tuple[Path, Path, Path, dict[str, str]]:
    workspace = options.workspace.expanduser().resolve()
    prefix = workspace / "prefix"
    source = workspace / "src/emacs"
    out = workspace / "out"
    if out.is_symlink():
        die(f"Output path must not be a symlink: {out}")

    ensure_deps_present(prefix)

    env = emacs_build_env(prefix, options.macos_target)
    prep_emacs_source(source, options.branch)
    run = partial(run_command, cwd=source, env=env)

    if (source / "Makefile").is_file():
        log("Cleaning previous Emacs build...")
        run(["make", "clean"])

    fix_ncurses_darwin(source)
    if terminal:
        apply_relocatable_patch(source)
        env["CPPFLAGS"] += " -DBUILDMACS_RELOCATABLE_TERMINAL"

    configure_flags = TERMINAL_CONFIGURE_FLAGS if terminal else APP_CONFIGURE_FLAGS
    log("Generating Emacs configure script...")
    run(["./autogen.sh"])

    log("Configuring Emacs...")
    try:
        run(["./configure", *configure_flags, f"--prefix={out}"])
    except subprocess.CalledProcessError:
        config_log = source / "config.log"
        if config_log.is_file():
            print(
                "\n".join(config_log.read_text(errors="replace").splitlines()[-200:]),
                file=sys.stderr,
            )

        die("Failed to configure Emacs build.")

    log("Building Emacs...")
    run(["make", f"-j{options.jobs}"])
    return workspace, source, out, env


def emacs_version(binary: Path, workspace: Path) -> str:
    version_output = run_output([str(binary), "--version"], workspace)
    version_match = re.match(r"GNU Emacs ([0-9]+(?:\.[0-9]+)*)", version_output)
    if version_match is None:
        die(f"Could not determine Emacs version from: {version_output!r}")

    return version_match[1]


def install_terminal_layout(out: Path, version: str) -> None:
    dumps = list((out / "libexec" / "emacs" / version).glob("*/*.pdmp"))
    if len(dumps) != 1:
        die(f"Expected one Emacs dump file, found {len(dumps)}")

    dump = dumps[0].relative_to(out)
    (out / "etc").symlink_to(f"share/emacs/{version}/etc", target_is_directory=True)
    (out / "lisp").symlink_to(f"share/emacs/{version}/lisp", target_is_directory=True)
    (out / "lib-src").symlink_to(dump.parent, target_is_directory=True)
    (out / "info").symlink_to("share/info", target_is_directory=True)
    (out / "bin" / f"emacs-{version}.pdmp").symlink_to(Path("..") / dump)


def build_app(options: BuildOptions) -> None:
    workspace, source, out, env = build_emacs(options, terminal=False)
    app = out / "Emacs.app"
    out.mkdir(parents=True, exist_ok=True)
    run_command(["make", "install"], cwd=source, env=env)

    log("Packaging Emacs.app...")
    remove_path(app)
    run_command(["ditto", str(source / "nextstep/Emacs.app"), str(app)])

    version = emacs_version(app / "Contents/MacOS/Emacs", workspace)
    commit = run_output(["git", "rev-parse", "--short", "HEAD"], source)

    dist = workspace / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    archive = dist / f"Emacs-{version}-{commit}.tar.xz"
    temporary = archive.with_name(archive.name + ".part")
    try:
        run_command(["tar", "-Jcf", str(temporary), "Emacs.app"], cwd=out)
        temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)

    log(f"Created archive: {archive}")


def build_terminal(options: BuildOptions) -> None:
    workspace, source, out, env = build_emacs(options, terminal=True)
    out.mkdir(parents=True, exist_ok=True)
    for path in out.iterdir():
        if path.name != "Emacs.app":
            remove_path(path)

    run_command(["make", "install"], cwd=source, env=env)

    version = emacs_version(out / "bin/emacs", workspace)
    install_terminal_layout(out, version)
    commit = run_output(["git", "rev-parse", "--short", "HEAD"], source)
    name = f"temacs-{version}-{commit}"
    dist = workspace / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    archive = dist / f"{name}.tar.xz"
    temporary = archive.with_name(archive.name + ".part")
    try:
        with tarfile.open(temporary, "w:xz") as output:
            output.add(out, arcname=name, recursive=False)
            for path in out.iterdir():
                if path.name != "Emacs.app":
                    output.add(path, arcname=f"{name}/{path.name}")
        temporary.replace(archive)
    finally:
        temporary.unlink(missing_ok=True)

    log(f"Created archive: {archive}")
