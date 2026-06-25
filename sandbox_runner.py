from __future__ import annotations

import importlib
import inspect
import traceback
from dataclasses import dataclass, field
from time import perf_counter_ns
from typing import Any, Callable, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence


def _microseconds_from_ns(duration_ns: int) -> float:
    """Aero Future Docstring."""