"""Tests for ``lib/music_video_adapter``, ``lib/music_video_ids``, and
``lib/music_video_drift`` — the music-video-anime pipeline helpers introduced
as the M-7 fix (2026-07-21).

Covers:
  - O-4 (field-name normalization): schema-form -> tool-form round trips
  - id pattern checks (music_video_scene_plan/asset_manifest/edit_decisions)
  - drift_ms computation and limit enforcement (beat_anchor_policy)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure ``lib.<module>`` imports resolve when this file is run directly
# (``python tests/pipelines/test_music_video_helpers.py``) — `python` sets
# cwd to the test file's directory by default, leaving `lib/` outside sys.path.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
os.chdir(str(_PROJECT_ROOT))

from lib.music_video_adapter import (
    adapt_asset_manifest_for_tool,
    adapt_edit_decisions_for_tool,
    adapt_schema_inputs_to_tool,
)
from lib.music_video_drift import (
    DEFAULT_MAX_DRIFT_MS,
    check_drift,
    compute_drift_ms,
)
from lib.music_video_ids import check_asset_id, check_cut_id, check_music_video_id, check_scene_id


def test_adapt_asset_manifest_schema_form_to_tool_form():
    """schema's entries[] + asset_id -> tool's assets[] + id."""
    schema_form = {
        "version": "1.0",
        "entries": [
            {"asset_id": "a001", "path": "/tmp/a.mp4", "license": "user_provided"},
            {"asset_id": "a002", "path": "/tmp/b.mp4"},
        ],
        "metadata": {"asset_route": "video_downloader"},
    }
    out = adapt_asset_manifest_for_tool(schema_form)
    assert "assets" in out
    assert "entries" in out  # original preserved for round-trip
    assert len(out["assets"]) == 2
    assert out["assets"][0]["id"] == "a001"
    assert out["assets"][0]["asset_id"] == "a001"  # source preserved
    print("O-4 schema->tool: OK")


def test_adapt_asset_manifest_passes_through_tool_form():
    """tool-form input is idempotent."""
    tool_form = {"assets": [{"id": "x", "path": "/tmp/x.mp4"}]}
    out = adapt_asset_manifest_for_tool(tool_form)
    assert out["assets"][0]["id"] == "x"
    print("O-4 tool->tool (idempotent): OK")


def test_adapt_edit_decisions_schema_form_to_tool_form():
    """cut_id + asset_path -> id + source."""
    schema_form = {
        "cuts": [
            {"cut_id": "c001", "scene_id": "s001", "asset_id": "a001",
             "asset_path": "/tmp/a.mp4", "at_seconds": 0.0, "duration_seconds": 2.0}
        ]
    }
    out = adapt_edit_decisions_for_tool(schema_form)
    assert out["cuts"][0]["id"] == "c001"
    assert out["cuts"][0]["source"] == "/tmp/a.mp4"
    assert out["cuts"][0]["cut_id"] == "c001"  # source preserved
    assert out["cuts"][0]["asset_id"] == "a001"
    print("O-4 edit decisions -> tool: OK")


def test_adapt_one_call_combined():
    ed = {"cuts": [{"cut_id": "c001", "asset_path": "/x", "at_seconds": 0.0}]}
    am = {"entries": [{"asset_id": "a001", "path": "/x"}]}
    ed2, am2 = adapt_schema_inputs_to_tool(ed, am)
    assert ed2["cuts"][0]["id"] == "c001"
    assert ed2["cuts"][0]["source"] == "/x"
    assert am2["assets"][0]["id"] == "a001"
    print("O-4 one-call adapter: OK")


def test_scene_id_pattern():
    assert check_scene_id("s001") is None
    assert check_scene_id("s1024") is None
    err = check_scene_id("s1")
    assert err and "sNNN" in err
    err = check_scene_id("scene-1")
    assert err
    err = check_scene_id("")
    assert err
    print("music_video_ids scene_id: OK")


def test_asset_id_pattern():
    assert check_asset_id("a001") is None
    err = check_asset_id("c001")  # wrong letter
    assert err and "aNNN" in err
    print("music_video_ids asset_id: OK")


def test_cut_id_pattern():
    assert check_cut_id("c001") is None
    err = check_cut_id("s001")  # wrong letter
    assert err and "cNNN" in err
    print("music_video_ids cut_id: OK")


def test_music_video_id_dispatch():
    assert check_music_video_id("scene", "s001") is None
    err = check_music_video_id("scene", "x1")
    assert err
    try:
        check_music_video_id("bogus", "x")
    except ValueError as e:
        assert "unknown" in str(e)
    else:
        raise AssertionError("expected ValueError")
    print("music_video_ids dispatch: OK")


def test_drift_compute_zero_at_anchor():
    assert compute_drift_ms(10.0, 10.0) == 0.0
    print("music_video_drift zero at anchor: OK")


def test_drift_compute_50ms_exact():
    # at=10.050, anchor=10.000 -> 50ms exactly (boundary ok)
    assert compute_drift_ms(10.050, 10.000) == 50.0
    print("music_video_drift 50ms exact: OK")


def test_drift_check_in_bounds():
    drift, err = check_drift(10.020, 10.000)
    assert drift == 20.0
    assert err is None
    print("music_video_drift in-bounds: OK")


def test_drift_check_out_of_bounds_descriptive_error():
    drift, err = check_drift(10.084, 10.000)
    assert drift == 84.0
    assert err is not None
    assert "84" in err and "50" in err and "10.08" in err and "10.00" in err
    print("music_video_drift out-of-bounds message: OK")


def test_drift_check_default_limit_is_50ms():
    drift, err = check_drift(11.060, 11.000)
    assert drift == 60.0
    assert err is not None  # default limit is 50
    # Custom limit accepts it
    drift, err = check_drift(11.060, 11.000, max_drift_ms=100)
    assert err is None
    print("music_video_drift default limit: OK")


def test_default_constant_matches_pipeline_manifest():
    # pipeline_defs/music-video-anime.yaml:beat_anchor_policy.max_drift_ms = 50
    assert DEFAULT_MAX_DRIFT_MS == 50
    print("music_video_drift constant: OK")


if __name__ == "__main__":
    test_adapt_asset_manifest_schema_form_to_tool_form()
    test_adapt_asset_manifest_passes_through_tool_form()
    test_adapt_edit_decisions_schema_form_to_tool_form()
    test_adapt_one_call_combined()
    test_scene_id_pattern()
    test_asset_id_pattern()
    test_cut_id_pattern()
    test_music_video_id_dispatch()
    test_drift_compute_zero_at_anchor()
    test_drift_compute_50ms_exact()
    test_drift_check_in_bounds()
    test_drift_check_out_of_bounds_descriptive_error()
    test_drift_check_default_limit_is_50ms()
    test_default_constant_matches_pipeline_manifest()
    print()
    print("ALL M-7 helper tests passed.")
