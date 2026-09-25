import re
from pathlib import Path

from .common import die


def fix_ncurses_darwin(source: Path) -> None:
    configure_ac = source / "configure.ac"
    original = configure_ac.read_text()
    updated = "".join(
        re.sub(r"lncurses(?!w)", "lncursesw", line) if "darwin" in line else line
        for line in original.splitlines(keepends=True)
    )
    if updated != original:
        configure_ac.write_text(updated)


def apply_relocatable_patch(source: Path) -> None:
    callproc = source / "src/callproc.c"

    original = callproc.read_text()
    if "#ifdef BUILDMACS_RELOCATABLE_TERMINAL\n" in original:
        return

    needle = "  /* Look for the files that should be in etc.  We don't use\n"
    if needle not in original:
        die("Could not patch Emacs terminal data directory lookup")

    patch = """#ifdef BUILDMACS_RELOCATABLE_TERMINAL
  /* The terminal archive keeps its data beside the executable tree.  */
  if (!data_dir && !NILP (Vinstallation_directory))
    {
      Lisp_Object etcdir = Fexpand_file_name (build_string ("etc"),
                                               Vinstallation_directory);
      if (!NILP (Ffile_exists_p (Fexpand_file_name (build_string ("NEWS"),
                                                  etcdir))))
        {
          Vdata_directory = Ffile_name_as_directory (etcdir);
          Vconfigure_info_directory =
            Fexpand_file_name (build_string ("info"),
                                Vinstallation_directory);
          data_dir = true;
        }
    }
#endif

"""
    callproc.write_text(original.replace(needle, patch + needle, 1))
