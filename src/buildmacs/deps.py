import os
import tarfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen

from .common import die, log, run_command


@dataclass(frozen=True, slots=True)
class Dependency:
    url: str
    configure_flags: tuple[str, ...] = ()

    @property
    def archive_name(self) -> str:
        return Path(urlsplit(self.url).path).name

    @property
    def source_dir(self) -> str:
        return self.archive_name.removesuffix(".tar.gz").removesuffix(".tar.xz")

    def prepare_source(self, src_dir: Path) -> None:
        archive = src_dir / self.archive_name
        download(self.url, archive)

        with tarfile.open(archive) as source:
            source.extractall(src_dir, filter="data")

    def build(
        self, prefix: Path, src_dir: Path, jobs: int, env: dict[str, str]
    ) -> None:
        source = src_dir / self.source_dir

        # Unfortunate special-case.
        build_env = env.copy()
        if self.source_dir.startswith("ncurses-"):
            for variable in ("TERMINFO", "TERMINFO_DIRS", "TERMCAP", "TERMPATH"):
                build_env.pop(variable, None)

        run = partial(run_command, cwd=source, env=build_env)

        if (source / "Makefile").is_file():
            run(["make", "distclean"])

        run(["./configure", f"--prefix={prefix}", *self.configure_flags])
        run(["make", f"-j{jobs}"])
        run(["make", "install"])


DEPENDENCIES = (
    Dependency(
        "https://ftpmirror.gnu.org/gnu/libiconv/libiconv-1.19.tar.gz",
        ("--disable-shared",),
    ),
    Dependency(
        "https://ftpmirror.gnu.org/gnu/ncurses/ncurses-6.6.tar.gz",
        (
            "--disable-shared",
            "--disable-db-install",
            "--with-default-terminfo-dir=/usr/share/terminfo",
            "--with-terminfo-dirs=/usr/share/terminfo",
        ),
    ),
    Dependency(
        "https://download.gnome.org/sources/libxml2/2.15/libxml2-2.15.3.tar.xz",
        ("--disable-shared",),
    ),
)

GNU_MIRROR_BASE = "https://ftpmirror.gnu.org/gnu/"
KERNEL_MIRROR_BASE = "https://mirrors.kernel.org/gnu/"


def download(url: str, dest: Path) -> None:
    if dest.is_file():
        return

    urls = (url,)
    if url.startswith(GNU_MIRROR_BASE):
        # The GNU URLs are (unsurprisingly) pretty unreliable.
        urls += (url.replace(GNU_MIRROR_BASE, KERNEL_MIRROR_BASE, 1),)

    temporary = dest.with_name(dest.name + ".part")
    for source_url in urls:
        try:
            with (
                urlopen(source_url, timeout=30) as response,
                temporary.open("wb") as output,
            ):
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)

            temporary.replace(dest)
            return
        except OSError:
            temporary.unlink(missing_ok=True)
            if source_url == urls[-1]:
                die(f"Download failed: {', '.join(urls)}")

            log(f"Download failed: {source_url} (will try next mirror)")


def ensure_deps_present(prefix: Path) -> None:
    missing = [
        dependency.source_dir
        for dependency in DEPENDENCIES
        if not (prefix / ".depflags" / dependency.source_dir).is_file()
    ]
    if missing:
        die(f"Missing dependencies: {', '.join(missing)} (run 'buildmacs deps' first)")


def build_deps(
    workspace: Path, jobs: int, dl_jobs: int, macos_target: str | None = None
) -> None:
    workspace = workspace.expanduser().resolve()
    prefix = workspace / "prefix"
    src_dir = workspace / "src"
    markers = prefix / ".depflags"

    pending = [dep for dep in DEPENDENCIES if not (markers / dep.source_dir).is_file()]
    if not pending:
        log("All dependencies already built.")
        return

    markers.mkdir(parents=True, exist_ok=True)
    src_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PATH"] = f"{prefix / 'bin'}:{env.get('PATH', '')}"
    env["PKG_CONFIG_PATH"] = f"{prefix / 'lib/pkgconfig'}:{prefix / 'share/pkgconfig'}"
    env["CPPFLAGS"] = f"-I{prefix / 'include'}"
    env["LDFLAGS"] = f"-L{prefix / 'lib'}"

    if macos_target is not None:
        env["MACOSX_DEPLOYMENT_TARGET"] = macos_target

    log("Downloading dependencies...")

    with ThreadPoolExecutor(max_workers=dl_jobs) as executor:
        futures = {
            executor.submit(dependency.prepare_source, src_dir): dependency
            for dependency in pending
        }
        for number, future in enumerate(as_completed(futures), start=1):
            future.result()
            log(f"({number}/{len(futures)}) {futures[future].source_dir}")

    log(f"Building {len(pending)} dependencies...")
    for dependency in pending:
        log(f"Building: {dependency.source_dir}")
        dependency.build(prefix, src_dir, jobs, env)

        (markers / dependency.source_dir).touch()
