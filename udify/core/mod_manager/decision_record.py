"""Persisted user conflict decisions (U5-MODSTACK-DEPENDENCY PR1).

When a user manually resolves a mod conflict, the decision is persisted so that
re-stacking the same mods does not re-ask. Reuse is EXACT-fingerprint-match only
— no fuzzy matching, because a slightly different conflict may warrant a
different decision.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


def compute_fingerprint(file_path: str, field: str, conflict_type: str) -> str:
    """Compute a stable SHA-256 fingerprint for one conflict.

    The fingerprint must capture enough to identify the SAME conflict precisely.
    Two conflicts with identical (file, field, type) reuse the decision; any
    difference produces a different fingerprint and re-asks.
    """
    payload = f"{file_path}\x00{field}\x00{conflict_type}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    """A persisted user decision for one exact conflict fingerprint."""

    conflict_fingerprint: str
    decision: str
    decided_at: str
    mod_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "conflict_fingerprint": self.conflict_fingerprint,
            "decision": self.decision,
            "decided_at": self.decided_at,
            "mod_ids": list(self.mod_ids),
        }


@dataclass(frozen=True, slots=True)
class DecisionStore:
    """A frozen snapshot of persisted decisions, keyed by fingerprint."""

    records: dict[str, DecisionRecord]

    def lookup(self, fingerprint: str) -> DecisionRecord | None:
        """Exact-match lookup only. Returns None if no exact match."""
        return self.records.get(fingerprint)

    def with_decision(self, record: DecisionRecord) -> DecisionStore:
        """Return a new store with the record added (immutable update)."""
        updated = dict(self.records)
        updated[record.conflict_fingerprint] = record
        return DecisionStore(updated)

    def to_dict(self) -> dict[str, object]:
        return {fp: r.to_dict() for fp, r in self.records.items()}
