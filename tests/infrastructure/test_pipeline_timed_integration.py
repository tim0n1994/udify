"""Integration: process_intent_timed produces a timing report (U3 PR2)."""

from __future__ import annotations

import pytest

from udify.core.pipeline import UdifyPipeline


@pytest.fixture
def timed_pipeline(tmp_path):
    (tmp_path / "characters.ini").write_text("[Hero]\nMaxLife=100\n")
    (tmp_path / "items.ini").write_text("[Sword]\nAttack=20\n")
    return UdifyPipeline(game_root=tmp_path)


@pytest.mark.asyncio
async def test_timed_pipeline_populates_timing_report(timed_pipeline):
    result = await timed_pipeline.process_intent_timed("user1", "让BOSS血量翻倍", preview_only=True)
    assert result.timing_report is not None
    # The report must carry the process_intent phase with a measured duration.
    phases = result.timing_report.get("phases", [])
    assert any(p["phase"] == "process_intent" for p in phases)
    assert result.timing_report["mandatory_ms"] >= 0
    assert result.timing_report["total_ms"] >= result.timing_report["mandatory_ms"]


@pytest.mark.asyncio
async def test_timed_pipeline_preserves_success_semantics(timed_pipeline):
    """Timing must not change correctness — invalid intent still fails."""
    result = await timed_pipeline.process_intent_timed("user1", "帮我写情书", preview_only=True)
    assert not result.success
    # Even a failed job carries timing (we measured the attempt).
    assert result.timing_report is not None
