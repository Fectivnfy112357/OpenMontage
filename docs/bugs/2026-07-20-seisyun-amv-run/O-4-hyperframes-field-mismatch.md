# O-4: hyperframes_compose field names don't match music_video_* schemas

**Severity**: P1
**Layer**: Platform (HyperFrames tool family)
**Affects**: Every pipeline using `hyperframes_compose` directly (music-video-anime, plus any pipeline routed through HyperFrames)
**Status**: Confirmed by GitHub issue #306
**GitHub Issue**: #306 (HyperFrames style bridge reads typography.heading and motion.pace from non-schema keys)

## Symptom

`hyperframes_compose.execute({operation: "render", ...})` fails or produces empty output when called with schema-compliant `edit_decisions` and `asset_manifest` artifacts:

```
Scaffold failed: edit_decisions with non-empty cuts[] is required for scaffold_workspace
```

Even when `edit_decisions` and `asset_manifest` are passed with non-empty `cuts[]` and `entries[]`, the tool internally maps the wrong field names:

```python
# tools/video/hyperframes_compose.py line 484-488 (current source)
resolved_cuts, asset_copies = self._resolve_and_stage_assets(
    edit_decisions.get("cuts", []),
    asset_manifest.get("assets", []),   # ← expects key "assets"
    workspace,
)
```

But the `music_video_asset_manifest` schema requires key `entries`, not `assets`. The tool's lookup:

```python
asset_lookup = {a["id"]: a for a in assets if "id" in a}   # ← expects key "id"
```

But `music_video_asset_manifest` schema requires `asset_id`, not `id`. Asset paths are never resolved, so all cuts render with no source.

## Reproduction

```python
from tools.video.hyperframes_compose import HyperFramesCompose
t = HyperFramesCompose()

# Schema-compliant input:
adapted_ed = {
    "cuts": [{"id": "c001", "source": "/path/to/clip.mp4", "at_seconds": 0, ...}],
    ...
}
adapted_am = {
    "assets": [{"id": "a001", "path": "/path/to/clip.mp4", ...}],
    ...
}

r = t.execute({
    "operation": "scaffold_workspace",
    "workspace_path": "...",
    "edit_decisions": adapted_ed,
    "asset_manifest": adapted_am,
})
# scaffold.data["cut_count"] == 100 BUT all asset_copies empty
# because asset_lookup is empty (key "id" not "asset_id")
```

When using **schema-compliant** field names (`asset_id`, `entries`):

```python
schema_compliant_am = {
    "entries": [{"asset_id": "a001", "path": "/path/to/clip.mp4", ...}],
    ...
}
# Tool fails: KeyError on "assets" or empty asset_lookup
```

## Root Cause

Two contracts exist independently:

1. **Tool internal API**: `asset_manifest["assets"][].{id, path, license, duration_seconds}` + `edit_decisions["cuts"][].{id, source, at_seconds, ...}`
2. **Music-video schema API**: `asset_manifest["entries"][].{asset_id, path, license, duration_seconds, ...}` + `edit_decisions["cuts"][].{cut_id, scene_id, asset_id, asset_path, ...}`

Neither side documents this mismatch. Agents must hand-translate field names to use the tool — confirmed by the `projects/seisyun-amv/scripts/render_v2.py` `adapted_ed` / `adapted_am` adapters:

```python
adapted_ed = {"metadata": {...}, "cuts": [{"id": c["cut_id"], "source": c["asset_path"], ...}]}
adapted_am = {"assets": [{"id": e["asset_id"], "path": e["path"], ...}]}
```

## Evidence

- GitHub issue #306: "HyperFrames style bridge reads typography.heading and motion.pace from non-schema keys (both silently drop to fallback)"
  - Same family of bug: HyperFrames tool reads from keys that don't exist in the documented schema
- Live error during 2026-07-20 run: tool called with `asset_manifest.get("assets", [])` returned `[]` because input had `entries`
- `lib/hyperframes_style_bridge.py` (issue #306) shows precedent for tool-side key-name errors that don't match schema

## Impact

- Agents **must** write adapter shims to call `hyperframes_compose` from music-video-anime artifacts
- Schema-compliant artifacts are unusable as-is
- Increases error surface: ~30 minutes of debug time per run for an adapter that should be auto-generated

## Fix

**Option A (preferred)**: change `hyperframes_compose.py` to accept **both** the music-video-anime schema fields AND its own internal fields:

```python
def _resolve_and_stage_assets(self, cuts, assets, workspace):
    # Accept either key naming convention
    normalized = []
    for a in assets:
        normalized.append({
            "id": a.get("id") or a.get("asset_id"),
            "path": a.get("path"),
            "license": a.get("license"),
            "duration_seconds": a.get("duration_seconds"),
            **{k: v for k, v in a.items() if k not in {"id", "asset_id", "path"}},
        })
    asset_lookup = {a["id"]: a for a in normalized}
    ...
```

**Option B**: document the tool's expected schema as canonical, and update all music-video-* schemas to match (`asset_id` → `id`, `entries` → `assets`). This breaks already-shipped artifacts.

**Option C (least churn)**: add a tool-side `input_schema` document and a normalizer function; agents keep their adapters but a future `lib/hyperframes_normalizer.py` centralizes the mapping.

## Verification

1. Write integration test `tests/video/test_hyperframes_compose.py::test_accepts_music_video_schema_input`
2. Call `scaffold_workspace` with `asset_manifest["entries"]` containing `asset_id` fields
3. Assert `scaffold.data["asset_copies"]` is non-empty (proves field resolution worked)

## Related

- O-5 (empty timeline generation) — same tool family
- O-6 (path resolution bug) — same tool family
- Issue #306 (style bridge key mismatch) — precedent for tool-side key bugs
- M-7 (missing pipeline helper scripts) — the adapter shim agents write should be canonicalized into `lib/pipelines/music_video_helpers.py`

## Workaround Applied This Run

Agent wrote a 30-line `adapted_ed` / `adapted_am` mapper inline in `projects/seisyun-amv/scripts/render_v2.py`.