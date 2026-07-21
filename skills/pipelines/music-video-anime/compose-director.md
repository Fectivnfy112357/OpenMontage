# Compose Director — Music Video Anime Pipeline

## When To Use

You are the **Compose Director** for a beat-synced anime music video. Your job is to render `edit_decisions` through the locked runtime (`hyperframes`) and verify the output actually looks beat-synced.

This is the last stage. The output is `projects/<project-id>/renders/final.mp4`.

## Runtime Lock (HARD RULE)

`pipeline_defs/music-video-anime.yaml:runtime_lock` declares:

```yaml
runtime_lock:
  render_runtime: hyperframes
  allow_swap: false
```

**Only `hyperframes_compose` is a valid render tool on this pipeline.** Do NOT call `video_compose` (which dispatches to Remotion / FFmpeg based on `edit_decisions.render_runtime`). Do NOT call FFmpeg directly for the final render. Use `hyperframes_compose`.

If `edit_decisions.render_runtime != "hyperframes"`, STOP. Surface the manifest inconsistency to the user.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json` | Artifact validation |
| Prior artifact | `music_video_edit_decisions` | The cut list to render |
| Prior artifact | `music_video_asset_manifest` | Asset paths referenced by cuts |
| Prior artifact | `music_video_proposal_packet` | runtime_lock confirmation |
| Tool | `tools/video/hyperframes_compose.py` | The renderer (auto-emits beat-anchored timeline as of M-5 fix) |
| Tool | `tools/audio/audio_mixer.py` | Optional audio bed mixing |
| Tool | `tools/analysis/beat_anchor.py` | Beat sync verification post-render |
| Layer 3 | `.agents/skills/hyperframes-core/references/sub-compositions.md` | Required reading: media-must-be-direct-child-of-#root rule |

## Process

### 0. Preflight — Confirm HyperFrames Is Available AND Music Is Cleared

Run:

```bash
npx hyperframes doctor
npx hyperframes --version
```

If `hyperframes` is not installed or reports errors, STOP. Surface to the user per AGENT_GUIDE → "Escalate Blockers Explicitly". Do not silently substitute with `video_compose` (Remotion/FFmpeg).

Then verify the music source is properly acknowledged. Read `music_video_brief.metadata.music_track_*`:

| condition | action |
|---|---|
| `music_track_source == "ytsearch_artist_track"` AND `music_track_user_ack_obtained != true` | STOP. The user must explicitly ack the license at research stage before compose. Re-prompt them. |
| `music_track_source == "ytsearch_artist_track"` AND `music_track_user_ack_obtained == true` | OK. Record the ack in render_report.metadata.user_ack_chain. |
| `music_track_source in ("user_provided", "video_downloader_url")` | OK. No ack required. |
| `music_track_source` missing | STOP. Brief is malformed. Re-run research. |

### 1. Build The HyperFrames Project

HyperFrames renders HTML/GSAP compositions. You need to build a project structure:

```
projects/<project-id>/renders/
├── hyperframes-project/
│   ├── hyperframes.json          # project manifest
│   ├── public/
│   │   ├── assets/
│   │   │   ├── music.mp3         # the locked music track
│   │   │   ├── clips/            # all the cut assets
│   │   │   └── overlays/         # subtitle text assets if any
│   ├── compositions/
│   │   └── timeline.html         # the composition
│   └── renders/
│       └── final.mp4             # output target
```

`hyperframes_compose` has a helper to scaffold this from `edit_decisions`. Read its input schema before calling.

### 2. Generate The Timeline Composition

The timeline composition is HTML + GSAP that:

- Loads the music track as the audio bed
- Iterates through cuts in order
- At each `cut.at_seconds`, swaps the displayed video/frame
- Applies `cut.motion` (ken_burns etc.) within the cut
- Applies `cut.transition_in` / `transition_out` at the cut boundaries
- Renders `cut.overlay` text if present

Use `hyperframes_compose.execute()` with:

```python
{
    "edit_decisions": edit_decisions_dict,
    "asset_manifest": asset_manifest_dict,
    "music_path": "<track path>",
    "output_path": "projects/<project-id>/renders/final.mp4",
    "fps": 30,
    "render_quality": "draft" | "production"   # start with draft for fast iteration
}
```

**M-5 fix note (2026-07-21)**: as of this writing, `tools/video/hyperframes_compose.py`
**generates the proper beat-anchored timeline automatically** from
`edit_decisions.cuts[].{at_seconds, duration_seconds}` — it emits
`<video class="clip">` elements with `data-start`/`data-duration` attributes
plus a GSAP main timeline that switches each cut's `opacity` at the boundary.
No agent-side rewriting of `workspace/index.html` is required.

**O-4 fix note (2026-07-21)**: `hyperframes_compose` now accepts both
`asset_manifest["assets"][]` (tool's internal API) and
`asset_manifest["entries"][]` (music_video_asset_manifest schema, keyed by
`asset_id`), normalizing internally via `_coerce_asset_entries`. Schema-compliant
inputs work without an adapter shim.

If the generated `workspace/index.html` does NOT contain a non-empty GSAP main
timeline referencing each cut's `at_seconds`, STOP and surface a hyperframes
bug — do not silently paper over it with a hand-written timeline.

### 3. Run Lint And Validate Before Render

```bash
cd projects/<project-id>/renders/hyperframes-project
npx hyperframes lint .
npx hyperframes validate .   # headless Chrome validation, catches JS errors
```

If `validate` reports JS errors, debug the timeline.html. Common errors:
- Asset path 404 (typo or missing file)
- GSAP timeline overflow (cut duration > asset duration)
- Off-anchor cut (start_seconds drift)

Do NOT proceed to render until `validate` exits 0.

### 4. Render The MP4

```bash
cd projects/<project-id>/renders/hyperframes-project
npx hyperframes render . --skill=music-video-anime -q draft -o renders/final.mp4 --fps 30
```

Start with `-q draft` (fast) for first iteration. Switch to `-q production` only after beat sync is verified.

For a 90-second AMV at 30fps, draft render typically takes 30-90 seconds; production takes 2-5 minutes.

### 5. Verify Beat Sync (MANDATORY)

This is what makes it an AMV and not just a slideshow. After render:

1. Extract 5-10 frame samples at known downbeat timestamps:
   ```bash
   ffmpeg -i renders/final.mp4 -vf "select='eq(n\,0)+eq(n\,15)+eq(n\,30)+eq(n\,45)+eq(n\,60)+eq(n\,75)+eq(n\,90)+eq(n\,105)+eq(n\,120)+eq(n\,150)'" -vsync vfr frames/frame_%03d.png
   ```

2. Run `beat_anchor.py` on the rendered MP4's audio track to verify the audio is intact and not drifted:
   ```bash
   python -m tools.analysis.beat_anchor <music track> -o /tmp/audiomap_render.json
   python -m tools.analysis.beat_anchor renders/final.mp4 -o /tmp/audiomap_render.json
   # Compare: the rendered audiomap should match the source audiomap within 200ms
   ```

3. Inspect frames at each downbeat. The visual content MUST change at each downbeat (within the cut's duration).

If beat sync is off (frame at downbeat shows the same content as frame before downbeat), debug:

- The cut's `at_seconds` drifted from `beat_anchor.t_seconds` → edit-director drift bug
- The asset trim window is wrong → asset-director trim bug
- The renderer mis-handled the cut boundary → timeline.html bug

Do NOT declare success until beat sync is verified.

### 6. Optional: Audio Bed Mixing

Music tracks usually do NOT need normalization — they are already mastered for playback. The audio_mixer is typically a no-op on this pipeline.

When to use it (rare):

- Source audio has noticeable intro/outro silence > 1 second
- Source audio is much louder or quieter than the platform target (e.g. above -6 LUFS or below -20 LUFS)
- User explicitly asked for a fade-in / fade-out

When NOT to use it:

- Music track sounds fine as-is (the common case)
- Adding normalization risks introducing artifacts on already-mastered music

If you skip mixing, **set `music_video_render_report.audio_post_processing.music_mixed = false`** AND **`explicit_skip_with_reason`** with a non-empty string explaining why. The schema enforces this — empty/null reason is rejected.

If you DO mix, record `pre_mix_lufs` and `post_mix_lufs` from the audio_mixer output so reviewers can verify the normalization was reasonable.

```python
from tools.audio.audio_mixer import AudioMixer
AudioMixer().execute({
    "input_path": "projects/<project-id>/renders/final.mp4",
    "operations": [
        {"type": "normalize", "target_db": -14},
        {"type": "fade_in", "start_seconds": 0, "duration_seconds": 0.5},
        {"type": "fade_out", "start_seconds": music_duration - 1.0, "duration_seconds": 1.0}
    ],
    "output_path": "projects/<project-id>/renders/final_mixed.mp4"
})
```

Optional — only needed if the raw render has audio issues.

### 7. Record The Render Report

The `music_video_render_report` schema (`schemas/artifacts/music_video_render_report.schema.json`)
validates this artifact. **M-3 fix (2026-07-21)**: `render_runtime` is now an
enum with `["hyperframes", "ffmpeg", "remotion"]` (no longer `const hyperframes`).
If `render_runtime != "hyperframes"`, you MUST populate the `runtime_swap` object
with `exception_clause_invoked=true` AND `user_authorized_at=<ISO timestamp>`
otherwise validation fails. The runtime lock forbids swap without authorization,
so the `runtime_swap` field is the canonical record of the exception clause
invocation (per `pipeline_defs/music-video-anime.yaml:runtime_lock` lines 64-71).

```json
{
  "version": "1.0",
  "render_runtime": "hyperframes",
  "output_path": "projects/<project-id>/renders/final.mp4",
  "music_track": {
    "path": "projects/<project-id>/assets/music/<file>",
    "duration_seconds": <float>,
    "audiomap_path": "projects/<project-id>/artifacts/audiomap.json",
    "rendered_audiomap_match_ms": <max drift between source and rendered audiomap>
  },
  "rendering": {
    "tool": "hyperframes_compose",
    "tool_version": "<from npx hyperframes --version>",
    "quality": "draft" | "production",
    "fps": 30,
    "render_duration_seconds": <wall time spent rendering>,
    "wall_clock_started_at": "<ISO 8601>",
    "wall_clock_completed_at": "<ISO 8601>"
  },
  "validation": {
    "hyperframes_lint_passed": true,
    "hyperframes_validate_passed": true,
    "ffprobe_passed": true,
    "duration_seconds": <float>,
    "resolution": "1920x1080",
    "has_audio": true,
    "video_codec": "h264",
    "audio_codec": "aac"
  },
  "beat_sync_verification": {
    "frames_sampled_at": ["12.34", "24.68", "37.02", "49.36", "61.70"],
    "all_downbeats_show_visual_change": true,
    "rendered_audiomap_drift_ms_max": <int>,
    "verification_passed": true
  },
  "runtime_swap_detected": false,
  "silent_fallback_used": false,
  "metadata": {
    "hyperframes_compose_version": "<version>",
    "asset_count_used": <int>,
    "cut_count_rendered": <int>,
    "hero_scene_count": <int>
  }
}
```

If a documented swap happened, add:

```json
"runtime_swap": {
  "exception_clause_invoked": true,
  "from_runtime": "hyperframes",
  "to_runtime": "ffmpeg",
  "user_authorized_at": "<ISO timestamp when user approved the swap>",
  "reason": "<why hyperframes failed>",
  "hyperframes_attempted_versions": ["vN.N.N"],
  "hyperframes_failure_mode": "<error message excerpt>"
}
```

### 8. Quality Gate

- `render_runtime == "hyperframes"` (runtime lock)
- `runtime_swap_detected == false` (no silent swap to another runtime)
- `silent_fallback_used == false`
- `validation.hyperframes_lint_passed == true`
- `validation.hyperframes_validate_passed == true`
- `validation.ffprobe_passed == true`
- `validation.duration_seconds` matches music duration within 200ms
- `beat_sync_verification.verification_passed == true`
- `beat_sync_verification.rendered_audiomap_drift_ms_max <= 200`
- Output file exists and is non-zero

## Common Pitfalls

- Calling `video_compose` because it's "the general renderer". On this pipeline, only `hyperframes_compose` is allowed. `video_compose` dispatches to Remotion/FFmpeg based on `edit_decisions.render_runtime`, but even with `render_runtime=hyperframes`, `video_compose` may not invoke the same path as `hyperframes_compose`. Use the dedicated tool.
- Skipping `npx hyperframes validate`. JS errors in the timeline composition only show up in headless Chrome.
- Rendering directly to production quality on first try. Use `draft` for iteration.
- Declaring success without beat sync verification. Visual frame inspection at downbeats is mandatory.
- Forgetting to record `runtime_swap_detected: false`. The reviewer checks this field for governance violations.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: false` for AMV). After review passes:
checkpoint with `status="complete"`, present the render summary (output path, duration, beat sync verification, render time), and **END YOUR TURN**.

If `beat_sync_verification.verification_passed == false`, gate on human approval and surface the off-beat frames — the user may want to re-edit or accept the imperfect sync.