# -*- coding: utf-8 -*-
"""Map ``blueprint.aero`` target blocks to an internal DAG and resolve build order.

The module bridges two worlds:

* **blueprint_lang** -- the block-DSL parser that yields a validated
  :class:`~blueprint_lang.nodes.Blueprint` AST with ``target`` blocks and
  ``requires`` dependency arrays.
* **The orchestrator's DAG** -- a flat ``{name: [deps]}`` dependency matrix
  consumed by the existing build engine.

Public API
----------
* :func:`blueprint_to_dag` -- convert a :class:`Blueprint` into a
  :class:`BuildGraph`.
* :class:`BuildGraph` -- holds the resolved topological order and can
  render a clean, minimalist visual tree of the planned build steps.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from blueprint_lang.nodes import Blueprint, ListValue, StringValue


@dataclass
class TargetNode:
    """A single build target extracted from the blueprint AST."""

    name: str
    language: str
    sources: List[str]
    requires: List[str]
    flags: List[str] = field(default_factory=list)
    defines: List[str] = field(default_factory=list)
    output: Optional[str] = None
    optional: bool = False
    # Rust/Cargo: point at a crate in a subdirectory and/or an explicit manifest.
    manifest_path: Optional[str] = None
    root: Optional[str] = None
    # Pin dependency versions for a synthesised manifest ("name=version" entries).
    cargo_dependencies: List[str] = field(default_factory=list)
    # RUSTFLAGS control: an optimization word and/or explicit rustflags.
    optimization: Optional[str] = None
    rustflags: List[str] = field(default_factory=list)
    # Polyglot emitter: translate UAST into this language instead of compiling.
    target_output_language: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Aero Future Docstring."""