# Edit Director — Music Video Anime Pipeline

## When To Use

You are the **Edit Director** for a beat-synced anime music video. Your job is to take `scene_plan` + `asset_manifest` and produce `edit_decisions` — the actual timeline the renderer will execute.

For AMV, the edit IS the beat grid. Every cut lands on a beat. There is no "creative editing judgment" the way cinematic has — the beats tell you when to cut, the assets tell you what to show. Your job is to make sure no cut drifts off-beat, no runtime gets silently swapped, and no transition vocabulary gets out of hand.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/edit_decisions.schema.json` (extended) | Artifact validation |
| Prior artifact | `music_video_scene_plan` | Beat-anchored scene list |
| Prior artifact | `music_video_asset_manifest` | Acquired assets per scene |
| Prior artifact | `music_video_proposal_packet` | Locked render_runtime = "hyperframes" |
| Prior artifact | `music_video_brief` | audiomap.json path |
| Tool | `tools/analysis/beat_anchor.py` | Verify beat anchor positions |

## Process

### 1. Verify The Runtime Lock

Read `proposal_packet.production_plan.render_runtime`. It MUST be `"hyperframes"`. If it's anything else (Remotion, FFmpeg), STOP — the proposal stage made an error, escalate to the user. The runtime lock on this pipeline is binding.

Record `edit_decisions.render_runtime = "hyperframes"` immediately. This field is checked by compose-director.

### 2. Build The Cut List

For each scene in `scene_plan.scenes[]`, produce one cut in `edit_decisions.cuts[]`:

```yaml
- cut_id: c001
  scene_id: s001
  asset_id: a001
  asset_path: projects/<project-id>/assets/clips/s001.mp4
  at_seconds: 0.0        # = scene.beat_anchor.t_seconds
  duration_seconds: 1.20  # = scene.end_seconds - scene.start_seconds
  beat_anchor:            # mirror from scene_plan
    type: on_beat
    t_seconds: 0.0
    source: audiomap.beats_sec[0]
  transition_in: hard_cut
  transition_out: hard_cut
  trim:
    asset_in_seconds: 0.0   # where in the source asset to start reading
    asset_out_seconds: 1.20 # where in the source asset to stop reading
  motion:
    type: static | ken_burns_in | ken_burns_out
    intensity: 0.0-1.0      # for ken_burns
  overlay:
    text: null | "subtitle text"
    at_seconds_within_cut: 0.0
    duration_seconds_within_cut: 1.20
    style: karaoke | impact | title
  rationale: "Cut on beat 0; opens with static shot, hard-cut to next beat"
```

### 3. Drift Check (THE CRITICAL STEP)

For each cut, verify:

```
cut.at_seconds == cut.beat_anchor.t_seconds   # exact
abs(cut.at_seconds - cut.beat_anchor.t_seconds) <= 0.050   # 50ms drift budget
```

If any cut drifts more than 50ms, **adjust the cut's `at_seconds`** to match the anchor. Do not change the anchor to match the cut — the beat grid is the source of truth.

### 4. Continuity Check

Verify cuts tile the music with no gaps or overlaps:

```
cuts[0].at_seconds == 0.0
cuts[i+1].at_seconds == cuts[i].at_seconds + cuts[i].duration_seconds  # for all i
cuts[-1].at_seconds + cuts[-1].duration_seconds == audiomap.audio.duration_sec  # ±200ms
```

If there's a gap, either:
- A previous cut is too short → extend it (still on-beat)
- The next cut starts late → snap it to the next beat

If there's an overlap, the next cut starts before the previous ends → check if intentional (crossfade) or trim.

### 5. Transition Vocabulary Check

Count distinct transition values across all cuts:

- `transition_in` values used: should be a small set
- `transition_out` values used: should be a small set

If the union of distinct values > 4, log a warning. AMV is usually 95% `hard_cut` + 1-2 hero accents (`flash_white`, `freeze_frame`).

### 6. Asset-to-Cut Trim Mapping

For each cut, compute the asset trim window:

```
asset_in_seconds  = scene.start_seconds % asset.duration_seconds
asset_out_seconds = asset_in_seconds + cut.duration_seconds
```

If `asset_out_seconds > asset.duration_seconds`, the asset is too short → either loop it (with crossfade) or replace the asset.

For ai_generated assets, the asset is already the exact length needed (you specified duration_seconds when generating). For video_downloader assets, you'll need to find a sub-clip within the downloaded source.

### 7. Motion Treatment Distribution

For `kinetic-burst` motion register:

- 80%+ cuts: `static` (no internal motion; the cut itself is the motion)
- 10-15% cuts: `ken_burns_in` with low intensity (0.1-0.3)
- Hero cuts only: `ken_burns_in` with higher intensity (0.5)

For `phrase-led` motion register:

- 40-60% cuts: `ken_burns_in` (motion registers the held shot)
- Rest: `static`

For `hybrid-burst`: mix per section per `script.motion_register_for_section`.

### 8. Record The Edit Decisions

```json
{
  "version": "1.0",
  "render_runtime": "hyperframes",
  "music_track": {
    "path": "projects/<project-id>/assets/music/<file>",
    "duration_seconds": <from audiomap>,
    "audiomap_path": "projects/<project-id>/artifacts/audiomap.json"
  },
  "cuts": [
    {
      "cut_id": "c001",
      "scene_id": "s001",
      "asset_id": "a001",
      "asset_path": "projects/<project-id>/assets/clips/s001.mp4",
      "at_seconds": 0.0,
      "duration_seconds": 1.20,
      "beat_anchor": {
        "type": "on_beat",
        "t_seconds": 0.0,
        "source": "audiomap.beats_sec[0]"
      },
      "drift_ms": 0,
      "transition_in": "hard_cut",
      "transition_out": "hard_cut",
      "trim": {
        "asset_in_seconds": 0.0,
        "asset_out_seconds": 1.20
      },
      "motion": {
        "type": "static",
        "intensity": 0.0
      },
      "overlay": null,
      "rationale": "Cut on beat 0 (intro); opens with static establishing shot"
    }
  ],
  "metadata": {
    "total_cuts": <int>,
    "total_duration_seconds": <float>,
    "transition_vocabulary_used": ["hard_cut", "flash_white"],
    "motion_distribution": {
      "static": <int>,
      "ken_burns_in": <int>,
      "freeze_frame": <int>
    },
    "drift_check_passed": true,
    "max_drift_ms_observed": <int>,
    "beat_grid_reliable": <bool>,
    "register": "kinetic-burst" | "phrase-led" | "hybrid-burst"
  }
}
```

### 9. Quality Gate

- `render_runtime == "hyperframes"` (binding lock from proposal)
- Every cut has a non-null `beat_anchor`
- `drift_ms <= 50` for every cut
- Cuts tile the music (no gaps > 100ms; no overlaps > 100ms unless intentional)
- `total_duration_seconds` matches music duration within 200ms
- `transition_vocabulary_used` has at most 4 distinct values
- `drift_check_passed == true`
- Cut count is within ±20% of `script.metadata.scene_count_total`

## Common Pitfalls

- Setting `render_runtime` to anything other than `hyperframes`. The runtime lock forbids it.
- Letting a cut drift because the asset doesn't quite reach the next beat. Snap to the next beat; trim the asset; do NOT drift.
- Using `slow_dissolve` because it "looks cinematic". AMV is not cinematic. Use hard cut.
- Trimming an asset to wrong in/out points. If the scene shows character A at start and character B at end, the trim window must show A, not B-then-A.
- Forgetting the drift check. This is the #1 AMV quality failure mode. Always run it.
- Adding motion treatment to too many cuts. 80%+ should be static for kinetic-burst.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: false` for AMV — the edit is largely deterministic from scene_plan, so the user approved the structure at scene_plan stage). After review passes:
checkpoint with `status="complete"` (skip awaiting_human unless drift_check_passed is false), present the cut list summary (count, drift stats, transition vocabulary), and **END YOUR TURN**.
If drift_check_passed is false, gate on human approval and surface the off-beat cuts.