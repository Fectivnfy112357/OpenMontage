"""Detection helper for the music-video-anime runtime_swap fallback path.

When HyperFrames physically cannot satisfy a render request (the O-5 family
of bugs: empty timeline, beat sync verification failure, frame coverage too
low, cut count dropped below threshold), the agent must NOT silently fall
back to another runtime. The governance contract is:

    runtime_swap_detected: bool
    silent_fallback_used: bool   (must be False — even documented fallbacks
                                  require user authorization)
    runtime_swap:               (required iff runtime_swap_detected=true)
        exception_clause_invoked: true
        user_authorized_at: <ISO timestamp>
        from_runtime: "hyperframes"
        to_runtime: "ffmpeg" | "remotion"
        reason: "<detection output>"
        hyperframes_attempted_versions: [...]
        hyperframes_failure_mode: "empty_timeline" | "beat_sync_failed" | ...

This module is a PURE FUNCTION. It receives the post-render signals
(beat_sync_verification block, cut_count_rendered vs total_cuts, exit code
from npx hyperframes) and returns either ``None`` (no fallback suggested)
or a fully-populated ``runtime_swap`` dict ready to drop into
``render_report.runtime_swap``.

Detection rules — conservative. We only suggest a fallback when the
symptoms are clear and unrecoverable inside HyperFrames:

    1. verification_passed == False (beat sync visual change absent)
    2. frames_sampled / total_cuts ratio < 0.5 (more than half the cuts
       couldn't be sampled — typical of empty-timeline O-5)
    3. npx hyperframes exit code != 0 with "empty" or "no clips" in stderr

The agent receives the suggestion, presents it to the user, and on approval
sets ``exception_clause_invoked=true`` + ``user_authorized_at``. Until then
the suggestion is metadata only.

Lightweight fix 2026-07-21: lightweight means we only DETECT and SUGGEST.
Auto-execution of the fallback is a heavier scope decision.
"""

from __future__ import annotations

from typing import Any, Optional


# Minimum beat-sync visual-change ratio before we treat empty-timeline as
# suspected. 0.5 means "at least half the cuts must show a frame change
# at their downbeat". Below this, O-5 empty-timeline is the likely cause.
EMPTY_TIMELINE_THRESHOLD = 0.5

# HyperFrames stderr signals that mean empty timeline (O-5 family). Match
# substrings, lowercase. Keep this list conservative — false positives push
# agents toward unauthorized runtime swaps.
EMPTY_TIMELINE_STDERR_PATTERNS = (
    "no clips",
    "empty timeline",
    "no cuts found",
    "0 clips",
    "frames: 0",
)


def _safe_ratio(numerator: Any, denominator: Any) -> float:
    try:
        n = float(numerator)
        d = float(denominator)
        if d <= 0:
            return 0.0
        return n / d
    except (TypeError, ValueError):
        return 0.0


def detect_runtime_swap(
    beat_sync_verification: Optional[dict[str, Any]],
    cut_count_rendered: Any,
    total_cuts: Any,
    npx_stderr: Optional[str] = "",
) -> Optional[dict[str, Any]]:
    """Return a ``runtime_swap`` dict iff fallback should be suggested.

    Parameters mirror the fields an agent has at hand after a render attempt::

        beat_sync_verification: render_report.beat_sync_verification block
                                (or None if the agent hasn't populated it yet)
        cut_count_rendered:     metadata.cut_count_rendered
        total_cuts:             metadata.total_cuts (from edit_decisions)
        npx_stderr:             tail of npx hyperframes render stderr

    Returns None when HyperFrames' output looks healthy. Returns a
    fully-formed runtime_swap dict (without ``user_authorized_at`` — the
    agent fills that on user approval) otherwise.

    Lightweight fix (2026-07-21).
    """
    failures: list[str] = []

    # Rule 1 — beat sync verification explicitly failed
    if isinstance(beat_sync_verification, dict):
        if beat_sync_verification.get("verification_passed") is False:
            failures.append("beat_sync_verification_failed")

        # Rule 2 — sampled frames too sparse vs total cuts (empty timeline)
        frames = beat_sync_verification.get("frames_sampled", 0) or 0
        ratio = _safe_ratio(frames, total_cuts)
        if total_cuts and ratio < EMPTY_TIMELINE_THRESHOLD:
            failures.append(f"frames_sampled_ratio_low:{ratio:.2f}")

    # Rule 3 — npx stderr carries O-5 markers
    if npx_stderr:
        lower = npx_stderr.lower()
        for marker in EMPTY_TIMELINE_STDERR_PATTERNS:
            if marker in lower:
                failures.append(f"stderr_marker:{marker}")
                break

    # cut_count_rendered may itself be the smoking gun (HyperFrames dropped
    # most cuts and reported only e.g. 5 of 107)
    rendered_ratio = _safe_ratio(cut_count_rendered, total_cuts)
    if total_cuts and rendered_ratio < EMPTY_TIMELINE_THRESHOLD:
        failures.append(f"cut_count_rendered_ratio_low:{rendered_ratio:.2f}")

    if not failures:
        return None

    # Pick the strongest single failure mode for hyperframes_failure_mode.
    # Priority: explicit beat_sync > stderr marker > ratio-based.
    if "beat_sync_verification_failed" in failures:
        failure_mode = "beat_sync_failed"
    elif any(f.startswith("stderr_marker:") for f in failures):
        failure_mode = "empty_timeline"
    else:
        failure_mode = "empty_timeline"

    return {
        "exception_clause_invoked": False,  # agent sets True on user approval
        "user_authorized_at": None,         # agent fills on approval
        "from_runtime": "hyperframes",
        "to_runtime": "ffmpeg",
        "reason": (
            "HyperFrames render produced symptoms consistent with O-5 "
            "(empty timeline / beat sync failure / severe cut drop). "
            f"Detected: {', '.join(failures)}. Fallback to ffmpeg+xfade "
            "requires explicit user authorization — see "
            "compose-director.md 'Fallback Trigger Flow'."
        ),
        "hyperframes_failure_mode": failure_mode,
        # Detection details for audit (not part of schema.required but
        # useful for reviewer inspection)
        "detection_signals": failures,
    }


def attach_suggestion_to_render_report(
    render_report: dict[str, Any],
    beat_sync_verification: Optional[dict[str, Any]] = None,
    cut_count_rendered: Any = None,
    npx_stderr: Optional[str] = "",
) -> dict[str, Any]:
    """Convenience wrapper: detect + mutate ``render_report`` in place.

    Mutates ``render_report.runtime_swap_detected`` to True and fills
    ``render_report.runtime_swap`` with the suggestion iff detection
    fires. Returns the same dict for chaining.

    Does NOT mutate ``silent_fallback_used`` — that flag remains False
    because we only SUGGEST here, never auto-execute. Lightweight scope.
    """
    total_cuts = (
        (render_report.get("metadata") or {}).get("total_cuts")
        if isinstance(render_report.get("metadata"), dict)
        else None
    )
    suggestion = detect_runtime_swap(
        beat_sync_verification=beat_sync_verification,
        cut_count_rendered=cut_count_rendered,
        total_cuts=total_cuts,
        npx_stderr=npx_stderr,
    )
    if suggestion is not None:
        render_report["runtime_swap_detected"] = True
        render_report["runtime_swap"] = suggestion
    return render_report