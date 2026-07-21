"""Regression test: HyperFramesCompose must coerce schema-form cuts
(cut_id + asset_path) into tool-form (id + source) so music-video-anime
runs do not fall through to the text-card placeholder.

Before M-10 fix (2026-07-21): _resolve_and_stage_assets read
``cut.get("source", "")`` which returned "" for every schema-compliant
music_video_edit_decisions cut (schema's additionalProperties:false
forbids injecting source directly). All 107 cuts rendered as
``<div class="clip text-card"><h1>Scene N</h1></div>``.

After fix: _coerce_cuts mirrors _coerce_asset_entries, deriving source
from asset_path (preferred) or asset_id (resolved via asset_lookup).
Original fields are preserved so the schema is still satisfied.
"""

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.video.hyperframes_compose import HyperFramesCompose  # noqa: E402


def test_coerce_cuts_schema_form_to_tool_form():
    schema_cuts = [
        {
            "cut_id": "c001",
            "scene_id": "s001",
            "asset_id": "a001",
            "asset_path": "/tmp/a.mp4",
            "at_seconds": 0.0,
            "duration_seconds": 2.0,
        }
    ]
    out = HyperFramesCompose._coerce_cuts(schema_cuts)
    assert out[0]["id"] == "c001"
    assert out[0]["source"] == "/tmp/a.mp4"
    # Originals preserved so JSON dump still passes schema validation
    assert out[0]["cut_id"] == "c001"
    assert out[0]["asset_id"] == "a001"
    assert out[0]["asset_path"] == "/tmp/a.mp4"


def test_coerce_cuts_tool_form_is_idempotent():
    """Tool-form input (id + source already present) must pass through unchanged."""
    tool_cuts = [{"id": "c001", "source": "/x.mp4"}]
    out = HyperFramesCompose._coerce_cuts(tool_cuts)
    assert out[0]["id"] == "c001"
    assert out[0]["source"] == "/x.mp4"


def test_coerce_cuts_falls_back_to_asset_id_when_no_path():
    """asset_id-only cuts get source=asset_id; resolution happens later
    in _resolve_and_stage_assets via the asset_lookup dict."""
    cuts = [{"cut_id": "c001", "asset_id": "a001"}]
    out = HyperFramesCompose._coerce_cuts(cuts)
    assert out[0]["source"] == "a001"


def test_coerce_cuts_empty_input():
    assert HyperFramesCompose._coerce_cuts([]) == []
    assert HyperFramesCompose._coerce_cuts(None) == []


def test_resolve_and_stage_assets_resolves_schema_form_cuts():
    """End-to-end: schema-form cuts (asset_path) get resolved into
    workspace-relative source paths, NOT empty strings.

    Before M-10 fix this assertion failed: src_path was None and the
    caller fell through to the text-card placeholder.
    """
    tmp_path = Path(tempfile.mkdtemp())
    src = tmp_path / "incoming" / "clip.mp4"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"\x00" * 32)

    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "assets").mkdir(exist_ok=True)

    cuts = [
        {
            "cut_id": "c001",
            "scene_id": "s001",
            "asset_id": "a001",
            "asset_path": str(src),
            "at_seconds": 0.0,
            "duration_seconds": 2.0,
        }
    ]
    assets = [
        {"asset_id": "a001", "path": str(src), "license": "user_provided"},
    ]

    h = HyperFramesCompose()
    resolved, copies = h._resolve_and_stage_assets(cuts, assets, workspace)

    # The cut's source must be a real path that exists on disk
    assert resolved[0]["source"] != ""
    assert Path(resolved[0]["source"]).exists()
    # The file should have been staged into workspace/assets/
    assert any("clip.mp4" in c["to"] for c in copies)
    # Original schema fields are preserved
    assert resolved[0]["cut_id"] == "c001"
    assert resolved[0]["asset_path"] == str(src)


def test_resolve_and_stage_assets_resolves_asset_id_via_lookup():
    """When schema cut has only asset_id, source=asset_id then asset_lookup
    maps it to the asset path."""
    tmp_path = Path(tempfile.mkdtemp())
    src = tmp_path / "incoming" / "clip.mp4"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(b"\x00" * 32)

    workspace = tmp_path / "ws"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "assets").mkdir(exist_ok=True)

    cuts = [
        {"cut_id": "c001", "asset_id": "a001", "at_seconds": 0.0,
         "duration_seconds": 1.0}
    ]
    assets = [{"asset_id": "a001", "path": str(src)}]

    h = HyperFramesCompose()
    resolved, copies = h._resolve_and_stage_assets(cuts, assets, workspace)
    assert Path(resolved[0]["source"]).exists()


if __name__ == "__main__":
    test_coerce_cuts_schema_form_to_tool_form()
    test_coerce_cuts_tool_form_is_idempotent()
    test_coerce_cuts_falls_back_to_asset_id_when_no_path()
    test_coerce_cuts_empty_input()
    test_resolve_and_stage_assets_resolves_schema_form_cuts()
    test_resolve_and_stage_assets_resolves_asset_id_via_lookup()
    print("ALL M-10 regression tests passed.")