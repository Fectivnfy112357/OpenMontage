# M-7: Missing `lib/pipelines/music_video_*.py` helper scripts

**Severity**: P2
**Layer**: Pipeline scripts (music-video-anime)
**Affects**: All music-video-anime stages
**Status**: Confirmed
**GitHub Issue**: None — recommend filing

## Symptom

Other OpenMontage pipelines (e.g. `cinematic`, `explainer`) have canonical helper modules in `lib/pipelines/<pipeline>/`. The `music-video-anime` pipeline has:

- `pipeline_defs/music-video-anime.yaml` (manifest)
- `skills/pipelines/music-video-anime/*.md` (director skills)
- `schemas/artifacts/music_video_*.json` (artifact schemas)

But **no** canonical scripts in `lib/pipelines/music_video_*.py` or `scripts/music_video_*.py`.

Every agent that runs this pipeline must hand-write stage orchestration inline (e.g. `projects/seisyun-amv/scripts/write_proposal.py`, `write_script.py`, `write_scene_plan.py`, `build_assets.py`, `render_*.py`).

## Reproduction

```bash
ls lib/pipelines/ 2>&1
# (other pipeline folders)

ls lib/pipelines/music_video_anime/ 2>&1
# ls: cannot access 'lib/pipelines/music_video_anime/': No such file or directory

find scripts/ -name "music_video*" 2>&1
# (nothing)
```

## Root Cause

The music-video-anime pipeline was designed with declarative YAML + director skills but no executable code. By contrast, other pipelines have:

- `lib/pipelines/explainer/` (helpers)
- `lib/pipelines/cinematic/` (helpers)
- `lib/pipelines/character-animation/` (helpers)

Music-video-anime's helpers are missing.

## Evidence

- `ls lib/pipelines/` shows 6 other pipeline folders, no `music_video_anime/`
- Live run: agent wrote 8 inline scripts in `projects/seisyun-amv/scripts/` that should be canonical
- Each script duplicates field-adapter logic (per O-4), schema-validation logic (per M-1, M-2, M-3), and timeline-authoring logic (per M-5)

## Impact

- **No reproducibility** — different runs by different agents produce different scripts
- **No version control of helper logic** — bugs in inline scripts are not in the project repo
- **Cross-pipeline inconsistency** — other pipelines have helpers, this one doesn't
- **Cognitive load** — every agent must re-derive script structure

## Fix

Add canonical helpers in `lib/pipelines/music_video_anime/`:

```
lib/pipelines/music_video_anime/
├── __init__.py
├── brief.py                # music_video_brief artifact construction
├── proposal.py             # music_video_proposal_packet construction
├── script.py               # music_video_script construction (handles M-1)
├── scene_plan.py           # music_video_scene_plan construction (handles M-2)
├── assets.py               # music_video_asset_manifest construction + clip re-encoding (handles M-4)
├── edit.py                 # music_video_edit_decisions construction
├── compose.py              # music_video_render_report construction + hyperframes timeline authoring (handles M-5, M-3)
├── publish.py              # publish_log construction + provenance_chain
└── hyperframes_adapter.py  # schema-to-tool field adapters (handles O-4)
```

Plus thin CLI entry points in `scripts/music_video_anime/<stage>.py`.

Each helper exposes a single function `build_<artifact>(inputs: dict) -> dict` that:
- Validates input
- Constructs artifact matching schema
- Returns both `dict` and validated `ToolResult`

## Verification

1. Refactor each `projects/seisyun-amv/scripts/write_*.py` to use the new helpers
2. Verify outputs are byte-identical to current (or schema-compliant)
3. Run end-to-end music-video-anime production using only `lib/pipelines/music_video_anime/` + `pipeline_defs/music-video-anime.yaml` + director skills (no agent-written inline scripts)
4. Add unit tests in `tests/pipelines/test_music_video_anime_helpers.py` for each helper

## Related

- O-4 (field name mismatch) — adapter belongs in `hyperframes_adapter.py`
- M-1/M-2/M-3/M-5 — each helper should encode the workaround
- M-9 (EP stage missing) — orchestration glue could live in `lib/pipelines/music_video_anime/orchestrator.py`

## Workaround Applied This Run

Agent wrote 8 inline scripts in `projects/seisyun-amv/scripts/`. These should be canonicalized into `lib/pipelines/music_video_anime/` for the next run.