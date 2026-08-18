"""Tests for seatbelt profile generation (U4-SANDBOX-REAL PR1)."""

from __future__ import annotations

from udify.core.execution.seatbelt_profile import build_seatbelt_profile, profile_for_temp_staging


def test_profile_uses_version_1_deny_default():
    p = build_seatbelt_profile(["/tmp/staging"])
    assert "(version 1)" in p
    assert "(deny default)" in p


def test_writable_dirs_injected():
    p = build_seatbelt_profile(["/tmp/a", "/tmp/b"])
    assert "/tmp/a" in p
    assert "/tmp/b" in p


def test_network_denied_by_default():
    p = build_seatbelt_profile(["/tmp/x"])
    assert "(deny network)" in p


def test_network_allowed_when_opt_in():
    p = build_seatbelt_profile(["/tmp/x"], allow_network=True)
    assert "(allow network)" in p


def test_process_exec_allowed_by_default():
    p = build_seatbelt_profile(["/tmp/x"])
    assert "process-exec" in p


def test_convenience_for_temp_staging():
    p = profile_for_temp_staging("/tmp/stage")
    assert "(deny default)" in p
    assert "/tmp/stage" in p
