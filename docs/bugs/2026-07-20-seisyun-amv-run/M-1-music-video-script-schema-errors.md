# M-1: `music_video_script` schema field type errors

**Severity**: P2
**Layer**: Pipeline schema (music-video-anime)
**Affects**: Any agent that constructs `music_video_script` artifacts from beat analysis
**Status**: Confirmed
**GitHub Issue**: None — recommend filing

## Symptom

Three separate schema rejections during script construction:

1. `'on-beat-karaoke (lyrics synced to beat grid on chorus only)' is not one of ['on-beat-karaoke', 'sparse-on-impact', 'none']` — enum type strict; additional parenthetical text rejected.
2. `'sparse-on-impact (lyric subtitles on phrase boundaries only, no karaoke)' is not one of [...]` — same pattern.
3. `'target_cut_count' is a required property` — field declared in director doc but missing in schema.

## Reproduction

```python
import json, jsonschema
schema = json.loads(open("schemas/artifacts/music_video_script.schema.json").read())
script = {
    "version": "1.0",
    "title": "test",
    "total_duration_seconds": 177.0,
    "voice_performance": None,
    "sections": [{
        "id": "intro",
        "text": None,
        "start_seconds": 0.61,
        "end_seconds": 28.96,
        "music_section_type": "intro",
        "motion_register_for_section": "phrase-led",
        # target_cut_count missing
        "beat_anchor": {"type": "phrase_start", "t_seconds": 0.61, "rationale": "..."},
    }],
    "metadata": {
        "motion_register_global": "hybrid-burst",
        "audiomap_path": "...",
    },
}
jsonschema.validate(script, schema)
# ValidationError: 'target_cut_count' is a required property
```

## Root Cause

`schemas/artifacts/music_video_script.schema.json`:
- Line 46: `"target_cut_count": {"type": "integer", "minimum": 1}` is listed under `properties` but NOT in `required` (line 27). Either director doc says it's required, or schema should make it optional. Current state: agents don't know which is right.
- Line 30-31: `"typography"` enum is strict: `["on-beat-karaoke", "sparse-on-impact", "none"]` — agents writing descriptive text (e.g. `"on-beat-karaoke (lyrics on chorus only)"`) fail validation.

## Evidence

- Live errors during 2026-07-20 run, captured in `projects/seisyun-amv/scripts/write_proposal.py` output
- Director doc `skills/pipelines/music-video-anime/script-director.md` line 84 says `target_cut_count: <int>` without `(required)` or `(optional)` marker
- Schema line 46: `target_cut_count` not in required list

## Impact

- Every agent must either:
  - Read both director doc + schema carefully (and discover the ambiguity)
  - Hit the error and retry
- Adds ~10-20 minutes of debug time per run
- Risk of silent semantic mismatch (cut density drift if schema enforcement is inconsistent)

## Fix

**Decision needed**: should `target_cut_count` be required or optional?

Recommendation: **required**, since the cut list depends on it (scene count = sum of all target_cut_count per section). Make schema match director:

```json
// In section items.required (line 27)
"required": ["id", "text", "start_seconds", "end_seconds", "music_section_type", "beat_anchor", "target_cut_count"]
```

For `typography` enum, two options:

**A**: keep strict enum, agents must use bare values.

**B**: change type to `string` with `maxLength: 100` to allow descriptive suffixes.

Recommendation: **A** (strict enum). Agents should put descriptive text in `description` or `metadata.typography_notes` field instead.

## Verification

1. Write test `tests/schemas/test_music_video_script.py::test_minimal_section_validates`
2. Construct minimal section with all required fields
3. Assert validation passes
4. Repeat with `target_cut_count` missing → should fail (proves required enforcement works)

## Related

- M-2 (scene_plan schema inconsistency)
- M-3 (render_report over-constrains runtime)
- M-8 (brief schema incomplete vs director doc)

## Workaround Applied This Run

Agent:
1. Stripped parenthetical text from `typography` enum values
2. Provided `target_cut_count` in every section (even when redundant)
3. Worked through schema in trial-and-error