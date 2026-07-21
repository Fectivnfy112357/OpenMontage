# Remediation Plan — 2026-07-20 seisyun-amv Run Bugs

Generated: 2026-07-21
Source run: `projects/seisyun-amv/` (HyperFrames music-video-anime AMV of fox capture plan "Seisyunbutayaro")

## Goal

Eliminate the 15 distinct bugs surfaced during the 2026-07-20 music-video-anime run, ordered by impact and cost-to-fix.

## Constraints

- All changes must preserve `music_video_*` schema contracts (backwards compatible where possible)
- All changes must not break existing pipeline runs
- Platform-level fixes (O-*) should ideally benefit multiple pipelines
- Pipeline-level fixes (M-*) should be scoped to `music-video-anime` only

## Phases

### Phase 1 — Unblock production (P0, 1-2 days)

| Order | Bug | Fix | Files |
|---|---|---|---|
| 1 | O-1 | `tools/analysis/beat_anchor.py`: replace `subprocess.run(["npx",...])` with `subprocess.run(["npx.cmd",...])` via `shutil.which` resolution (Option C in O-1) | `tools/analysis/beat_anchor.py` (line 293-294) |
| 2 | O-5 | Rewrite `_generate_index_html` in `tools/video/hyperframes_compose.py` to emit GSAP timeline from `at_seconds` / `duration_seconds` (Option A in O-5) | `tools/video/hyperframes_compose.py` (~line 955-1023) |

**Note**: O-3 and O-6 were both verified FIXED on 2026-07-21:
- O-3: `tools/analysis/video_downloader.py` line 197 already uses metadata duration check
- O-6: PR #374 MERGED in commit `33c7000`; `tools/video/hyperframes_compose.py` line 657 now uses `.expanduser().resolve()`

**Validation**: end-to-end music-video-anime run on Windows native produces 177s MP4 in 1 attempt, no agent hand-rewriting of `index.html`.

### Phase 2 — Schema governance (P1, 1-2 days)

| Order | Bug | Fix | Files |
|---|---|---|---|
| 3 | M-3 | Add `runtime_swap` field to `music_video_render_report` schema; relax `render_runtime` enum to allow documented fallbacks; update `compose-director.md` Step 7 | `schemas/artifacts/music_video_render_report.schema.json`, `skills/pipelines/music-video-anime/compose-director.md` |
| 4 | O-4 | Add field-name normalizer to `hyperframes_compose` accepting both `id`/`asset_id` and `assets`/`entries` keys (Option A in O-4) | `tools/video/hyperframes_compose.py` (line ~484-488) |
| 5 | O-6 | `.resolve()` output_path at line 657 (per issue #360) | `tools/video/hyperframes_compose.py` line 657 |
| 6 | M-5 | Update `compose-director.md` to document the composition pattern (per Option C in M-5) and add reference to `.agents/skills/hyperframes-core/references/sub-compositions.md` in "Read before" list | `skills/pipelines/music-video-anime/compose-director.md` |

**Validation**: governance tests + integration test for full compose.

### Phase 3 — Canonicalization (P2, 2-3 days)

| Order | Bug | Fix | Files |
|---|---|---|---|
| 7 | M-7 | Create `lib/pipelines/music_video_anime/` with 10 helper modules (per M-7 fix) | new directory `lib/pipelines/music_video_anime/` |
| 8 | M-1 | Add `target_cut_count` to `music_video_script` schema's `required`; keep `typography` enum strict | `schemas/artifacts/music_video_script.schema.json` line 27 |
| 9 | M-2 | Allow `next_beat_anchor: ["object", "null"]` in `music_video_scene_plan` schema; update director doc | `schemas/artifacts/music_video_scene_plan.schema.json` line 95-97, `skills/pipelines/music-video-anime/scene-director.md` line 130-135 |
| 10 | M-4 | Add "re-encode with -g 30" step to `asset-director.md` Step 5 | `skills/pipelines/music-video-anime/asset-director.md` |
| 11 | M-6 | Add cross-reference note in `proposal-director.md` Step 5 to `compose-director.md` governance | `skills/pipelines/music-video-anime/proposal-director.md` |

### Phase 4 — Polish (P2-P3, 1-2 days)

| Order | Bug | Fix | Files |
|---|---|---|---|
| 12 | O-7 | Add CI check `skill-source-drift.yml` (per O-7 fix Option B/C); mark missing modules as `pending_creation` in skill frontmatter | `.github/workflows/skill-source-drift.yml`, all skill files |
| 13 | M-8 | Add missing `metadata.properties` to `music_video_brief` schema (per M-8 fix) | `schemas/artifacts/music_video_brief.schema.json` |
| 14 | M-9 | Add explicit `executive_producer` stage to `pipeline_defs/music-video-anime.yaml` (per M-9 fix) | `pipeline_defs/music-video-anime.yaml:stages` |
| 15 | O-3 | Wire `max_duration_seconds` to `--match-filter "duration:<=N"` in `video_downloader.py`; add CI test for obsolete flag detection | `tools/analysis/video_downloader.py` |

## Total Estimate

| Phase | Effort | Calendar (single engineer) |
|---|---|---|
| Phase 1 | 0.5-1 day | 1-2 days |
| Phase 2 | 1-2 days | 2-3 days |
| Phase 3 | 2-3 days | 4-6 days |
| Phase 4 | 1-2 days | 2-3 days |
| **Total** | **~5-8 engineering days** | **~2 weeks calendar** |

**Reductions after 2026-07-21 verification**:
- O-3 removed (was agent's wrapper script bug, not tool bug) → Phase 4 task 15 dropped
- O-6 fixed by upstream PR #374 → Phase 2 task 5 dropped
- Net reduction: ~1 task (~0.5 day)

## Risk

- **Phase 1 O-5 rewrite** is the highest-risk item: `_generate_index_html` is used by every HyperFrames pipeline, not just music-video-anime. The fix must preserve image-and-typography template behavior while adding cut-list-driven mode.
  - Mitigation: add a `composition_mode: "atelier" | "templated"` parameter that defaults to current behavior; only music-video-anime / beat-synced pipelines opt in to the new mode.
- **Phase 3 M-7 refactor** is the largest delta: 10 new modules + tests + refactor of any existing inline scripts.
  - Mitigation: ship helpers first, then migrate `projects/seisyun-amv/scripts/` to use them in a follow-up PR; do not block other fixes on M-7 completion.

## Success Criteria

After all phases complete, a fresh end-to-end music-video-anime run should:

1. Pass all 4 human-approval gates (proposal, script, scene_plan, assets, publish) without agent workaround
2. Compose stage produces 177s MP4 on first render without agent rewriting `index.html`
3. All `music_video_*` schema validations pass on first try
4. No `decision_log` entries about runtime swap (because HyperFrames works)
5. `lib/pipelines/music_video_anime/` is the only place agents go to build artifacts
6. EP stage emits a `checkpoint_executive_producer.json` and `ep_review` artifact
7. Total wall time < 45 minutes (per `orchestration.max_wall_time_minutes`)

## Filing Plan

| File GitHub Issue | Bugs Covered |
|---|---|
| New: `beat_anchor fails on Windows` | O-1 |
| New: `hyperframes_compose field names don't match music_video_* schemas` | O-4 |
| New: `hyperframes_compose _generate_index_html emits empty timeline` | O-5 |
| ~~New: `video_downloader --max-duration obsolete; max_duration_seconds field unused`~~ | O-3 — **REMOVED 2026-07-21 (not a tool bug)** |
| New: `music_video_render_report over-constrains runtime; no documented fallback path` | M-3 |
| New: `asset-director missing clip re-encode step` | M-4 |
| New: `compose-director assumes tool generates timeline; documents no fallback` | M-5 |
| New: `proposal-director ignores governance schema coupling with compose` | M-6 |
| New: `music_video_anime pipeline missing lib/pipelines/ helpers` | M-7 |
| New: `music_video_script schema target_cut_count inconsistency` | M-1 |
| New: `music_video_scene_plan next_beat_anchor not nullable` | M-2 |
| New: `music_video_brief schema incomplete vs director doc` | M-8 |
| New: `executive_producer stage not implemented in music-video-anime pipeline` | M-9 |
| New: `skill doc/source drift across .agents/skills/` | O-7 |
| ~~Reference existing: #360 (closed by PR #374)~~ | O-6 — **FIXED, no new filing needed** |
| Reference existing: #306, #359 (still open, separate bugs) | (Platform coverage) |

## Order of Filing

To minimize coordination cost, file in this order (each issue is independent):

1. File 13 new issues (one per non-duplicate bug) — can be done in one PR description
2. Submit 4 PRs in priority order (P0 → P3)
3. After each PR, close corresponding issues

Total PRs: 4 (one per phase).

## Tracking

- Use `docs/bugs/2026-07-20-seisyun-amv-run/` as the canonical reference
- Each bug file has a "Status" field; update to "Fixed in PR #N" when closed
- Add a CHANGELOG entry for each closed bug
- Run end-to-end music-video-anime production in CI on each fix to confirm no regression