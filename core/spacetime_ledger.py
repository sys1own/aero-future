"""Aero-Calculus spacetime tracking & verification layer.

This module implements *Block Universe* memory for the Aero-Calculus.  Every
HIN node is annotated with a logical spacetime coordinate
``X = (x, y, z, T_causal)`` where ``T_causal`` is an absolute counter pointing
directly at a transaction in the append-only ``context.aero`` ledger.  Past
records are *timeless*: once committed, a block (and the coordinate index it
froze) can never be rewritten.

Three pieces cooperate:

* :class:`CoordinateVector` -- arbitrary-precision (150-digit ``Decimal``)
  spacetime vectors.  64-bit floats collapse at the ``1/N ≈ 10⁻¹²²``
  cosmological noise floor, so all arithmetic is carried in high precision.
* :class:`BlockUniverseLedger` -- a read/write, hash-chained driver for
  ``context.aero`` that records every graph mutation, compile metric and
  performance parameter chronologically.
* :class:`RigidityVerifier` -- runs coordinate-perturbation sweeps over module
  boundaries and checks, via the ``(26, 8, 312)`` kernel model, that boundary
  eigenvalues persist as rigid invariants under transport.  A drift past the
  noise floor raises :class:`AnomalyClosureError`.
"""

from __future__ import annotations

from decimal import Decimal, getcontext, localcontext
from types import MappingProxyType
from typing import Dict, List, Optional, Sequence
import hashlib
import json
import os
import time

# Global decimal precision supporting 512-bit cosmological precision.
# 150 decimal digits comfortably covers the 1/N ≈ 10⁻¹²² noise floor.
getcontext().prec = 150

# Working precision for the eigen/transport kernels (extra guard digits).
_WORK_PREC = 180


class AnomalyClosureError(Exception):
    """Raised when coordinate sweeps detect a geometric/algebraic violation."""


class FrozenCoordinateError(Exception):
    """Raised when mutating a frozen (committed) spacetime record.

    Enforces the timeless nature of the Block Universe: past coordinate
    indices and ledger blocks are immutable once written.
    """


# ---------------------------------------------------------------------------
# Coordinate vector
# ---------------------------------------------------------------------------
class CoordinateVector:
    """High-precision spacetime vector ``X = (x, y, z, T_causal)``.

    Spatial components are :class:`~decimal.Decimal` (150-digit precision);
    ``t_causal`` is an integer index into the ``context.aero`` transaction
    sequence.  Once :meth:`freeze` is called the vector is immutable -- any
    attempt to rebind ``x``, ``y``, ``z`` or ``t_causal`` raises
    :class:`FrozenCoordinateError`.
    """

    _GUARDED = ("x", "y", "z", "t_causal")

    def __init__(self, x: str, y: str, z: str, t_causal: int):
        self.x = Decimal(str(x))
        self.y = Decimal(str(y))
        self.z = Decimal(str(z))
        self.t_causal = int(t_causal)

    def __setattr__(self, name: str, value) -> None:
        if getattr(self, "_frozen", False) and name in self._GUARDED:
            raise FrozenCoordinateError(
                f"cannot mutate frozen spacetime coordinate '{name}' "
                f"at T_causal={getattr(self, 't_causal', '?')}"
            )
        object.__setattr__(self, name, value)

    # -- lifecycle ---------------------------------------------------------
    def freeze(self) -> "CoordinateVector":
        """Seal this coordinate against further mutation (block becomes past)."""
        object.__setattr__(self, "_frozen", True)
        return self

    @property
    def frozen(self) -> bool:
        return getattr(self, "_frozen", False)

    # -- algebra -----------------------------------------------------------
    def distance_to(self, other: "CoordinateVector") -> Decimal:
        with localcontext() as ctx:
            ctx.prec = _WORK_PREC
            return (
                (self.x - other.x) ** 2
                + (self.y - other.y) ** 2
                + (self.z - other.z) ** 2
            ).sqrt()

    def translate(self, dx: Decimal, dy: Decimal, dz: Decimal) -> "CoordinateVector":
        """Return a new, unfrozen coordinate transported by ``(dx, dy, dz)``."""
        return CoordinateVector(
            str(self.x + Decimal(dx)),
            str(self.y + Decimal(dy)),
            str(self.z + Decimal(dz)),
            self.t_causal,
        )

    def is_finite(self) -> bool:
        return all(c.is_finite() for c in (self.x, self.y, self.z))

    def as_tuple(self):
        return (self.x, self.y, self.z, self.t_causal)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CoordinateVector):
            return NotImplemented
        return self.as_tuple() == other.as_tuple()

    def __repr__(self) -> str:
        return f"X(x={self.x}, y={self.y}, z={self.z}, T={self.t_causal})"


# ---------------------------------------------------------------------------
# Block Universe ledger
# ---------------------------------------------------------------------------
class BlockUniverseLedger:
    """Append-only, hash-chained driver for the ``context.aero`` ledger.

    Stores every graph mutation, compile metric and performance parameter
    chronologically.  Each block is linked to its predecessor by a SHA-256
    hash chain, so any tampering with a past record is detectable and direct
    mutation is refused (the records are *timeless*).
    """

    CHAIN_KEY = "ledger"

    def __init__(self, file_path: str = "context.aero"):
        self.file_path = file_path
        if not os.path.exists(self.file_path):
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {self.CHAIN_KEY: [], "version": "aero_calculus_v1"}
                    )
                    + "\n"
                )
        self._data = self._load()
        # Per-node coordinate annotations (node_id -> CoordinateVector).
        self.annotations: Dict[str, CoordinateVector] = {}

    # -- persistence -------------------------------------------------------
    def _load(self) -> dict:
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {self.CHAIN_KEY: [], "version": "aero_calculus_v1"}
        # Interoperate with an existing evolve-style ledger.
        if self.CHAIN_KEY not in data and "mutation_history" in data:
            self.CHAIN_KEY = "mutation_history"
        data.setdefault(self.CHAIN_KEY, [])
        return data

    def _persist(self) -> None:
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    @property
    def _chain(self) -> List[dict]:
        return self._data[self.CHAIN_KEY]

    # -- hashing -----------------------------------------------------------
    @staticmethod
    def _hash_block(prev_hash: str, index: int, payload: dict) -> str:
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(
            f"{prev_hash}|{index}|{canonical}".encode("utf-8")
        ).hexdigest()

    # -- read/write --------------------------------------------------------
    def append_transaction(self, tx_data: dict) -> int:
        """Append a cryptographically traceable block; return its ``T_causal``.

        The returned index *is* ``T_causal`` -- the absolute position of the
        transaction in the chronological sequence.
        """
        index = len(self._chain)
        prev_hash = self._chain[-1]["block_hash"] if self._chain else ""
        block = {
            "t_causal": index,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "prev_hash": prev_hash,
            "payload": tx_data,
        }
        block["block_hash"] = self._hash_block(prev_hash, index, tx_data)
        self._chain.append(block)
        self._persist()
        return index

    def annotate_node(
        self, node, coordinate: CoordinateVector, metric: Optional[dict] = None
    ) -> int:
        """Annotate a HIN node with a coordinate and record the mutation.

        The coordinate's ``T_causal`` is bound to the freshly committed block
        and the coordinate is then frozen -- it has become part of the past.
        Returns the assigned ``T_causal``.
        """
        node_id = getattr(node, "node_id", node)
        index = self.append_transaction(
            {
                "kind": "graph_mutation",
                "node_id": node_id,
                "coordinate": [str(coordinate.x), str(coordinate.y), str(coordinate.z)],
                "metric": metric or {},
            }
        )
        object.__setattr__(coordinate, "t_causal", index)
        coordinate.freeze()
        self.annotations[node_id] = coordinate
        if hasattr(node, "node_id"):
            setattr(node, "coordinate", coordinate)
        return index

    def get_transaction(self, t_causal: int) -> MappingProxyType:
        """Return an immutable read-only view of a committed block."""
        if t_causal < 0 or t_causal >= len(self._chain):
            raise IndexError(f"no transaction at T_causal={t_causal}")
        return MappingProxyType(dict(self._chain[t_causal]))

    def __len__(self) -> int:
        return len(self._chain)

    # -- immutability guard ------------------------------------------------
    def overwrite_transaction(self, t_causal: int, tx_data: dict) -> None:
        """Refuse to rewrite a committed block (timeless past).

        Raises:
            FrozenCoordinateError: always, for any already-committed index.
        """
        if 0 <= t_causal < len(self._chain):
            raise FrozenCoordinateError(
                f"transaction T_causal={t_causal} is frozen in the block "
                f"universe and cannot be overwritten"
            )
        raise IndexError(f"no transaction at T_causal={t_causal}")

    # -- integrity ---------------------------------------------------------
    def verify_integrity(self) -> bool:
        """Verify the hash chain links each block to its predecessor."""
        prev_hash = ""
        for index, block in enumerate(self._chain):
            if block.get("prev_hash", "") != prev_hash:
                return False
            recomputed = self._hash_block(
                prev_hash, block.get("t_causal", index), block.get("payload", {})
            )
            if block.get("block_hash") != recomputed:
                return False
            prev_hash = block["block_hash"]
        return True


# ---------------------------------------------------------------------------
# Rigidity verifier
# ---------------------------------------------------------------------------
class RigidityVerifier:
    """Coordinate-perturbation sweeps enforcing boundary algebraic rigidity."""

    def __init__(self):
        # The (26, 8, 312) Kernel constants as high-precision decimals.
        self.kernel_dimension = 26
        self.kernel_model = (26, 8, 312)
        self.rigidity_eigenvalue = Decimal("8.312")
        # Algebraic noise floor: 1/N ≈ 10⁻¹²².
        self.noise_floor = Decimal(10) ** (-122)
        # Perturbation displacement ΔX just above the floor.
        self.delta = Decimal(10) ** (-120)
        self.max_boundary = 8  # the kernel's 8-fold boundary multiplicity

    # -- public API --------------------------------------------------------
    def verify_boundary(self, boundary_ports: list) -> bool:
        """Run a perturbation sweep over a module boundary.

        Builds a transport (distance) matrix from the boundary coordinates,
        computes its eigenvalues, applies a rigid transport displacement
        ``ΔX`` and recomputes them.  A rigid boundary is translation-invariant,
        so its eigenvalues must persist to within the noise floor.  Any drift
        beyond the floor -- or a collapsed/non-finite boundary -- signals that
        a structural anomaly has infected the graph topology.

        Raises:
            AnomalyClosureError: if rigidity is violated.
        """
        coords = self._extract_coords(boundary_ports)
        if len(coords) < 2:
            return True  # trivially rigid

        for c in coords:
            if not c.is_finite():
                raise AnomalyClosureError(
                    "Boundary coordinate is non-finite; topology corrupted."
                )

        with localcontext() as ctx:
            ctx.prec = _WORK_PREC

            base_matrix = self._transport_matrix(coords)
            base_eigs = self._eigenvalues(base_matrix)

            # A collapsed boundary (zero spatial extent) is a structural
            # anomaly: every eigenvalue vanishes.
            if all(abs(v) <= self.noise_floor for v in base_eigs):
                raise AnomalyClosureError(
                    "Boundary collapsed to a point; algebraic rigidity absent."
                )

            # Rigid transport: translate the whole boundary by ΔX.
            moved = [c.translate(self.delta, self.delta, self.delta) for c in coords]
            moved_matrix = self._transport_matrix(moved)
            moved_eigs = self._eigenvalues(moved_matrix)

            drift = self._spectral_drift(base_eigs, moved_eigs)
            if drift > self.noise_floor:
                raise AnomalyClosureError(
                    "Boundary algebraic rigidity shattered during perturbation "
                    f"sweep (drift={drift:.3e} > floor={self.noise_floor:.3e})."
                )

        return True

    # -- transport matrices ------------------------------------------------
    @staticmethod
    def _transport_matrix(coords: Sequence[CoordinateVector]) -> List[List[Decimal]]:
        n = len(coords)
        matrix = [[Decimal(0)] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                d = coords[i].distance_to(coords[j])
                matrix[i][j] = d
                matrix[j][i] = d
        return matrix

    @staticmethod
    def _spectral_drift(a: List[Decimal], b: List[Decimal]) -> Decimal:
        sa = sorted(a)
        sb = sorted(b)
        return max((abs(x - y) for x, y in zip(sa, sb)), default=Decimal(0))

    # -- high-precision symmetric eigensolver (Jacobi) ---------------------
    def _eigenvalues(self, matrix: List[List[Decimal]]) -> List[Decimal]:
        """Eigenvalues of a symmetric matrix via the Jacobi rotation method.

        Pure-``Decimal`` arithmetic keeps the full 150+ digit precision that a
        float64 eigensolver would shred at cosmological scale.
        """
        n = len(matrix)
        a = [row[:] for row in matrix]
        if n == 1:
            return [a[0][0]]

        threshold = Decimal(10) ** (-(_WORK_PREC - 20))
        for _ in range(100 * n):
            # Largest off-diagonal magnitude and its position.
            p, q, off = 0, 1, Decimal(-1)
            for i in range(n):
                for j in range(i + 1, n):
                    m = abs(a[i][j])
                    if m > off:
                        off, p, q = m, i, j
            if off <= threshold:
                break

            app, aqq, apq = a[p][p], a[q][q], a[p][q]
            if app == aqq:
                t = Decimal(1) if apq > 0 else Decimal(-1)
            else:
                phi = (aqq - app) / (2 * apq)
                sign = Decimal(1) if phi >= 0 else Decimal(-1)
                t = sign / (abs(phi) + (phi * phi + 1).sqrt())
            c = 1 / (t * t + 1).sqrt()
            s = t * c

            # Apply the Jacobi rotation J^T A J in place.
            for k in range(n):
                akp, akq = a[k][p], a[k][q]
                a[k][p] = c * akp - s * akq
                a[k][q] = s * akp + c * akq
            for k in range(n):
                apk, aqk = a[p][k], a[q][k]
                a[p][k] = c * apk - s * aqk
                a[q][k] = s * apk + c * aqk

        return [a[i][i] for i in range(n)]

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _extract_coords(boundary_ports: list) -> List[CoordinateVector]:
        coords: List[CoordinateVector] = []
        for item in boundary_ports:
            if isinstance(item, CoordinateVector):
                coords.append(item)
            elif hasattr(item, "coordinate") and isinstance(
                item.coordinate, CoordinateVector
            ):
                coords.append(item.coordinate)
            elif isinstance(item, dict) and "coordinate" in item:
                c = item["coordinate"]
                coords.append(
                    c if isinstance(c, CoordinateVector) else CoordinateVector(*c)
                )
        return coords


__all__ = [
    "AnomalyClosureError",
    "FrozenCoordinateError",
    "CoordinateVector",
    "BlockUniverseLedger",
    "RigidityVerifier",
]
