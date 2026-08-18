"""Immutable contracts for deterministic content-graph reference resolution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from udify.models.content_graph import NodeType

type ScalarValue = str | int | float | bool | None


class ReferenceOperator(StrEnum):
    """Supported deterministic reference operations."""

    ORDINAL = "ordinal"
    SUPERLATIVE = "superlative"
    SPATIAL = "spatial"
    ID = "id"


class OrderDomain(StrEnum):
    """Explicit ordering domains available to ordinal resolution."""

    DB_INDEX = "db_index"
    TROOP_MEMBER = "troop_member"
    FIRST_ENCOUNTER = "first_encounter"
    SPATIAL = "spatial"


class ClarificationReason(StrEnum):
    """Stable reasons why deterministic resolution needs user input."""

    AMBIGUOUS_ORDINAL = "ambiguous_ordinal"
    MISSING_ORDER_DOMAIN = "missing_order_domain"
    MULTI_SUPERLATIVE_TIE = "multi_superlative_tie"
    NO_CANDIDATES = "no_candidates"


@dataclass(frozen=True, slots=True)
class ReferenceSpec:
    """Describe one deterministic reference-resolution operation.

    Attributes:
        operator: Resolution operator to apply after candidate filtering.
        semantic_filters: Exact-match semantic constraints such as
            ``("is_boss", True)``.
        node_type: Optional hard filter for the content-node type.
        name: Optional case-insensitive exact node-name filter.
        identifier: Exact node ID required by the ``ID`` operator.
        ordinal: One-based ordinal required by the ``ORDINAL`` operator.
        order_domain: Ordering source used by ordinal resolution.
        metric: Numeric attribute used by ``SUPERLATIVE``.
        maximize: ``True`` selects a maximum, ``False`` selects a minimum.
            ``None`` means maximum for ``SUPERLATIVE`` and minimum for
            ``SPATIAL``.
    """

    operator: ReferenceOperator
    semantic_filters: tuple[tuple[str, ScalarValue], ...] = ()
    node_type: NodeType | None = None
    name: str | None = None
    identifier: str | None = None
    ordinal: int | None = None
    order_domain: OrderDomain | None = None
    metric: str | None = None
    maximize: bool | None = None

    def __post_init__(self) -> None:
        """Validate operator-specific invariants and immutable filters."""
        filter_names = [name for name, _value in self.semantic_filters]
        if len(filter_names) != len(set(filter_names)):
            raise ValueError("semantic_filters must not contain duplicate keys")
        if any(not name.strip() for name in filter_names):
            raise ValueError("semantic filter names must be non-empty")
        if any(not _is_scalar(value) for _name, value in self.semantic_filters):
            raise TypeError("semantic filter values must be JSON scalars")
        if self.name is not None and not self.name.strip():
            raise ValueError("name must be non-empty when provided")

        if self.operator is ReferenceOperator.ID:
            if self.identifier is None or not self.identifier.strip():
                raise ValueError("ID references require a non-empty identifier")
            if any(
                value is not None
                for value in (
                    self.ordinal,
                    self.order_domain,
                    self.metric,
                    self.maximize,
                )
            ):
                raise ValueError("ID references cannot define ordering fields")
            return

        if self.identifier is not None:
            raise ValueError("identifier is only valid for ID references")

        if self.operator is ReferenceOperator.ORDINAL:
            if self.ordinal is None or self.ordinal < 1:
                raise ValueError("ORDINAL references require ordinal >= 1")
            if self.metric is not None or self.maximize is not None:
                raise ValueError("ORDINAL references cannot define metric fields")
            return

        if self.ordinal is not None:
            raise ValueError("ordinal is only valid for ORDINAL references")

        if self.operator is ReferenceOperator.SUPERLATIVE:
            if self.metric not in {"attack", "hp"}:
                raise ValueError("SUPERLATIVE metric must be 'attack' or 'hp'")
            if self.order_domain is not None:
                raise ValueError("SUPERLATIVE references do not use order_domain")
            return

        if self.operator is ReferenceOperator.SPATIAL:
            if self.metric is not None:
                raise ValueError("SPATIAL references use distance_to_player")
            if self.order_domain not in {None, OrderDomain.SPATIAL}:
                raise ValueError("SPATIAL references require the SPATIAL domain")

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""
        return {
            "operator": self.operator.value,
            "semantic_filters": dict(self.semantic_filters),
            "node_type": self.node_type.name if self.node_type is not None else None,
            "name": self.name,
            "identifier": self.identifier,
            "ordinal": self.ordinal,
            "order_domain": (self.order_domain.value if self.order_domain is not None else None),
            "metric": self.metric,
            "maximize": self.maximize,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ReferenceSpec:
        """Build a validated specification from ``to_dict`` output.

        Args:
            value: Mapping containing the serialized specification.

        Returns:
            A validated immutable specification.

        Raises:
            TypeError: If a serialized field has the wrong shape.
            ValueError: If an enum value or specification invariant is invalid.
        """
        raw_filters = value.get("semantic_filters", {})
        if not isinstance(raw_filters, Mapping):
            raise TypeError("semantic_filters must be a mapping")

        filters: list[tuple[str, ScalarValue]] = []
        for raw_name, raw_filter_value in raw_filters.items():
            if not isinstance(raw_name, str):
                raise TypeError("semantic filter keys must be strings")
            if not _is_scalar(raw_filter_value):
                raise TypeError("semantic filter values must be JSON scalars")
            filters.append((raw_name, cast(ScalarValue, raw_filter_value)))

        raw_node_type = value.get("node_type")
        if raw_node_type is not None and not isinstance(raw_node_type, str):
            raise TypeError("node_type must be a string or null")
        node_type = NodeType[raw_node_type] if raw_node_type is not None else None

        raw_order_domain = value.get("order_domain")
        if raw_order_domain is not None and not isinstance(raw_order_domain, str):
            raise TypeError("order_domain must be a string or null")

        return cls(
            operator=ReferenceOperator(_required_string(value, "operator")),
            semantic_filters=tuple(sorted(filters)),
            node_type=node_type,
            name=_optional_string(value.get("name"), "name"),
            identifier=_optional_string(value.get("identifier"), "identifier"),
            ordinal=_optional_integer(value.get("ordinal"), "ordinal"),
            order_domain=(OrderDomain(raw_order_domain) if raw_order_domain is not None else None),
            metric=_optional_string(value.get("metric"), "metric"),
            maximize=_optional_boolean(value.get("maximize"), "maximize"),
        )


@dataclass(frozen=True, slots=True)
class ClarificationRequest:
    """Structured request for user input when a unique target is unavailable.

    Attributes:
        reason: Stable machine-readable ambiguity reason.
        question: Human-readable question suitable for the client UI.
        candidate_ids: Candidate node IDs relevant to the ambiguity.
        options: User-selectable deterministic options.
        details: Additional immutable scalar diagnostics.
    """

    reason: ClarificationReason
    question: str
    candidate_ids: tuple[str, ...] = ()
    options: tuple[str, ...] = ()
    details: tuple[tuple[str, ScalarValue], ...] = ()

    def __post_init__(self) -> None:
        """Validate request text and immutable collections."""
        if not self.question.strip():
            raise ValueError("question must be non-empty")
        if len(self.candidate_ids) != len(set(self.candidate_ids)):
            raise ValueError("candidate_ids must not contain duplicates")

        detail_names = [name for name, _value in self.details]
        if len(detail_names) != len(set(detail_names)):
            raise ValueError("details must not contain duplicate keys")
        if any(not name.strip() for name in detail_names):
            raise ValueError("detail names must be non-empty")
        if any(not _is_scalar(value) for _name, value in self.details):
            raise TypeError("detail values must be JSON scalars")

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible representation."""
        return {
            "reason": self.reason.value,
            "question": self.question,
            "candidate_ids": list(self.candidate_ids),
            "options": list(self.options),
            "details": dict(self.details),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> ClarificationRequest:
        """Build a validated request from ``to_dict`` output.

        Args:
            value: Mapping containing the serialized request.

        Returns:
            A validated immutable clarification request.
        """
        raw_candidate_ids = value.get("candidate_ids", ())
        raw_options = value.get("options", ())
        raw_details = value.get("details", {})

        candidate_ids = _string_sequence(raw_candidate_ids, "candidate_ids")
        options = _string_sequence(raw_options, "options")

        if not isinstance(raw_details, Mapping):
            raise TypeError("details must be a mapping")

        details: list[tuple[str, ScalarValue]] = []
        for raw_name, raw_detail_value in raw_details.items():
            if not isinstance(raw_name, str):
                raise TypeError("detail keys must be strings")
            if not _is_scalar(raw_detail_value):
                raise TypeError("detail values must be JSON scalars")
            details.append((raw_name, cast(ScalarValue, raw_detail_value)))

        return cls(
            reason=ClarificationReason(_required_string(value, "reason")),
            question=_required_string(value, "question"),
            candidate_ids=candidate_ids,
            options=options,
            details=tuple(sorted(details)),
        )


def _is_scalar(value: object) -> bool:
    return value is None or isinstance(value, str | int | float | bool)


def _required_string(value: Mapping[str, object], key: str) -> str:
    raw_value = value.get(key)
    if not isinstance(raw_value, str):
        raise TypeError(f"{key} must be a string")
    return raw_value


def _optional_string(value: object, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string or null")
    return value


def _optional_integer(value: object, key: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an integer or null")
    return value


def _optional_boolean(value: object, key: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a boolean or null")
    return value


def _string_sequence(value: object, key: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise TypeError(f"{key} must be a sequence of strings")

    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{key} must contain only strings")
        result.append(item)
    return tuple(result)
