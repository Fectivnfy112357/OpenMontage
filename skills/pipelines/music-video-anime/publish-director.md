# Publish Director — Music Video Anime Pipeline

## When To Use

You are the **Publish Director** for a beat-synced anime music video. Your job is to take the rendered MP4 from compose and assemble a publishable package: hero export + thumbnail + metadata + provenance chain.

For AMV, the provenance chain matters more than usual because assets frequently come from third-party AMV clips with unclear license. Every `user_requested` asset MUST have an unbroken ack chain from proposal → assets → render → publish.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/publish_log.schema.json` | Artifact validation (general registry; shared with other pipelines) |
| Prior artifact | `music_video_render_report` from Compose Director | The rendered MP4 + render metadata |
| Prior artifact | `music_video_asset_manifest` (load via render_report reference) | Asset provenance |
| Prior artifact | `music_video_proposal_packet` (optional) | User ack records |
| Prior artifact | `music_video_script` (optional) | Section metadata |
| Tool | `ffmpeg` + `json` (stdlib) | Hero export + thumbnail extraction + metadata sidecar |

## Process

### 1. Verify Beat Sync Verified Flag

Read `music_video_render_report.beat_sync_verification.verification_passed`. If false, STOP. The video is not deliverable until compose passes beat sync.

### 2. Walk The Provenance Chain (assets + music)

For each asset in the render's cut list, look up its source via `music_video_asset_manifest`. Build a provenance chain:

```
asset_id → source_url → license → user_ack (if applicable)
```

Special rules:
- `license == user_requested` MUST have `user_ack_obtained == true` in the manifest, AND a corresponding entry in `music_video_proposal_packet.acknowledgments`
- `license == user_provided` MUST have a `source_url` (the URL the user gave)
- `license == ai_generated` has no third-party IP — record `seed` and `prompt` for reproducibility

**Music track provenance** (parallel chain):

```
music_track_id → source_method → license → user_ack (if applicable)
```

Where `source_method` is `music_video_brief.metadata.music_track_source`:

| source_method | license | user_ack record |
|---|---|---|
| `user_provided` | `user_provided` | n/a |
| `video_downloader_url` | `user_provided` | n/a |
| `ytsearch_artist_track` | `user_requested` | `music_track_user_ack_obtained=true` in brief + ack recorded at research stage |

If any link in the chain is missing, STOP and surface to the user.

### 3. Build Hero Export

For music-video-anime, the canonical hero is the rendered MP4 itself (no need for a derivative cut). Verify:

- Resolution matches `music_video_proposal_packet.production_plan.target_resolution`
- Codec matches the spec (h264 video, aac audio, mp4 container)
- File size is reasonable (< 200MB for 90s AMV at 1080p)

### 4. Build Thumbnail / Poster Frame

Pick a thumbnail from the audio energy peak:

- If `audiomap.key_moments` has a `DROP` event, pick the frame 0.5s into that DROP
- Otherwise, pick the frame at the song's peak loudness (from `audiomap.diagnostics.peak` if present)

Extract via `ffmpeg`:

```bash
ffmpeg -i final.mp4 -ss <peak_sec> -frames:v 1 -q:v 2 thumbnail.jpg
```

### 5. Build Metadata Sidecar

Create a JSON sidecar with all the metadata needed for upload platforms:

```json
{
  "version": "1.0",
  "title": "AMV: <anime> × <track>",
  "music": {
    "track_title": "<...>",
    "artist": "<...>",
    "duration_seconds": <...>,
    "bpm": <...>,
    "audiomap_path": "<...>"
  },
  "anime_theme": {
    "title": "<...>",
    "title_romaji": "<...>",
    "characters": [...],
    "palette": "<...>"
  },
  "render": {
    "tool": "hyperframes_compose",
    "tool_version": "<...>",
    "render_runtime": "hyperframes",
    "fps": <...>,
    "duration_seconds": <...>,
    "resolution": "1920x1080"
  },
  "asset_summary": {
    "total_assets": <int>,
    "by_license": {
      "user_provided": <int>,
      "user_requested": <int>,
      "ai_generated": <int>
    }
  },
  "motion_register": "kinetic-burst" | "phrase-led" | "hybrid-burst",
  "tags": ["amv", "anime", "music video", "<anime>", "<track>"]
}
```

### 6. Record The Publish Log

```json
{
  "version": "1.0",
  "output_package": {
    "hero_video": "projects/<project-id>/publish/final.mp4",
    "thumbnail": "projects/<project-id>/publish/thumbnail.jpg",
    "metadata_sidecar": "projects/<project-id>/publish/metadata.json"
  },
  "exports": [
    {
      "label": "hero_1080p",
      "path": "projects/<project-id>/publish/final.mp4",
      "codec": "h264",
      "container": "mp4",
      "resolution": "1920x1080",
      "fps": 30,
      "duration_seconds": <float>,
      "file_size_bytes": <int>
    }
  ],
  "provenance_chain": [
    {
      "asset_id": "a001",
      "scene_id": "s001",
      "license": "user_requested",
      "source_url": "https://www.youtube.com/watch?v=...",
      "user_ack_obtained": true,
      "ack_source": "proposal_packet.acknowledgments[0]"
    }
  ],
  "thumbnail": {
    "path": "projects/<project-id>/publish/thumbnail.jpg",
    "extracted_at_seconds": <float>,
    "selection_reason": "DROP key_moment at <t_seconds>"
  },
  "metadata": {
    "music_track": "<track path>",
    "anime_theme": "<anime>",
    "render_runtime": "hyperframes",
    "beat_sync_verified": true,
    "all_user_acks_obtained": true,
    "publish_log_artifact_path": "projects/<project-id>/artifacts/publish_log.json"
  }
}
```

### 7. Quality Gate

- `output_package.hero_video` exists and passes ffprobe
- Every `license == user_requested` asset has an unbroken ack chain to user confirmation
- thumbnail.jpg exists and is non-zero size
- metadata sidecar is valid JSON
- All `music_video_render_report.runtime_swap_detected == false` (runtime lock honored)

## Common Pitfalls

- Skipping the provenance chain. AMV is the highest-risk pipeline for license compliance; the publish_log is the audit trail.
- Picking a thumbnail at a quiet moment. Pick at a DROP or peak loudness, not at intro silence.
- Failing to record `ack_source` for user_requested assets. The user will not remember what they ack'd; the publish_log must.
- Treating `license == ai_generated` as license-free. It is license-free for THIS output, but the anime characters depicted may still be third-party IP (Sony/Aniplex/etc.). The publish_log should warn that the OUTPUT is original but the SUBJECTS are not.

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the publish summary (hero path, thumbnail, metadata, provenance chain), and **END YOUR TURN**.
Approval is per-gate — an earlier "go ahead" does not cover this gate.