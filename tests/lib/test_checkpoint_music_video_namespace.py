"""Regression test: music-video-anime stages emit music_video_* artifacts,
which the canonical CANONICAL_STAGE_ARTIFACTS map does not know.

Before O-3/M-1 fix (2026-07-21): every music-video-anime stage would raise
CheckpointValidationError because the validator looked up `research` →
`research_brief` and never found it in the user's `music_video_brief` artifacts.
The agent worked around it with an inline monkey-patch on write_checkpoint.

After fix: PIPELINE_STAGE_ARTIFACT_OVERRIDES is consulted first when
pipeline_type is given, so `("music-video-anime", "research")` resolves to
`music_video_brief`. The generic canonical map still wins for unknown
pipelines (preserves test_canonical_stage_still_requires_its_artifact).
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from lib.checkpoint import (  # noqa: E402
    CheckpointValidationError,
    PIPELINE_STAGE_ARTIFACT_OVERRIDES,
    validate_checkpoint,
)
from schemas.artifacts import ARTIFACT_NAMES  # noqa: E402


def _expect_raises(callable_, *, match: str) -> None:
    """Minimal pytest.raises-style helper that doesn't require pytest import."""
    try:
        callable_()
    except CheckpointValidationError as exc:
        if match not in str(exc):
            raise AssertionError(
                f"expected error matching {match!r}, got: {exc}"
            ) from exc
        return
    raise AssertionError(
        f"expected CheckpointValidationError matching {match!r}, but no error raised"
    )


def _checkpoint(stage, status, artifacts, pipeline_type):
    return {
        "version": "1.0",
        "project_id": "proj",
        "pipeline_type": pipeline_type,
        "stage": stage,
        "status": status,
        "timestamp": "2026-01-01T00:00:00Z",
        "artifacts": artifacts,
    }


def _valid_brief():
    return {
        "version": "1.0",
        "title": "AMV test",
        "hook": "test",
        "key_points": ["k1"],
        "tone": "hybrid-burst",
        "style": "anime music video (AMV/MAD)",
        "target_platform": "bilibili",
        "target_duration_seconds": 30,
        "metadata": {
            "music_track_path": "p/x.mp3",
            "music_track_duration_seconds": 30.0,
            "music_track_source": "ytsearch_artist_track",
            "music_track_license": "user_requested",
            "music_track_requires_user_ack": True,
            "music_track_user_ack_obtained": True,
            "global_user_ack_obtained": True,
            "audiomap_path": "p/audiomap.json",
            "anime_theme": {"explicit": True, "title": "Test"},
            "asset_route_options": {"agnes_opt_in": False},
        },
    }


def test_override_table_covers_eight_music_video_stages():
    # music-video-anime manifest declares 8 stages; each MUST have an override
    # so an artifact-bearing checkpoint can complete.
    expected = {
        "research", "proposal", "script", "scene_plan",
        "assets", "edit", "compose",
    }
    actual = {
        stage for (pipeline, stage) in PIPELINE_STAGE_ARTIFACT_OVERRIDES
        if pipeline == "music-video-anime"
    }
    assert actual == expected


def test_music_video_research_accepts_music_video_brief():
    validate_checkpoint(
        _checkpoint(
            "research", "completed",
            {"music_video_brief": _valid_brief()},
            "music-video-anime",
        )
    )


def test_music_video_research_rejects_generic_research_brief():
    # The pipeline's stage is research but the override says it expects
    # music_video_brief — a generic research_brief artifact must NOT satisfy.
    _expect_raises(
        lambda: validate_checkpoint(
            _checkpoint(
                "research", "completed",
                {"research_brief": _valid_brief()},
                "music-video-anime",
            )
        ),
        match="music_video_brief",
    )


def test_music_video_compose_requires_music_video_render_report():
    _expect_raises(
        lambda: validate_checkpoint(
            _checkpoint(
                "compose", "completed",
                {"render_report": {"version": "1.0"}},
                "music-video-anime",
            )
        ),
        match="music_video_render_report",
    )


def test_canonical_stage_still_requires_its_artifact_for_other_pipelines():
    # The override must NOT weaken enforcement for canonical-only pipelines.
    # character-animation has no override for `compose`, so it still demands
    # `render_report` like every other canonical pipeline.
    _expect_raises(
        lambda: validate_checkpoint(
            _checkpoint("compose", "completed", {}, "character-animation")
        ),
        match="render_report",
    )


def test_artifact_names_registers_all_seven_music_video_names():
    for name in (
        "music_video_brief",
        "music_video_proposal_packet",
        "music_video_script",
        "music_video_scene_plan",
        "music_video_asset_manifest",
        "music_video_edit_decisions",
        "music_video_render_report",
    ):
        assert name in ARTIFACT_NAMES, f"{name} missing from ARTIFACT_NAMES"


if __name__ == "__main__":
    test_override_table_covers_eight_music_video_stages()
    test_music_video_research_accepts_music_video_brief()
    test_music_video_research_rejects_generic_research_brief()
    test_music_video_compose_requires_music_video_render_report()
    test_canonical_stage_still_requires_its_artifact_for_other_pipelines()
    test_artifact_names_registers_all_seven_music_video_names()
    print("ALL O-3/M-1 regression tests passed.")