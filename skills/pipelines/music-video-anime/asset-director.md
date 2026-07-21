# Asset Director — Music Video Anime Pipeline

## When To Use

You are the **Asset Director** for a beat-synced anime music video. Your job is to provide exactly ONE visual asset per scene from `scene_plan`. The asset route is locked at the proposal stage; this stage EXECUTES that route, not decides it.

## Asset Route (USER-DEFINED, BINDING)

The user has explicitly defined this rule:

```
default route: video_downloader
  ├─ user provided URL → direct download, license="user_provided"
  └─ no URL → ytsearch:<keywords>, license="user_requested",
              requires_explicit_acknowledgment=true

ONLY when user said "用 AI 生成 / AI 画 / AI 出图":
  route: agnes_image + agnes_video
```

This is binding. Do NOT invert. If `proposal_packet.production_plan.asset_route == "video_downloader"`, use `video_downloader` for ALL assets unless the user added a hybrid clause explicitly.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` (extended with license fields) | Artifact validation |
| Prior artifact | `music_video_scene_plan` from Scene Director | The cut list with beat anchors |
| Prior artifact | `music_video_proposal_packet` from Proposal Director | Locked asset_route + selected concept |
| Prior artifact | `music_video_brief` | audiomap path + anime_theme + visual references |
| Tool | `tools/analysis/video_downloader.py` | For video_downloader route |
| Tool | `tools/graphics/agnes_image.py` | For ai_generation route (anime-tuned FLUX) |
| Tool | `tools/video/agnes_video.py` | For ai_generation route (anime-style video gen) |
| Layer 3 | `.agents/skills/agnes-media/SKILL.md` | Required reading before calling agnes tools |
| Layer 3 | `.agents/skills/yt-dlp/SKILL.md` or `video-download` reference | Required for video_downloader |

## Process

### 1. Read The Scene Plan And Identify Asset Slots

For each scene in `scene_plan.scenes[]`, determine the asset slot:

```yaml
scene_id: s001
required_assets: ["video_clip"]  # or ["image", "text_overlay"] etc.
asset_route: video_downloader | ai_generation   # from proposal
duration_seconds: scene.end - scene.start
subject: { type: character, identifiers: [sakurajima_mai, bunny_suit] }
hero_moment: false
```

### 2. Build Search / Generation Queries

For each scene slot, craft a query that captures the visual concept:

**For `video_downloader` route**:

- If user provided URLs → use them directly for the most relevant scenes (typically hero scenes)
- Otherwise → craft `ytsearch:<keywords>` query
  - keywords: `<anime title> <character/scenario keywords> AMV` (English for broadest search)
  - or: `ytsearch5:<anime romaji title> <scene keyword>` (5 results per call)
  - or for music-track-specific: `ytsearch3:<artist> <track title> AMV`

**For `ai_generation` route**:

- `image_prompt`: subject + anime_style_modifiers + scene_atmosphere
  - Example: `sakurajima mai from rascal does not dream of bunny girl senpai, walking through sunlit school hallway, soft pink light, anime style, cinematic lighting, 1080p`
  - Always include "anime style" or specific anime name for fidelity
- `video_prompt`: same + action
  - Example: same image prompt + `, walking slowly, hair swaying, subtle camera push-in`

Read `.agents/skills/agnes-media/SKILL.md` BEFORE generating. It has provider-specific prompting guidance (FLUX seed, negative_prompt, reference_image_url handling) that dramatically improves output.

### 3. License Tracking (MANDATORY)

For every asset, record in `asset_manifest.entries[].license`:

| License | When | `requires_user_ack` |
|---|---|---|
| `user_provided` | User gave a specific URL or dropped a file | `false` |
| `user_requested` | ytsearch:<keywords> result, no specific user URL | `true` |
| `ai_generated` | agnes_image or agnes_video produced it | `false` (no third-party IP) |
| `music_library` | Track from `music_library/` (this is for audio, not video — applies if reusing music) | `false` |

**`requires_user_ack=true` assets**: by default they inherit `music_video_brief.metadata.global_user_ack_obtained`. When the global flag is `true`, do **not** re-prompt per asset — set `user_ack_obtained=true` directly with `ack_source: "brief.global_user_ack_obtained"`. Only re-prompt when the global flag is `false` or absent.

### 4. Asset Acquisition — HARD ROUTE GATE

**Before any acquisition, READ `music_video_proposal_packet.production_plan.asset_route`.** This pipeline defaults to `video_downloader` (yt-dlp). Calling `AgnesImage` / `AgnesVideo` is a governance violation unless:

- `asset_route == "ai_generation"`, AND
- `music_video_brief.metadata.asset_route_options.agnes_opt_in == true`, AND
- The user explicitly said "用 AI 生成 / AI 画 / AI 出图" at proposal OR assets stage.

**If `asset_route == "video_downloader"` or `"hybrid"` and the AI clause above does NOT hold, do NOT import or call `AgnesImage` / `AgnesVideo`.** Acquire all assets via `video_downloader` (yt-dlp / ytsearch). This is binding — read the AGENT_GUIDE "Asset Route Decision (USER-DEFINED RULE)" rationale at the top of this skill before any tool call.

**Default acquisition path** (when `asset_route` is `video_downloader` or `hybrid` without AI opt-in):

```python
from tools.analysis.video_downloader import VideoDownloader

downloader = VideoDownloader()
result = downloader.execute({
    "url": "ytsearch5:<anime> <scene> AMV",  # ytsearch syntax is supported by yt-dlp
    "output_dir": "projects/<project-id>/assets/clips/",
    "format": "video",
    "max_resolution": "720p",   # AMV is usually 720p or below; full HD is overkill
    "max_duration_seconds": 600
})
```

Then trim the downloaded clip to match the scene's `end_seconds - start_seconds`. Use `video_trimmer`:

```python
from tools.video.video_trimmer import VideoTrimmer
trimmer = VideoTrimmer()
result = trimmer.execute({
    "input_path": downloaded_clip_path,
    "output_path": f"projects/<project-id>/assets/clips/{scene_id}.mp4",
    "start_seconds": <in-clip start>,
    "end_seconds": <in-clip end>
})
```

**AI path** (only when the gate above holds):

```python
from tools.graphics.agnes_image import AgnesImage
from tools.video.agnes_video import AgnesVideo

# Generate keyframe
image_result = AgnesImage().execute({
    "prompt": "<scene image prompt>",
    "aspect_ratio": "landscape",  # 16:9 for video
    "seed": <fixed seed for reproducibility>
})

# Generate video clip from keyframe (or use agnes_video keyframe mode)
video_result = AgnesVideo().execute({
    "prompt": "<scene video prompt>",
    "image_url": image_result.data["image_path"],  # keyframe-driven mode
    "duration_seconds": scene_duration,
    "seed": <fixed seed>
})
```

**Always pass a fixed seed** for reproducibility (per memory: "Reproducible video generation requires setting a fixed seed").

### 5. Quality Filtering

For each acquired asset, run a quick sanity check:

- File exists and is non-zero size
- `ffprobe` reports a valid video stream with reasonable duration (>= 80% of requested duration)
- For ai_generated: re-inspect the image; reject if it doesn't match the scene's subject identifiers

Failed assets get a retry pass with a different query / seed. After 2 retries, log the failure and surface to the user.

### 5a. Clip Re-Encoding For Dense Keyframes (M-4 fix)

After `video_trimmer` (Step 4) produces the per-scene trimmed clip, **re-encode every
trimmed clip** with `-g 30 -keyint_min 30` so HyperFrames' frame extraction has a
seek-safe GOP. Default `ffmpeg` output has a GOP of 5–10s; a trimmed 0.5–1s cut
may have only one keyframe or none, which causes HyperFrames render to abort with:

```
Video "cut-070" has sparse keyframes (max interval: 4.8s). This causes seek
failures and frame freezing.
Extracting video frames ... captured 14 of expected 15 frames (coverage 93.3%,
threshold 95.0%). aborting render to prevent shipping a wrong MP4.
```

Re-encode step (insert between Step 4 video_trimmer output and Step 5 sanity check):

```python
import subprocess
cmd = [
    "ffmpeg", "-y", "-i", str(trimmed_clip_path),
    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
    "-r", "30",
    "-g", "30", "-keyint_min", "30",   # one keyframe per second
    "-movflags", "+faststart",
    "-c:a", "copy",
    str(reencoded_clip_path),
]
subprocess.run(cmd, check=True)
```

Point `asset_manifest.entries[].path` at the re-encoded file, not the trimmer
output. Failed assets get a retry pass with a different query / seed. After 2
retries, log the failure and surface to the user.

**For very short clips (< 1s)** where the 95% coverage threshold is structurally
unreachable, set `HF_VIDEO_COVERAGE_THRESHOLD=0` in the compose-stage render env.
Document this in the asset entry `provenance.notes` field.

See `docs/bugs/2026-07-20-seisyun-amv-run/M-4-asset-director-missing-reencode.md`.

### 6. Mapping Assets To Scenes (1:1)

Each scene MUST get exactly one primary asset. Mapping rules:

- Asset duration >= scene duration (asset will be trimmed to fit; the remaining unused portion is discarded)
- Hero scenes get the highest-quality assets
- Adjacent scenes should use assets from DIFFERENT source clips (avoid back-to-back same-source visual)

If two scenes share the same source clip, flag it under `metadata.cross_scene_source_reuse` and ask: is this intentional (e.g. a freeze-frame moment) or should one be replaced?

### 7. Record The Asset Manifest

```json
{
  "version": "1.0",
  "entries": [
    {
      "scene_id": "s001",
      "asset_id": "a001",
      "asset_type": "video_clip" | "image" | "image_animation",
      "source": "video_downloader" | "agnes_image" | "agnes_video",
      "path": "projects/<project-id>/assets/clips/s001.mp4",
      "duration_seconds": 1.20,
      "license": "user_provided" | "user_requested" | "ai_generated",
      "requires_user_ack": false,
      "source_url": "https://..." | null,
      "provenance": {
        "original_url": "https://..." | null,
        "search_query": "ytsearch5:sakurajima bunny suit AMV" | null,
        "channel_or_artist": "..." | null,
        "license_note": "AMV — fan derivative; user has acknowledged"
      },
      "seed": 12345 | null,
      "checksum": "sha256:..."
    }
  ],
  "metadata": {
    "asset_route": "video_downloader" | "ai_generation" | "hybrid",
    "total_assets": <int>,
    "user_ack_required_count": <int>,
    "user_ack_obtained_count": <int>,
    "license_summary": {
      "user_provided": <int>,
      "user_requested": <int>,
      "ai_generated": <int>
    },
    "cross_scene_source_reuse": [
      {"asset_id": "a003", "scene_ids": ["s003", "s007"], "note": "freeze-frame continuation, intentional"}
    ]
  }
}
```

### 8. Quality Gate

- One asset per scene (1:1 mapping)
- All asset files exist on disk and pass ffprobe / file-size sanity
- All `license` fields are present and from the allowed enum
- All `requires_user_ack=true` assets have a corresponding acknowledgment (either in proposal_packet or obtained here)
- No `asset_id` reused across two scenes (unless explicitly noted in cross_scene_source_reuse)
- Total asset count matches `scene_plan.scenes[].length`
- Hero scenes have assets marked `quality: hero` or similar high-priority tag

## Common Pitfalls

- Using `ai_generation` when user did NOT opt in. This is the most common governance violation on this pipeline. Always check `proposal_packet.production_plan.asset_route`.
- Treating `ytsearch` results as free-to-use. AMVs are derivative works; require user_ack.
- Same-source-clip reuse on back-to-back scenes. Looks like a frozen frame; looks broken.
- Forgetting to pass a seed for AI generation. Without a seed, re-runs produce different output, breaking reproducibility.
- Not reading `.agents/skills/agnes-media/SKILL.md` before calling agnes tools. The skill has FLUX-specific prompting that improves output dramatically.
- Asking for assets longer than needed and forgetting to trim. AMV scenes are short; 5s asset on a 0.8s scene wastes 4.2s of storage.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the asset summary (count by license, hero scene assets, any user_ack pending), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval is per-gate — an earlier "go ahead" does not cover this gate.