# M-8: `music_video_brief` schema incomplete vs director doc

**Severity**: P3
**Layer**: Pipeline schema (music-video-anime)
**Affects**: research stage output
**Status**: Confirmed
**GitHub Issue**: None — recommend filing

## Symptom

`skills/pipelines/music-video-anime/research-director.md` Step 8 ("Record The Research Brief") lists the following as required metadata fields:

- `music_track_path`
- `music_track_duration_seconds`
- `audiomap_path`
- `bpm`
- `beat_grid_reliable`
- `anime_theme` (with `explicit: true|false` and sub-fields)
- `asset_route_options`
- `third_party_footage_candidates`
- `visual_references`
- `global_user_ack_obtained`
- `global_user_ack_statement`
- `music_track_search_query`
- `music_track_youtube_video_id`
- `music_track_uploader`
- `music_track_publisher`
- `music_track_sha256`

But `schemas/artifacts/music_video_brief.schema.json` `metadata.properties` only lists a subset. Custom fields like `music_track_search_query` and `music_track_uploader` are not declared in schema.

Workaround: schema does not have `additionalProperties: false` at `metadata` level, so extra fields are accepted. But this means:
1. Agents don't know which fields are canonical vs ad-hoc
2. Downstream stages can't reliably consume them
3. Schema validation is permissive, allowing drift

## Reproduction

```python
import json, jsonschema
schema = json.loads(open("schemas/artifacts/music_video_brief.schema.json").read())
brief = {
    "version": "1.0",
    "title": "test",
    "hook": "...",
    "key_points": ["..."],
    "tone": "hybrid-burst",
    "style": "AMV",
    "target_platform": "generic",
    "target_duration_seconds": 177.0,
    "metadata": {
        "music_track_path": "/path/track.wav",
        "music_track_duration_seconds": 177.07,
        "music_track_source": "ytsearch_artist_track",
        "music_track_license": "user_requested",
        "music_track_requires_user_ack": True,
        "music_track_user_ack_obtained": True,
        "global_user_ack_obtained": True,
        # All these are NOT in schema but passed in:
        "audiomap_path": "...",
        "bpm": 127.1,
        "beat_grid_reliable": True,
        "anime_theme": {...},
        "music_track_search_query": "ytsearch:...",
        "music_track_youtube_video_id": "...",
        "music_track_uploader": "fox capture plan",
        "music_track_publisher": "Aniplex Inc.",
        "music_track_sha256": "...",
    },
}
jsonschema.validate(brief, schema)
# Passes (because additionalProperties is allowed at metadata level)
# But: schema doesn't know about audiomap_path, bpm, etc. as canonical fields
```

## Root Cause

Schema was written before director doc was finalized. Director doc lists more required fields than schema declares.

## Evidence

- `research-director.md` Step 8 vs `music_video_brief.schema.json` lines 38-163
- `metadata.properties` in schema lists: `music_track_path`, `music_track_duration_seconds`, `music_track_source`, `music_track_license`, `music_track_requires_user_ack`, `music_track_user_ack_obtained`, `global_user_ack_obtained`, `audiomap_path`, `bpm`, `beat_grid_reliable`, `anime_theme`, `asset_route_options`, `third_party_footage_candidates`, `visual_references`
- Missing from schema: `music_track_search_query`, `music_track_youtube_video_id`, `music_track_uploader`, `music_track_publisher`, `music_track_sha256`, `global_user_ack_statement`

## Impact

- Mild — schema validation passes due to `additionalProperties` not being false
- Field naming inconsistent between director doc and schema
- Future readers don't know which fields are stable contracts

## Fix

Update `schemas/artifacts/music_video_brief.schema.json` `metadata.properties`:

```json
"music_track_search_query": {"type": "string", "description": "ytsearch:<keywords> used to find the track"},
"music_track_youtube_video_id": {"type": "string"},
"music_track_uploader": {"type": "string"},
"music_track_publisher": {"type": "string"},
"music_track_sha256": {"type": "string", "description": "sha256 of music file for provenance"},
"global_user_ack_statement": {"type": "string"}
```

And add `required: ["music_track_path", ...]` for the additional fields that are truly required (per director doc wording).

## Verification

1. Write test `tests/schemas/test_music_video_brief.py::test_director_doc_fields_all_in_schema`
2. Read `research-director.md` Step 8, extract all `metadata.<field>` references
3. Assert each is declared in schema
4. Currently fails → captures the bug

## Related

- M-1 (script schema field errors) — same family: schema/director drift
- M-2 (scene_plan schema inconsistency) — same family
- M-7 (missing helper scripts) — would centralize "build brief" logic

## Workaround Applied This Run

Agent added all director-doc-referenced fields to the brief JSON, even though schema didn't validate them. Workaround was simple because `additionalProperties` is permissive at `metadata` level.