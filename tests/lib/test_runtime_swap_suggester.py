"""Regression tests for the lightweight runtime_swap fallback suggestion.

Verifies:
  1. detect_runtime_swap returns None for healthy inputs
  2. detect_runtime_swap returns a populated dict when beat_sync fails
  3. detect_runtime_swap returns a populated dict when frames_sampled ratio is low
  4. detect_runtime_swap returns a populated dict when npx stderr carries O-5 markers
  5. attach_suggestion_to_render_report mutates render_report.runtime_swap_detected
  6. attach_suggestion_to_render_report leaves render_report untouched on healthy inputs
  7. exception_clause_invoked stays False until user approves (NEVER auto-execute)
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.runtime_swap_suggester import (  # noqa: E402
    EMPTY_TIMELINE_STDERR_PATTERNS,
    EMPTY_TIMELINE_THRESHOLD,
    attach_suggestion_to_render_report,
    detect_runtime_swap,
)


def test_healthy_input_returns_none():
    """All signals look OK -> no fallback suggestion."""
    result = detect_runtime_swap(
        beat_sync_verification={
            "verification_passed": True,
            "frames_sampled": 100,
            "max_drift_ms_observed": 30,
        },
        cut_count_rendered=100,
        total_cuts=100,
        npx_stderr="[hyperframes] rendered successfully",
    )
    assert result is None, f"expected None, got {result}"


def test_beat_sync_verification_failure_triggers_suggestion():
    result = detect_runtime_swap(
        beat_sync_verification={"verification_passed": False, "frames_sampled": 100},
        cut_count_rendered=100,
        total_cuts=100,
        npx_stderr="",
    )
    assert result is not None
    assert result["from_runtime"] == "hyperframes"
    assert result["to_runtime"] == "ffmpeg"
    assert result["hyperframes_failure_mode"] == "beat_sync_failed"
    assert "beat_sync_verification_failed" in result["detection_signals"]
    assert result["exception_clause_invoked"] is False
    assert result["user_authorized_at"] is None
    print("beat_sync failure detection: OK")


def test_frames_sampled_ratio_low_triggers_suggestion():
    # 10 sampled out of 100 total cuts → ratio 0.10 < threshold 0.5
    result = detect_runtime_swap(
        beat_sync_verification={"verification_passed": True, "frames_sampled": 10},
        cut_count_rendered=10,
        total_cuts=100,
        npx_stderr="",
    )
    assert result is not None
    assert result["hyperframes_failure_mode"] in ("empty_timeline", "beat_sync_failed")
    assert any("ratio_low" in s for s in result["detection_signals"])
    print("ratio-based detection: OK")


def test_npx_stderr_marker_triggers_suggestion():
    result = detect_runtime_swap(
        beat_sync_verification=None,
        cut_count_rendered=0,
        total_cuts=100,
        npx_stderr="[hyperframes] error: empty timeline — 0 clips produced",
    )
    assert result is not None
    assert result["hyperframes_failure_mode"] == "empty_timeline"
    assert any("stderr_marker:" in s for s in result["detection_signals"])
    print("stderr marker detection: OK")


def test_each_empty_timeline_pattern_recognized():
    for pattern in EMPTY_TIMELINE_STDERR_PATTERNS:
        result = detect_runtime_swap(
            beat_sync_verification=None,
            cut_count_rendered=0,
            total_cuts=10,
            npx_stderr=f"hyperframes render error: {pattern} found in timeline",
        )
        assert result is not None, f"pattern {pattern!r} should trigger detection"
    print(f"all {len(EMPTY_TIMELINE_STDERR_PATTERNS)} stderr patterns recognized: OK")


def test_attach_suggestion_mutates_render_report():
    rr = {
        "metadata": {"total_cuts": 100, "cut_count_rendered": 5},
        "runtime_swap_detected": False,
    }
    out = attach_suggestion_to_render_report(
        rr,
        beat_sync_verification={"verification_passed": False, "frames_sampled": 5},
        cut_count_rendered=5,
        npx_stderr="",
    )
    assert out["runtime_swap_detected"] is True
    assert "runtime_swap" in out
    assert out["runtime_swap"]["from_runtime"] == "hyperframes"
    assert out["runtime_swap"]["exception_clause_invoked"] is False
    # silent_fallback_used not touched (still absent / False)
    assert out.get("silent_fallback_used", False) is False
    print("attach_suggestion mutation: OK")


def test_attach_suggestion_leaves_healthy_render_alone():
    rr = {
        "metadata": {"total_cuts": 50, "cut_count_rendered": 50},
        "runtime_swap_detected": False,
    }
    out = attach_suggestion_to_render_report(
        rr,
        beat_sync_verification={"verification_passed": True, "frames_sampled": 50},
        cut_count_rendered=50,
        npx_stderr="[hyperframes] rendered 1920x1080 OK",
    )
    assert out["runtime_swap_detected"] is False
    assert "runtime_swap" not in out
    print("healthy render left alone: OK")


def test_exception_clause_never_auto_invoked():
    """Lightweight scope guard: detect_runtime_swap MUST NEVER set
    exception_clause_invoked=True. That flag is reserved for the moment
    the user explicitly authorizes the fallback."""
    cases = [
        # beat sync fail
        {"beat_sync_verification": {"verification_passed": False, "frames_sampled": 0},
         "cut_count_rendered": 0, "total_cuts": 10, "npx_stderr": ""},
        # ratio low
        {"beat_sync_verification": {"verification_passed": True, "frames_sampled": 1},
         "cut_count_rendered": 1, "total_cuts": 100, "npx_stderr": ""},
        # stderr marker
        {"beat_sync_verification": None,
         "cut_count_rendered": 0, "total_cuts": 10,
         "npx_stderr": "error: no clips"},
    ]
    for c in cases:
        r = detect_runtime_swap(**c)
        assert r is not None, f"case did not trigger: {c}"
        assert r["exception_clause_invoked"] is False, (
            f"FAIL: lightweight scope violated — exception_clause_invoked "
            f"auto-set to True for {c}"
        )
    print("exception_clause_invoked never auto-set: OK")


def test_threshold_constant_is_documented():
    assert 0.0 < EMPTY_TIMELINE_THRESHOLD < 1.0
    assert EMPTY_TIMELINE_THRESHOLD == 0.5
    print(f"threshold constant {EMPTY_TIMELINE_THRESHOLD}: OK")


if __name__ == "__main__":
    test_healthy_input_returns_none()
    test_beat_sync_verification_failure_triggers_suggestion()
    test_frames_sampled_ratio_low_triggers_suggestion()
    test_npx_stderr_marker_triggers_suggestion()
    test_each_empty_timeline_pattern_recognized()
    test_attach_suggestion_mutates_render_report()
    test_attach_suggestion_leaves_healthy_render_alone()
    test_exception_clause_never_auto_invoked()
    test_threshold_constant_is_documented()
    print()
    print("ALL runtime_swap_suggester tests passed.")