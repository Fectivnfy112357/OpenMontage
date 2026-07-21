# 2026-07-20 seisyun-amv Run — Bug Report & Remediation Plan

## Run Summary

| Field | Value |
|---|---|
| Date | 2026-07-20 ~14:30-23:50 UTC |
| Pipeline | `music-video-anime` v1.0 |
| Project | `projects/seisyun-amv/` |
| Stages completed | research → proposal → script → scene_plan → assets → edit → compose → publish |
| Final deliverable | `seisyun-amv_1920x1080_hero.mp4` (81.7 MB, 177.11s, 1920×1080, h264+aac) |
| Wall time | ~9.5 hours (including 3 manual user gates) |
| Outcome | **Successful** — but with 13 distinct bugs documented below |
| Re-verify date | 2026-07-21 — 2 bugs found already fixed (see "Already Fixed" table) |

## Bug Triage Summary

| ID | Severity | Layer | Verified by GitHub Issue | Title |
|---|---|---|---|---|
| O-1 | P0 | Platform (beat_anchor) | ⚠️ Indirect (Windows family, #396) | `subprocess.run(["npx",...])` fails on Windows with WinError 2 |
| ~~O-3~~ | ~~P2~~ | n/a | n/a | **REMOVED 2026-07-21**: was incorrectly attributed to video_downloader.py. Tool already uses `max_duration_seconds` metadata check (line 197), not `--max-duration` CLI flag. Agent's own wrapper script used obsolete flag — not a tool bug. |
| O-4 | P1 | Platform (hyperframes family) | ✅ #306 | HyperFrames tool/schema field key mismatches |
| O-5 | P0 | Platform (hyperframes family) | ✅ #306 + #359 + #360 | `_generate_index_html` emits empty timeline; silent fallback; relative path bug |
| ~~O-6~~ | ~~P1~~ | n/a | ~~✅ #360~~ | **REMOVED 2026-07-21**: PR #374 MERGED in commit `33c7000`. `tools/video/hyperframes_compose.py` line 657 now uses `.expanduser().resolve()`. Issue #360 still OPEN but fix is in main. |
| O-7 | P2 | Platform (skill docs) | ✅ Verified 2026-07-20 observation | Skill doc/source discrepancies |
| M-1 | P2 | Pipeline schema | ❌ None — recommend filing | `music_video_script` schema field type errors |
| M-2 | P2 | Pipeline schema | ❌ None — recommend filing | `music_video_scene_plan` `next_beat_anchor` inconsistent |
| M-3 | P1 | Pipeline schema | ❌ None — recommend filing | `music_video_render_report` over-constrains runtime |
| M-4 | P2 | Pipeline skill | ❌ None — recommend filing | `asset-director` missing clip re-encode step |
| M-5 | P1 | Pipeline + Platform (shared) | ⚠️ Mixed | `compose-director` assumes tool generates timeline |
| M-6 | P2 | Pipeline skill | ❌ None — recommend filing | `proposal-director` ignores governance schema coupling |
| M-7 | P2 | Pipeline scripts | ❌ None — recommend filing | Missing `lib/pipelines/music_video_*.py` helpers |
| M-8 | P3 | Pipeline schema | ❌ None — recommend filing | `music_video_brief` schema incomplete vs director doc |
| M-9 | P2 | Pipeline structure | ❌ None — recommend filing | EP (executive-producer) stage not implemented as explicit stage |

**Legend**:
- ✅ = Confirmed by GitHub issue text
- ⚠️ = Confirmed by related issue or observation
- ❌ = No existing issue — recommend filing
- Layer = Platform (affects multiple pipelines) vs Pipeline (music-video-anime only)

## Already Fixed (verified 2026-07-21)

| ID | Original issue | Fix verified | Source |
|---|---|---|---|
| O-3 | yt-dlp `--max-duration` obsolete | `tools/analysis/video_downloader.py` line 197 uses metadata duration check; agent wrapper bug, not tool bug | (correction) |
| O-6 | relative `output_path` two-base resolution | `tools/video/hyperframes_compose.py` line 657 now `.expanduser().resolve()` | PR #374 MERGED in commit `33c7000` |

## Filing Plan

| Action | Count | Target |
|---|---|---|
| File new issues for unconfirmed bugs | 12 | https://github.com/calesthio/OpenMontage/issues/new |
| Reference existing issues in PRs | 4 (#306, #359, #360, #396) | https://github.com/calesthio/OpenMontage/pulls |
| Fix in PR by priority | P0 → P1 → P2 → P3 | Local branches |

## Recommended Fix Order

1. **O-1** (P0, blocks beat_anchor on Windows) — single-line fix: `subprocess.run(["npx.cmd", ...])` or `shell=True`
2. **O-5** (P0, blocks video composition) — agent workaround applied; needs upstream HyperFrames fix
3. **M-3** (P1, blocks emergency runtime downgrade) — schema relaxation + add `exception_clause_invoked` field
4. **O-4 + O-6** (P1, HyperFrames family) — coordinated fix in `hyperframes_compose.py`
5. **M-1, M-2** (P2, schema cleanup) — mechanical fixes
6. **M-5** (P1, shared) — `compose-director` clarification
7. **M-7, M-9** (P2-P3, structural) — helper scripts + EP stage formalization
8. **M-4, M-6, M-8, O-3, O-7** (P2-P3, polish) — docs/skill cleanup

## Conventions for Individual Bug Files

Each file in this directory follows:

```markdown
# O-{N}: <short title>

**Severity**: P0 | P1 | P2 | P3
**Layer**: Platform | Pipeline
**Affects**: <which pipelines / tools>
**Status**: Confirmed | Suspected | Reopened
**GitHub Issue**: <number or "recommend filing">

## Symptom
<what the user / agent observes>

## Reproduction
<minimal steps>

## Root Cause
<technical trace to bad-value source>

## Evidence
<file:line refs, GitHub issue quote, agent log>

## Impact
<what gets blocked or misrendered>

## Fix
<concrete change>

## Verification
<how to prove the fix works>

## Related
<links to other bugs>
```