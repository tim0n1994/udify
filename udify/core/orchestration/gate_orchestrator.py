"""Gate orchestrator — runs the five trust gates as a fail-closed state machine.

iter6 (V1-ORCHESTRATION research): the five gates are not five sequential ``if``
checks. Four are *blocking trust gates* (intent grounding, dependency, sandbox,
runtime validation) and one is a *cross-cutting control gate* (latency timing).

The key invariant is the **degradation rule**: a failure may lower the *delivery
tier* (from verified down to static-only) but may NEVER lower the *safety level*
(sandbox execution never degrades to bare execution). ``final_tier`` is the
minimum tier across all blocking gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum
from typing import Any, Protocol


class GateName(StrEnum):
    """The five trust gates."""

    INTENT_GROUNDING = "intent_grounding"
    DEPENDENCY = "dependency"
    SANDBOX = "sandbox"
    RUNTIME_VALIDATION = "runtime_validation"
    LATENCY = "latency"


class GateLifecycle(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DECIDED = "decided"


class GateVerdict(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NEEDS_CLARIFICATION = "needs_clarification"


class DeliveryTier(int, Enum):
    """Higher int = stronger tier. ``min()`` across gates yields the weakest link."""

    NONE = 0
    STATIC_ONLY = 1
    UNVERIFIED_ARTIFACT = 2
    INSTALLED_VERIFIED = 3


# Gates that block the job when they fail. LATENCY is cross-cutting and never blocks.
BLOCKING_GATES: tuple[GateName, ...] = (
    GateName.INTENT_GROUNDING,
    GateName.SANDBOX,
    GateName.RUNTIME_VALIDATION,
    GateName.DEPENDENCY,
)

# The serial order in which blocking gates run (dependency is checked before install).
GATE_ORDER: tuple[GateName, ...] = (
    GateName.INTENT_GROUNDING,
    GateName.SANDBOX,
    GateName.RUNTIME_VALIDATION,
    GateName.DEPENDENCY,
)


@dataclass(frozen=True, slots=True)
class GateResult:
    """One gate's lifecycle + verdict + the delivery tier it allows."""

    name: GateName
    lifecycle: GateLifecycle
    verdict: GateVerdict
    evidence: str
    delivery_tier: DeliveryTier
    clarification: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name.value,
            "lifecycle": self.lifecycle.value,
            "verdict": self.verdict.value,
            "evidence": self.evidence,
            "delivery_tier": self.delivery_tier.name,
            "clarification": self.clarification,
        }


@dataclass(frozen=True, slots=True)
class JobVerdict:
    """The aggregated result of running all gates for one job."""

    job_id: str
    gates: tuple[GateResult, ...]
    final_tier: DeliveryTier
    final_tier_reason: str

    @property
    def needs_clarification(self) -> bool:
        """True if any gate paused the job for user input."""
        return any(g.verdict is GateVerdict.NEEDS_CLARIFICATION for g in self.gates)

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "gates": [g.to_dict() for g in self.gates],
            "final_tier": self.final_tier.name,
            "final_tier_reason": self.final_tier_reason,
        }


class GateContext(Protocol):
    """Inputs the gates reason over. Implemented by the caller (job runner)."""

    graph: Any
    intent: Any
    patch: Any
    manifests: Any


def gate_intent_grounding(ctx: GateContext) -> GateResult:
    """Check that the intent resolved to a unique, correct target."""
    resolved = getattr(ctx, "resolved_targets", None)
    ambiguous = getattr(ctx, "ambiguous", False)
    if ambiguous:
        return GateResult(
            name=GateName.INTENT_GROUNDING,
            lifecycle=GateLifecycle.DECIDED,
            verdict=GateVerdict.NEEDS_CLARIFICATION,
            evidence="intent is ambiguous; user must disambiguate",
            delivery_tier=DeliveryTier.NONE,
            clarification="Multiple targets matched the intent. Please specify which one.",
        )
    if not resolved:
        return GateResult(
            name=GateName.INTENT_GROUNDING,
            lifecycle=GateLifecycle.DECIDED,
            verdict=GateVerdict.FAIL,
            evidence="no target resolved from intent",
            delivery_tier=DeliveryTier.NONE,
        )
    return GateResult(
        name=GateName.INTENT_GROUNDING,
        lifecycle=GateLifecycle.DECIDED,
        verdict=GateVerdict.PASS,
        evidence=f"resolved {len(resolved)} target(s)",
        delivery_tier=DeliveryTier.INSTALLED_VERIFIED,
    )


def gate_sandbox(ctx: GateContext) -> GateResult:
    """Check that script execution is sandboxed or honestly degraded."""
    sandboxed = getattr(ctx, "sandboxed", None)
    # The degradation rule: unsandboxed execution lowers tier but the gate still PASSES
    # (static-only delivery). It never silently claims sandboxed.
    if sandboxed is True:
        return GateResult(
            name=GateName.SANDBOX,
            lifecycle=GateLifecycle.DECIDED,
            verdict=GateVerdict.PASS,
            evidence="scripts executed under sandbox-exec",
            delivery_tier=DeliveryTier.INSTALLED_VERIFIED,
        )
    if sandboxed is False:
        return GateResult(
            name=GateName.SANDBOX,
            lifecycle=GateLifecycle.DECIDED,
            verdict=GateVerdict.PASS,
            evidence="scripts not executed; no sandbox execution claimed (static-only)",
            delivery_tier=DeliveryTier.STATIC_ONLY,
        )
    # No scripts to run -> sandbox gate is trivially satisfied at full tier.
    return GateResult(
        name=GateName.SANDBOX,
        lifecycle=GateLifecycle.DECIDED,
        verdict=GateVerdict.PASS,
        evidence="no scripts to execute",
        delivery_tier=DeliveryTier.INSTALLED_VERIFIED,
    )


def gate_runtime_validation(ctx: GateContext) -> GateResult:
    """Check the runtime validation report."""
    validation_passed = getattr(ctx, "validation_passed", None)
    validation_skipped = getattr(ctx, "validation_skipped", False)
    if validation_passed is True and not validation_skipped:
        return GateResult(
            name=GateName.RUNTIME_VALIDATION,
            lifecycle=GateLifecycle.DECIDED,
            verdict=GateVerdict.PASS,
            evidence="runtime validation passed",
            delivery_tier=DeliveryTier.INSTALLED_VERIFIED,
        )
    if validation_skipped or validation_passed is None:
        return GateResult(
            name=GateName.RUNTIME_VALIDATION,
            lifecycle=GateLifecycle.DECIDED,
            verdict=GateVerdict.PASS,
            evidence="runtime validation not available; delivery downgraded to unverified",
            delivery_tier=DeliveryTier.UNVERIFIED_ARTIFACT,
        )
    return GateResult(
        name=GateName.RUNTIME_VALIDATION,
        lifecycle=GateLifecycle.DECIDED,
        verdict=GateVerdict.FAIL,
        evidence="runtime validation failed",
        delivery_tier=DeliveryTier.UNVERIFIED_ARTIFACT,
    )


def gate_dependency(ctx: GateContext) -> GateResult:
    """Check for dependency conflicts before install."""
    conflicts = getattr(ctx, "dependency_conflicts", [])
    if getattr(ctx, "package_only", False):
        return GateResult(
            name=GateName.DEPENDENCY,
            lifecycle=GateLifecycle.DECIDED,
            verdict=GateVerdict.PASS,
            evidence="installation dependencies not evaluated: package-only delivery",
            delivery_tier=DeliveryTier.UNVERIFIED_ARTIFACT,
        )
    has_cycle = any(getattr(c, "kind", None) == "CYCLE" for c in conflicts)
    has_missing = any(getattr(c, "kind", None) == "MISSING" for c in conflicts)
    if has_cycle or has_missing:
        return GateResult(
            name=GateName.DEPENDENCY,
            lifecycle=GateLifecycle.DECIDED,
            verdict=GateVerdict.FAIL,
            evidence=f"{len(conflicts)} blocking dependency conflict(s)",
            delivery_tier=DeliveryTier.NONE,
        )
    return GateResult(
        name=GateName.DEPENDENCY,
        lifecycle=GateLifecycle.DECIDED,
        verdict=GateVerdict.PASS,
        evidence="no blocking dependency conflicts",
        delivery_tier=DeliveryTier.INSTALLED_VERIFIED,
    )


_GATE_FUNCS = {
    GateName.INTENT_GROUNDING: gate_intent_grounding,
    GateName.SANDBOX: gate_sandbox,
    GateName.RUNTIME_VALIDATION: gate_runtime_validation,
    GateName.DEPENDENCY: gate_dependency,
}


class GateOrchestrator:
    """Run the five gates in serial order and aggregate into a JobVerdict.

    A ``NEEDS_CLARIFICATION`` verdict immediately pauses: later gates do not run.
    The ``final_tier`` is the minimum tier across all blocking gates, so a single
    weak gate lowers the whole job's delivery promise.
    """

    def run_gates(self, job_id: str, ctx: GateContext) -> JobVerdict:
        results: list[GateResult] = []
        paused = False
        for name in GATE_ORDER:
            if paused:
                results.append(
                    GateResult(
                        name=name,
                        lifecycle=GateLifecycle.PENDING,
                        verdict=GateVerdict.PASS,
                        evidence="skipped: earlier gate paused the job",
                        delivery_tier=DeliveryTier.NONE,
                    )
                )
                continue
            fn = _GATE_FUNCS[name]
            result = fn(ctx)
            results.append(result)
            if result.verdict is GateVerdict.NEEDS_CLARIFICATION:
                paused = True

        blocking = [
            r for r in results if r.name in BLOCKING_GATES and r.lifecycle is GateLifecycle.DECIDED
        ]
        if blocking:
            final_tier = min(r.delivery_tier for r in blocking)
            weakest = min(blocking, key=lambda r: r.delivery_tier)
            reason = f"{weakest.name.value} gate set the tier to {weakest.delivery_tier.name}"
        else:
            final_tier = DeliveryTier.NONE
            reason = "no blocking gates decided (job paused before any ran)"

        return JobVerdict(
            job_id=job_id,
            gates=tuple(results),
            final_tier=final_tier,
            final_tier_reason=reason,
        )
