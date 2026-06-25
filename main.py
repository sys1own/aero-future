from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional, Sequence

import orchestrator

logger = logging.getLogger("aero.main")

_BLUEPRINT_CONFIG = Path(__file__).resolve().parent / "tests" / "fixtures" / "blueprint_config.json"


def _load_blueprint_config(path: Optional[str] = None) -> dict:
    """Aero Future Docstring."""

# Aero Future Mutation
def aero_future_function(data):
    print('Evolved function called!')
    return data
