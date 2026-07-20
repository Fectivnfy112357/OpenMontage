# Script Director — Music Video Anime Pipeline

## When To Use

You are the **Script Director** for a beat-synced anime music video. The script on this pipeline is NOT narration — it is a **beat-anchored cut list**. Every section in `script.sections[]` corresponds to a musical unit (intro / verse / chorus / bridge / outro), and every section carries a `beat_anchor` field that points to a real timestamp in audiomap.json.

The script is the contract between proposal ("how many cuts, how dense") and scene_plan ("which cut goes where"). If the script is wrong, every downstream stage is guessing.

## Prerequisites

| Layer | Resource | Purpose |
|-------|----------|---------|
| Schema | `schemas/artifacts/script.schema.json` (this pipeline's extension: `music_video_script.schema.json` if needed) | Artifact validation |
| Prior artifact | `music_video_proposal_packet` from Proposal Director | Selected concept + cut density + asset route |
| Prior artifact | `music_video_brief` | audiomap.json path + anime_theme characterization |
| Tool | `tools/analysis/beat_anchor.py` | Re-read audiomap.json to confirm beat positions |
| Meta | `skills/meta/reviewer.md` | Self-review pass |

## Process

### 1. Re-read The Music Map

Load `projects/<project-id>/artifacts/audiomap.json`. Confirm:

- `audio.duration_sec` — total music length
- `beats_sec[]` — beat positions (seconds)
- `downbeats_sec[]` — bar positions (seconds)
- `onsets_sec[]` — note/onset positions (for tight cuts)
- `key_moments[]` — `SURGE` / `DROP` / `hard_stop` events (for hero cuts)
- `phrases[]` — phrase boundaries (for phrase-led motion register)

If audiomap.json is missing or empty, STOP. The script cannot be built without the beat grid.

### 2. Identify Music Sections

Walk through audiomap in order. Mark section boundaries at:

| Boundary type | Marked by |
|---|---|
| Intro | `audio.duration_sec > 0` AND first phrase boundary OR first key_moment |
| Verse | Phrase boundaries where energy level is low/medium |
| Chorus | Where key_moments contains `SURGE` OR `DROP` |
| Bridge | Mid-song energy dip followed by a SURGE |
| Outro | Last phrase boundary OR `hard_stop` |

For a 90s typical song, expect 1 intro + 2 verses + 2 choruses + 1 bridge + 1 outro = ~7 sections. For a 30s clip, expect fewer. For a 3-minute epic, expect 10-15.

Each section MUST have a `start_seconds` (first beat_anchor in that section) and `end_seconds` (last beat_anchor in that section).

### 3. Decide Cut Density Per Section

The `motion_register` from the approved concept drives this:

| Motion register | Cut density | Anchor type |
|---|---|---|
| `kinetic-burst` (DnB / trap / drum&bass) | 1 cut per 0.5-1.5s | `on_beat` or `onset` |
| `phrase-led` (ballad / mood) | 1 cut per 2-6s | `phrase_start` / `phrase_end` |
| `hybrid-burst` | 1 cut per 2-3s on verses, 0.5-1s on chorus | Mix |

For each section, compute `target_cut_count = (end_seconds - start_seconds) / expected_cut_length`.

### 4. Optional: Subtitle Card Script

If the concept includes typography (`on-beat-karaoke` or `sparse-on-impact`):

- **On-beat karaoke**: list each line of lyrics with its first-beat timestamp. Don't write full lyrics — just write the lines that get a karaoke-style text card.
- **Sparse on impact**: list 3-7 impactful phrases that should appear as title cards. Each at a `SURGE` or `DROP` key_moment.

If `typography == "none"`, skip this section entirely.

### 5. NO Narration

This pipeline does not produce narration. The script sections have NO `text` field for spoken voice. If the user wants narration, they are asking for a different pipeline (cinematic / animated-explainer). Surface this at the proposal stage, not here.

### 6. Record The Script

Schema (extends existing `script.schema.json` with these fields):

```json
{
  "version": "1.0",
  "title": "AMV: <anime title> × <music track>",
  "total_duration_seconds": <from audiomap>,
  "voice_performance": null,   // AMV has no narration
  "sections": [
    {
      "id": "intro",
      "label": "INTRO",
      "text": null,             // no narration
      "start_seconds": <first beat anchor in intro>,
      "end_seconds": <last beat anchor in intro>,
      "music_section_type": "intro" | "verse" | "chorus" | "bridge" | "outro",
      "motion_register_for_section": "kinetic-burst" | "phrase-led" | "hybrid-burst",
      "target_cut_count": <int>,
      "beat_anchor": {
        "type": "phrase_start" | "downbeat" | "phrase_end" | "drop" | "silence_start",
        "t_seconds": <start_seconds of section>,
        "rationale": "first beat of intro phrase per audiomap.phrases[0]"
      },
      "subtitle_cards": [
        {
          "at_beat_index": <int, index into audiomap.beats_sec>,
          "at_seconds": <float>,
          "text": "short impactful phrase",
          "style": "impact" | "lyric-karaoke" | "title"
        }
      ],
      "delivery_cues": null,
      "enhancement_cues": [
        {
          "type": "transition_flash" | "flash_white" | "flash_black" | "ken_burns_in" | "ken_burns_out" | "freeze_frame",
          "description": "...",
          "timestamp_seconds": <at boundary between sections>
        }
      ],
      "narrative_role": "establish_context" | "build_tension" | "deliver_payload" | "emotional_beat" | "transition" | "call_to_action",
      "shot_intent": "Why this section exists in the cut list",
      "source_ref": "audiomap.json#<key>:<index>"
    }
  ],
  "metadata": {
    "motion_register_global": "kinetic-burst" | "phrase-led" | "hybrid-burst",
    "typography": "on-beat-karaoke" | "sparse-on-impact" | "none",
    "audiomap_path": "projects/<project-id>/artifacts/audiomap.json",
    "cut_density_per_minute": <int>,
    "scene_count_total": <sum of target_cut_count>,
    "language_of_subtitles": "zh" | "en" | "ja" | "none"
  }
}
```

### 7. Quality Gate

- Every section has a non-null `beat_anchor` pointing to a real timestamp
- `beat_anchor.t_seconds` is within ±50ms of audiomap.beats_sec / downbeats_sec / onsets_sec (validate by index lookup)
- `sections[].start_seconds` is monotonically non-decreasing
- `sections[-1].end_seconds` matches `audiomap.audio.duration_sec` within 100ms
- No narration fields are populated (`text == null` everywhere)
- Total `target_cut_count` across all sections is reasonable (matches proposal_packet.production_plan.scene_count within 20%)

## Common Pitfalls

- Writing a narration script. This pipeline has NO narration. If the user wants it, surface at proposal stage.
- Ignoring audiomap and writing cut boundaries by guessing. Always reference audiomap timestamps.
- Subtitle text that doesn't match beat positions. Karaoke text MUST land on lyric onsets.
- Same motion register on every section. Hybrid-burst means verses phrase-led + chorus kinetic-burst.
- Putting `text` (narration) in sections. Leave it null; the schema forbids it on this pipeline's strict mode (use the music_video_script.schema.json if you make one, with `text` required to be null).

---

## Gate Reminder (Binding)

This stage gates on human approval (`human_approval_default: true`). After review passes:
checkpoint with `status="awaiting_human"`, present the cut list summary (sections + cut counts + beat anchors + subtitle cards), and **END YOUR TURN**. Do not start the next stage in the same response.
Approval is per-gate — an earlier "go ahead" does not cover this gate.