                               -*- Buildmacs -*-

TLDR:

  A minimal setup for making static builds of Emacs for macOS. Mostly for
  personal use; certainly not battle-tested.

Usage:

  $ buildmacs deps      # download & build dependencies (must run first)
  $ buildmacs app       # build a full Emacs.app
  $ buildmacs terminal  # build a terminal-only Emacs, no app bundle
  $ buildmacs clean     # clean workspace

  $ buildmacs --help    # for more info

References:

  - https://github.com/hanwenguo/emacs-ns-static-build
  - https://github.com/RadioNoiseE/ebuild

Disclaimer:

  Initially ported to Python with LLMs, cleaned up (somewhat) by hand after.
