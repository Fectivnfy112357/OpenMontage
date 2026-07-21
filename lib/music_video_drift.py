"""Drift computation for music-video-anime beat-anchor alignment.

The pipeline's ``beat_anchor_policy`` (in ``pipeline_defs/music-video-anime.yaml``)
requires every cut boundary to land within ``max_drift_ms`` (default 50ms)
of the chosen ``beat_anchor.t_seconds``. The ``music_video_edit_decisions``
schema's ``cuts[i].drift_ms`` field is the canonical record.

This helper centralizes the formula and surfaces a single descriptive error
when drift exceeds the limit, instead of one cryptic
``ValidationError: 84 is greater than 50`` per offending cut.
"""

from __future__ import annotations

DEFAULT_MAX_DRIFT_MS = 50  # per pipeline_defs/music-video-anime.yaml:beat_anchor_policy


def compute_drift_ms(at_seconds: float, anchor_t_seconds: float) -> float:
    """Return ``1000 * |at_seconds - anchor.t_seconds|`` rounded to 2dp."""
    return round(1000 * abs(float(at_seconds) - float(anchor_t_seconds)), 2)


def check_drift(
    at_seconds: float,
    anchor_t_seconds: float,
    *,
    max_drift_ms: float = DEFAULT_MAX_DRIFT_MS,
) -> tuple[float, str | None]:
    """Compute drift and validate against the limit.

    Returns ``(drift_ms, error_or_None)``. The error string is human-readable
    (says "cut at 12.34s drifted 84ms from anchor at 11.50s (limit 50ms)")
    and is suitable for direct return via ``ToolResult(success=False, error=...)``.
    """
    drift_ms = compute_drift_ms(at_seconds, anchor_t_seconds)
    if drift_ms > max_drift_ms:
        return drift_ms, (
            f"cut at {at_seconds:.2f}s drifted {drift_ms}ms from beat_anchor at "
            f"{anchor_t_seconds:.2f}s (limit {max_drift_ms}ms per "
            "pipeline beat_anchor_policy.max_drift_ms)"
        )
    return drift_ms, None
