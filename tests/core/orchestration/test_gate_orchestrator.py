"""Tests for the GateOrchestrator fail-closed state machine (iter6 M1)."""

from __future__ import annotations

from types import SimpleNamespace

from udify.core.orchestration.gate_orchestrator import (
    BLOCKING_GATES,
    DeliveryTier,
    GateLifecycle,
    GateName,
    GateOrchestrator,
    GateVerdict,
)


def _ctx(**kw: object) -> SimpleNamespace:
    """Build a fake gate context with sensible defaults."""
    defaults = {
        "resolved_targets": ["boss1"],
        "ambiguous": False,
        "sandboxed": True,
        "validation_passed": True,
        "validation_skipped": False,
        "dependency_conflicts": [],
    }
    defaults.update(kw)
    return SimpleNamespace(**defaults)


class TestAllGatesPass:
    def test_all_pass_yields_installed_verified(self) -> None:
        verdict = GateOrchestrator().run_gates("job-1", _ctx())
        assert verdict.final_tier is DeliveryTier.INSTALLED_VERIFIED
        assert all(g.verdict is GateVerdict.PASS for g in verdict.gates)
        assert not verdict.needs_clarification

    def test_four_blocking_gates_decided(self) -> None:
        verdict = GateOrchestrator().run_gates("job-1", _ctx())
        decided = [g for g in verdict.gates if g.lifecycle is GateLifecycle.DECIDED]
        assert len(decided) == len(BLOCKING_GATES)


class TestNeedsClarificationPauses:
    def test_ambiguous_intent_pauses_job(self) -> None:
        verdict = GateOrchestrator().run_gates("job-1", _ctx(ambiguous=True))
        assert verdict.needs_clarification
        assert verdict.final_tier is DeliveryTier.NONE

    def test_pause_skips_later_gates(self) -> None:
        verdict = GateOrchestrator().run_gates("job-1", _ctx(ambiguous=True))
        intent_gate = [g for g in verdict.gates if g.name is GateName.INTENT_GROUNDING][0]
        assert intent_gate.verdict is GateVerdict.NEEDS_CLARIFICATION
        sandbox_gate = [g for g in verdict.gates if g.name is GateName.SANDBOX][0]
        assert sandbox_gate.lifecycle is GateLifecycle.PENDING
        assert "skipped" in sandbox_gate.evidence

    def test_clarification_message_present(self) -> None:
        verdict = GateOrchestrator().run_gates("job-1", _ctx(ambiguous=True))
        intent_gate = [g for g in verdict.gates if g.name is GateName.INTENT_GROUNDING][0]
        assert intent_gate.clarification is not None


class TestSandboxDegradation:
    def test_unsandboxed_lowers_to_static_only(self) -> None:
        """Degradation rule: unsandboxed lowers tier to static-only, never claims sandboxed."""
        verdict = GateOrchestrator().run_gates("job-1", _ctx(sandboxed=False))
        assert verdict.final_tier is DeliveryTier.STATIC_ONLY
        sandbox_gate = [g for g in verdict.gates if g.name is GateName.SANDBOX][0]
        assert sandbox_gate.verdict is GateVerdict.PASS  # still passes, just lower tier
        assert "static-only" in sandbox_gate.evidence

    def test_sandbox_pass_at_full_tier(self) -> None:
        verdict = GateOrchestrator().run_gates("job-1", _ctx(sandboxed=True))
        sandbox_gate = [g for g in verdict.gates if g.name is GateName.SANDBOX][0]
        assert sandbox_gate.delivery_tier is DeliveryTier.INSTALLED_VERIFIED


class TestRuntimeValidation:
    def test_validation_failure_lowers_to_unverified(self) -> None:
        verdict = GateOrchestrator().run_gates("job-1", _ctx(validation_passed=False))
        assert verdict.final_tier is DeliveryTier.UNVERIFIED_ARTIFACT

    def test_validation_skipped_lowers_to_unverified(self) -> None:
        verdict = GateOrchestrator().run_gates(
            "job-1", _ctx(validation_passed=None, validation_skipped=True)
        )
        assert verdict.final_tier is DeliveryTier.UNVERIFIED_ARTIFACT


class TestDependencyGate:
    def test_cycle_conflict_blocks_install(self) -> None:
        conflict = SimpleNamespace(kind="CYCLE")
        verdict = GateOrchestrator().run_gates("job-1", _ctx(dependency_conflicts=[conflict]))
        assert verdict.final_tier is DeliveryTier.NONE

    def test_missing_dependency_blocks(self) -> None:
        conflict = SimpleNamespace(kind="MISSING")
        verdict = GateOrchestrator().run_gates("job-1", _ctx(dependency_conflicts=[conflict]))
        assert verdict.final_tier is DeliveryTier.NONE

    def test_no_conflicts_passes(self) -> None:
        verdict = GateOrchestrator().run_gates("job-1", _ctx(dependency_conflicts=[]))
        dep_gate = [g for g in verdict.gates if g.name is GateName.DEPENDENCY][0]
        assert dep_gate.verdict is GateVerdict.PASS


class TestFinalTierIsMin:
    def test_weakest_gate_determines_tier(self) -> None:
        # Sandbox unsandboxed (static_only=1) but validation passed (verified=3)
        # -> final tier should be static_only (the minimum).
        verdict = GateOrchestrator().run_gates(
            "job-1", _ctx(sandboxed=False, validation_passed=True)
        )
        assert verdict.final_tier is DeliveryTier.STATIC_ONLY

    def test_final_tier_reason_names_weakest_gate(self) -> None:
        verdict = GateOrchestrator().run_gates("job-1", _ctx(sandboxed=False))
        assert "sandbox" in verdict.final_tier_reason


class TestFrozenAndSerialization:
    def test_job_verdict_is_frozen(self) -> None:
        verdict = GateOrchestrator().run_gates("job-1", _ctx())
        try:
            verdict.final_tier = DeliveryTier.NONE  # type: ignore[misc]
            raise AssertionError("should be frozen")
        except AttributeError:
            pass

    def test_to_dict_roundtrips_tier_name(self) -> None:
        verdict = GateOrchestrator().run_gates("job-1", _ctx())
        d = verdict.to_dict()
        assert d["final_tier"] == "INSTALLED_VERIFIED"
        assert len(d["gates"]) == len(BLOCKING_GATES)
