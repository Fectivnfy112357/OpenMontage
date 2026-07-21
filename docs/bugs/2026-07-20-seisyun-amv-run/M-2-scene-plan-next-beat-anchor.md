# M-2: `music_video_scene_plan` `next_beat_anchor` inconsistent

**Severity**: P2
**Layer**: Pipeline schema (music-video-anime)
**Affects**: scene_plan generation
**Status**: Confirmed
**GitHub Issue**: None — recommend filing

## Symptom

Schema validation error: `'None is not of type 'object''` at `path: ['scenes', N, 'next_beat_anchor']` for the last scene in a cut list.

## Reproduction

```python
import json, jsonschema
schema = json.loads(open("schemas/artifacts/music_video_scene_plan.schema.json").read())
plan = {
    "version": "1.0",
    "scenes": [
        {
            "id": "s001",
            "type": "broll",
            "description": "...",
            "start_seconds": 0.61,
            "end_seconds": 1.50,
            "beat_anchor": {"type": "phrase_start", "t_seconds": 0.61, "source": "..."},
            "next_beat_anchor": None,   # ← last scene has no next
            "required_assets": ["video_clip"],
            "subject": {"type": "character", "identifiers": [...]},
            "drift_ms": 0,
        },
        ...
    ],
    "metadata": {...},
}
jsonschema.validate(plan, schema)
# ValidationError: None is not of type 'object' at scenes/0/next_beat_anchor
```

## Root Cause

`schemas/artifacts/music_video_scene_plan.schema.json` line 95-97:

```json
"next_beat_anchor": {
    "type": "object",
    ...
}
```

The field is described in `skills/pipelines/music-video-anime/scene-director.md` line 130-135 as:

> "next_beat_anchor: Anchor for the next scene (used to compute this scene's end_seconds). **Optional but recommended.**"

But the schema has `"type": "object"` without `["object", "null"]`, so `None` fails.

## Evidence

- Live error during 2026-07-20 run
- Director doc says "optional", schema is strict — internal contradiction in pipeline's own specs

## Impact

- Agents must set `next_beat_anchor` for every scene, even the last one (which has no next)
- The "last scene anchor at music duration" workaround is intuitive but undocumented

## Fix

Change schema:

```json
"next_beat_anchor": {
    "type": ["object", "null"],   // accept None
    ...
}
```

And update director doc to clarify:

> "Optional except for the LAST scene, which should set `next_beat_anchor` to a phrase_end anchor at `audiomap.audio.duration_sec`."

## Verification

1. Write test `tests/schemas/test_music_video_scene_plan.py::test_last_scene_with_null_next_anchor_validates`
2. Construct plan with `scenes[-1].next_beat_anchor = None`
3. Assert validation passes (after schema fix)
4. Currently fails → captures the bug

## Related

- M-1 (script schema field errors)
- M-3 (render_report over-constrains)
- M-8 (brief schema incomplete vs director doc)

## Workaround Applied This Run

Agent set `scenes[-1].next_beat_anchor = {"type": "phrase_end", "t_seconds": audio_duration, "source": "audiomap.audio.duration_sec"}`.