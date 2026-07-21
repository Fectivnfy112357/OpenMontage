# O-7: Skill documentation references tools that don't exist

**Severity**: P2
**Layer**: Platform (skill docs / source mismatch)
**Affects**: Every agent that consults skills before acting
**Status**: Confirmed (verified 2026-07-20 by code audit)
**GitHub Issue**: None specific — recommend filing

## Symptom

`.agents/skills/` documents reference tools, classes, and pipelines that don't exist in source. Agent assumes skills are authoritative; lands on missing imports.

Concrete mismatches observed:

| Documented | Reality |
|---|---|
| `tools/analysis/video_downloader_ejs.py` | Only `tools/analysis/video_downloader.py` exists |
| `tools/audio/piper_tts_windows.py` Windows subclass | Only `tools/audio/piper_tts.py` (no platform subclass) |
| `pipeline_defs/music-video.yaml` (and tools/audio/beat_detect_librosa.py) | Missing; music-video-anime pipeline files were manually deleted 2026-07-17 (current pipeline is `music-video-anime.yaml` only) |
| `platform-subclass-pattern.md` worked examples point at `piper_tts_windows.py` and `video_downloader_ejs.py` | Both fictional |
| "~90 BaseTool subclasses" | Actual: 103 across 98 files |
| `stock_sources` claims 15 sources including pixabay | Actual: 16 adapters including `pixabay_video` (separate from pixabay image) |

Verified-correct assertions (per 2026-07-20 observation): explainer folder name matches manifest, 12 production pipelines, character-animation has 6 rig tools, documentary-montage has 5 stages, scaffold_atelier_project.py exists, atelier schema files are complete, cap_recorder is Windows-platform-gated, direct_clip_search uses adapter name.

## Reproduction

```bash
ls tools/audio/piper_tts_windows.py 2>&1
# ls: cannot access 'tools/audio/piper_tts_windows.py': No such file or directory

ls tools/analysis/video_downloader_ejs.py 2>&1
# ls: cannot access 'tools/analysis/video_downloader_ejs.py': No such file or directory

ls pipeline_defs/music-video.yaml 2>&1
# ls: cannot access 'pipeline_defs/music-video.yaml': No such file or directory
```

## Root Cause

Skills evolved through parallel tracks (skill authors vs source authors) without a synchronization gate. When source code was deleted/renamed/refactored, skill docs were not updated.

## Evidence

- Hindsight observation 2026-07-20T07:51:43 (audit of skill doc discrepancies)
- Direct file existence checks (above)
- `find tools/ -name "*windows*"` returns no results; `find tools/ -name "*ejs*"` returns no results

## Impact

- Agents waste time attempting to import non-existent modules
- Trust calibration broken: agents can't tell which skills are accurate vs outdated
- Especially bad for new users who follow skills first, source second

## Fix

Three options proposed in original audit:

**Option A — make skills authoritative** (preferred long-term): bring source up to match skill claims. Add `video_downloader_ejs.py`, `piper_tts_windows.py`, `music-video.yaml` etc. Heavy lift (~weeks).

**Option B — update skills to match source as truth**: stamp each skill with its last-verified date. Add a `status: verified | deprecated | pending_creation` frontmatter. Mark missing modules as `pending_creation` with proposed specs. Light lift (~days).

**Option C — hybrid (recommended)**: build source for music-video pipeline (Option A for one specific pipeline that we now have empirical usage data for); downgrade other mismatches to `pending_creation` wording (Option B for everything else).

**Audit helper**: add a CI check that runs `git grep` for each `tools/...` filename mentioned in `.agents/skills/**/*.md` and reports missing files. Fail CI when drift detected.

## Verification

1. Add `.github/workflows/skill-source-drift.yml` that:
   - extracts all `tools/...py` filenames from `.agents/skills/`
   - runs `find tools/ -name X.py` for each
   - fails if any are missing
2. Run on current main → should fail with list of missing modules
3. Apply Option B/C fixes; re-run → should pass

## Related

- O-2 (tool_registry stale cache — REMOVED: verified not a real bug; agent should re-discover per AGENT_GUIDE.md)
- Issue #237 (Local zero-key rendering) — discusses similar platform-vs-skill drift
- M-7 (missing pipeline helpers) — pipeline-level skill/source mismatch for music-video-anime specifically

## Workaround Applied This Run

Agent cross-referenced each skill claim against `find` results before importing. The `music-video-anime` pipeline works because it was re-added to `pipeline_defs/` after the 2026-07-17 deletion, but other skills (e.g. ones mentioning `music-video` lowercase) are still stale.