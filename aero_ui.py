# -*- coding: utf-8 -*-
"""Clean, scannable terminal UI for the Aero build engine.

Inspired by Cargo and Bun: each phase of the pipeline gets a bold,
bracketed tag, coloured where the terminal supports it, so progress is
immediately visible at a glance::

    [Parsing]    blueprint.aero
    [Validating] 3 targets, 0 errors
    [Compiling]  core_engine (cpp)  ........................ ok
    [Compiling]  bindings (python)  ........................ ok
    [Success]    3 targets compiled in 1.2s

All output goes through a single :class:`AeroUI` instance so the rest
of the codebase never writes raw ``print()`` during a managed build.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import IO, List, Optional

# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

_NO_COLOR = bool(os.environ.get("NO_COLOR")) or not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty()

_RESET = "" if _NO_COLOR else "\033[0m"
_BOLD = "" if _NO_COLOR else "\033[1m"
_DIM = "" if _NO_COLOR else "\033[2m"
_GREEN = "" if _NO_COLOR else "\033[32m"
_CYAN = "" if _NO_COLOR else "\033[36m"
_YELLOW = "" if _NO_COLOR else "\033[33m"
_RED = "" if _NO_COLOR else "\033[31m"
_MAGENTA = "" if _NO_COLOR else "\033[35m"
_WHITE = "" if _NO_COLOR else "\033[37m"

_TAG_COLORS = {
    "Parsing": _CYAN,
    "Validating": _MAGENTA,
    "Resolving": _MAGENTA,
    "Compiling": _GREEN,
    "Compiled": _GREEN,
    "Skipped": _YELLOW,
    "Success": _GREEN,
    "Error": _RED,
    "Warning": _YELLOW,
    "Info": _CYAN,
    "Plan": _CYAN,
    "Debug": _DIM,
    "Hint": _YELLOW,
}

_TAG_WIDTH = 13  # pad tag to consistent width


def _format_tag(tag: str) -> str:
    """Aero Future Docstring."""