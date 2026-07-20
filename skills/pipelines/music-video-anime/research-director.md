# Research Director — Music Video Anime Pipeline

## When To Use

You are the **Research Director** for a beat-synced anime music video (AMV / MAD / 卡点视频). The research stage is the foundation: the music must be analyzed ONCE here so every downstream stage works on the same beat grid, and the anime theme must be characterized so visual decisions in scene_plan and asset stages have a source of truth.

This stage produces **two artifacts under one umbrella**:

1. **`beat_analysis`** — audiomap.json + per-track beat grid. This is the spine.
2. **`research_brief`** — anime theme characterization + visual approach options.

The downstream agent will treat `beat_analysis` as ground truth; `scene_director` and `edit_director` will reject any cut that does not align to a beat anchor from `beat_analysis`.

## Runtime Selection (this stage does not select runtime)

Runtime selection happens at `proposal-director`. This stage only collects facts. But the proposal stage will lock `render_runtime = "hyperframes"` per `pipeline_defs/music-video-anime.yaml:runtime_lock`, so while collecting research you do NOT need to evaluate Remotion or FFmpeg as alternatives.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/music_video_brief.schema.json` | Artifact validation |
| Tool | `tools/analysis/beat_anchor.py` | The one and only beat analyzer |
| Tool | `tools/analysis/audio_energy.py` | Optional cross-check for energy phrases |
| Tool | `tools/analysis/video_analyzer` | Optional — analyze user-provided anime reference clip |
| Tool | `tools/analysis/video_downloader` | Optional — for anime reference clips the user supplies by URL |
| Tool | `tools/analysis/scene_detect`, `frame_sampler` | Optional — for visual reference frames |
| Meta | `skills/meta/reviewer.md` | Self-review pass |
| User input | Conversation history | The music track + the anime theme |

## Process

### 1. Resolve The Music Source (BEFORE any other analysis)

The music is the spine. Find out exactly how the user wants to acquire the track:

| Option | User input | Tool to use | source tag | license tag | requires_user_ack |
|---|---|---|---|---|---|
| **A. User-provided file** | File already dropped in `projects/<project-id>/assets/music/` or `music_library/` | (none — direct reference) | `user_provided` | `user_provided` | false |
| **B. User-provided URL** | User gave a direct audio URL (SoundCloud, Bandcamp, direct MP3 link, etc.) | `video_downloader(url=<url>, format="audio_only", max_resolution="n/a")` | `video_downloader_url` | `user_provided` | false |
| **C. ytsearch by name** | User said "the track is X by Y" (artist + title) | `video_downloader(url="ytsearch3:<artist> <title>", format="audio_only")` | `ytsearch_artist_track` | `user_requested` | **true** — must ack before compose |
| ~~D. royalty-free library~~ | (intentionally skipped — pixabay_music does not have anime OST coverage) | n/a | n/a | n/a | n/a |

**Why option C requires user_ack**: ytsearch results come from anonymous YouTube uploads. Even when an official channel (Aniplex, Sony Music Japan, etc.) has uploaded the track, agent cannot verify the upload's license status without an authoritative source. Treating it as a safe license would be lying. The user explicitly acknowledges: "I understand this audio may have unclear licensing; I'm using it for this personal project."

**Step-by-step for option C (the typical case):**

1. Construct the search query. For a user request like "青春ブタ野郎 by fox capture plan", try variations:
   - `"<artist> <title>"` (English/romaji)
   - `"<artist> <title> official"`
   - For anime OST: the YouTube title is often the romaji (e.g. "Seisyunbutayaro fox capture plan") instead of the Japanese title (e.g. "青春ブタ野郎"). Try both.
2. Run `ytsearch3:<query>` via `video_downloader` to get the top 3 candidates.
3. Look at `uploader`/`channel` in the result — if it matches the official artist channel (fox capture plan, Aniplex, Sony Music Japan, etc.), prefer that result.
4. Confirm with the user: "Found `<title>` by `<uploader>`, `<duration>`s, Aniplex official. Use this? (yes/no)". The user must say yes before you download.
5. Download via `video_downloader(url=<chosen_video_url>, format="audio_only", max_resolution="n/a")`.
6. **STOP and ask for user_ack** before proceeding to Step 2 (beat analysis). Show:
   ```
   MUSIC SOURCE ACKNOWLEDGMENT
   ├─ Track: Seisyunbutayaro
   ├─ Artist: fox capture plan
   ├─ Source: ytsearch3:Seisyunbutayaro fox capture plan
   ├─ Uploader: fox capture plan (Aniplex Inc.)
   ├─ License risk: YouTube uploads may have unclear distribution terms
   └─ Do you acknowledge this and want to proceed? (yes/no)
   ```
   Until the user says yes, do NOT run beat_anchor and do NOT mark music_track_user_ack_obtained=true.

**Schema consistency**: the four field combinations in `music_video_brief.metadata.music_track_*` are enforced by `music_track_source_license_consistency` (oneOf branches). Inconsistent combinations are rejected at validation. If you set `source=ytsearch_artist_track` but `license=user_provided`, the brief will fail to validate.

Save the music file at: `projects/<project-id>/assets/music/<track_filename>` (e.g. `Seisyunbutayaro-fox-capture-plan.mp3`).

**STOP conditions**:
- If all `ytsearch` candidates are clearly fan uploads (not the official channel), warn the user before downloading. They may want to drop their own file (option A) instead.
- If the audio file is corrupt, fails ffprobe, or has 0 duration, STOP and ask the user to provide a different source.

### 2. Run The Beat Analyzer ONCE

Use `tools/analysis/beat_anchor.py` to analyze the locked music track. This is the ONLY beat analyzer — **never re-measure beats with another tool or by ear**. The analyzer wraps `npx hyperframes beats` (deterministic, headless, no librosa needed) and writes `audiomap.json` with:

- `bpm` — only reliable when the music is genuinely rhythmic (verdict is yours)
- `beats_sec[]` — the beat grid (seconds)
- `downbeats_sec[]` — the downbeat positions (start of each bar)
- `onsets_sec[]` — note/onset positions for tighter cuts
- `key_moments[]` — `SURGE` / `DROP` / `hard_stop` events
- `phrases[]` — phrase boundaries
- `energy_phases[]` — energy level + density per region
- `audio.duration_sec` — total length

**Save the audiomap to** `projects/<project-id>/artifacts/audiomap.json`.

If the analyzer fails or returns empty (e.g. corrupt audio, unsupported format), STOP. Do not improvise beats.

### 3. Characterize The Anime Theme

From the user's prompt, determine:

- **Anime title** (if named) — e.g. "青春猪头少年不会梦到兔女郎学姐" / "Rascal Does Not Dream of Bunny Girl Senpai"
- **Key characters** (if mentioned) — e.g. "Sakurajima Mai", "Azusagawa Sakuta"
- **Key scenes/motifs** — what visual elements must appear (e.g. "train station", "library", "bunny suit", "Fujisawa beach")
- **Color/tone references** — what palette the user associates with this anime

If the user did NOT name an anime, characterize by **vibe** instead:
- "校园恋爱" → high school romance register
- "热血少年" → shonen energy
- "治愈日常" → iyashi-keki slow life register

Record under `research_brief.metadata.anime_theme` as either `{explicit: true, title, characters[], motifs[], palette}` or `{explicit: false, vibe_register, sample_keywords[]}`.

### 4. Asset Route Decision (FACT-FINDING, NOT DECISION)

This stage records **what assets are available** under the asset route in the eventual proposal. The proposal stage will lock the decision. Do not commit here, but report:

| Condition | Report under `research_brief.metadata.asset_route_options` |
|---|---|
| User has anime reference clips / URLs | `{route: "video_downloader", user_provided_urls: [...]}` |
| User has NOT provided clips | `{route: "video_downloader", ytsearch_candidates: ["<keywords>"]}` |
| User has explicitly said "用 AI 生成 / AI 画 / AI 出图" | `{route: "ai_generation", agnes_opt_in: true}` |

`video_downloader` is the default — only flip to `ai_generation` if the user has explicitly opted in. This is the rule the user defined; do not invert it.

### 5. Web Research For Visual Reference

Use `web_search` (allowed tools include `web_search`) to gather:

- 3-5 visual reference URLs for the anime (key art, screenshots, AMV stills)
- 1-2 reference AMVs of similar style (for tone, NOT for asset reuse)
- Music mood references (genre + energy + BPM range — see `skills/creative/music-gen-usage.md` BPM table)

Avoid searching for "anime music videos" as stock — the user wants their own AMV, not a published one.

### 6. Visual Approach Options (2-3 Distinct)

Identify at least 2-3 distinct visual approaches. These will become concept_options in the proposal stage. Examples:

| Approach | Description |
|---|---|
| **High-cut kinetic** | 0.5-1.5s cuts per beat, maximum energy. Best for trap/electronic/drum&bass. |
| **Phrase-driven mood** | 2-6s cuts aligned to phrase boundaries, lyrical camera work. Best for vocal-driven rock/ballad. |
| **Hybrid burst** | Quiet phrases hold on longer cuts, then bursts of high-cut on chorus/drop. Best for songs with dynamic range. |

Each approach should specify:
- expected cut density (cuts per beat, or cuts per minute)
- motion treatment (ken-burns, hard-cut, flash, freeze-frame)
- typography usage (subtitle cards on-beat vs off-beat)

### 7. Provenance Flag For Third-Party Footage

If any visual approach relies on third-party AMV footage (the `ytsearch:` route), record under `research_brief.metadata.third_party_footage_candidates`:

```yaml
- candidate_url: "https://www.youtube.com/watch?v=..."
  source_channel: "..."
  notes: "AMV — fan-made derivative of anime; license unclear"
  requires_user_ack: true
```

The asset stage will require explicit user_ack for these.

### 8. Record The Research Brief

Minimum fields:

```json
{
  "version": "1.0",
  "topic": "Anime music video: <anime title> × <music track>",
  "hook": "<one-line creative direction>",
  "key_points": [
    "Music: <track> — <bpm> BPM — <key_moments count> drops/surges",
    "Anime theme: <title or vibe_register>",
    "Visual approach: <one of the 2-3 options>"
  ],
  "core_message": "A beat-synced <bpm> BPM visual interpretation of <track> through <anime> imagery",
  "tone": "kinetic" | "mood-led" | "hybrid-burst",
  "style": "anime music video (AMV/MAD)",
  "target_audience": "anime fans / bilibili douyin viewers",
  "target_platform": "tiktok" | "bilibili" | "youtube_shorts" | "generic",
  "target_duration_seconds": <music duration>,
  "metadata": {
    "music_track_path": "projects/<project-id>/assets/music/<file>",
    "music_track_duration_seconds": <from audiomap>,
    "bpm": <from audiomap>,
    "beat_grid_reliable": <true|false, your verdict>,
    "anime_theme": { ... },
    "asset_route_options": { ... },
    "third_party_footage_candidates": [ ... ]
  }
}
```

### 9. Quality Gate

- audiomap.json exists on disk; its `audio.duration_sec` matches the music file's actual duration (±100ms)
- research_brief.metadata.bpm is populated (or `null` if beat_grid_reliable=false)
- At least 2 visual approach options identified
- anime_theme is characterized (explicit OR vibe-based)
- Asset route options recorded (one of: user_provided_urls, ytsearch_candidates, agnes_opt_in)
- All third-party footage candidates flagged with requires_user_ack

## Common Pitfalls

- Re-measuring beats with `audio_energy` or by ear. **NO.** One analyzer. Trust it.
- Skipping the music lock step. Without a concrete file path, every downstream stage is guessing.
- Defaulting to "ai generation" because the user named an anime. Default is `video_downloader` — only flip when user has explicitly opted in.
- Treating user-provided AMV URLs as free to use. They are AMVs — derivative works with unclear license; require user_ack.
- Failing to identify the BPM-verdict. A 60 BPM balladic track and a 160 BPM DnB track have totally different cut densities; you must commit to which one this is.

---

## Gate Reminder (Binding)

This stage gates on human approval. After review passes:
checkpoint with `status="awaiting_human"`, present the summary (audimap summary + anime theme + visual approach options + asset route decision), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval is per-gate — an earlier "go ahead" does not cover this gate.