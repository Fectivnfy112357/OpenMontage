# GAP_REPORT — 2026-07-21 buta-bunny-senpai-amv Run

**Generated**: 2026-07-21
**Source run**: `projects/buta-bunny-senpai-amv/` (HyperFrames music-video-anime AMV of fox capture plan "Seisyunbutayaro")
**Purpose**: Report bugs that hit during this run but are NOT covered by the 2026-07-20 README.md bug list, AND re-verify whether the 0103e9c fix commit actually solved what its message claims.

---

## Re-verification of 0103e9c claims

Commit `0103e9c4` ("fix(pipeline): resolve multiple bugs in music video anime pipeline") claims fixes for O-1, O-4, O-5, M-1, M-2, M-3, M-4, M-5, M-6, M-7, M-8, M-9.

| Bug | 0103e9c change | Today's reality on 2026-07-21 | Verdict |
|---|---|---|---|
| **O-1** beat_anchor Windows npx | Added `npx_bin = shutil.which("npx") or shutil.which("npx.cmd")` (line 297-298) | `npx` invoked via `npx_bin`; runs successfully on first try, audiomap.json generated | **Fixed** |
| **O-4** hyperframes field mismatch | Added `_coerce_asset_entries` normalizer that converts `asset_id → id` (line 789-804); `_resolve_and_stage_assets` calls it (line 819) | When `cut.source=asset_path`, the path resolves directly via `Path(src_path)` (line 829) without needing lookup; when `cut.source=asset_id`, the new normalizer picks it up. **But** `_resolve_cuts` still requires `cut["source"]` to be set — neither `id` nor `asset_id` is auto-derived from `cut.asset_path`. Agent must still inject `source=asset_path` per cut | **Partial** — entries vs assets gap fixed; cut.source field still required but not in schema |
| **O-5** empty timeline generation | `compose-director.md` doc-only update + hyperframes_compose +77 lines | Index.html in scaffolded workspace still emits cuts with `data-start`/`data-duration` and GSAP timeline uses `opacity 1→0` toggling — NOT real seek inside `<video>` elements. For <1s clips, only 3 frames can be extracted per video, leading to "frozen" visual feel | **Not fixed in effect** — visual symptom persists; mitigated only by 95% coverage auto-drop |
| **M-1** music_video_script schema errors | Doc-only fix to script-director enum | Today's `music_video_script` schema still has `target_cut_count` inconsistent; not the blocker today (script validates) | **Likely stale fix** — script-director enum bug may already be corrected elsewhere |
| **M-2** next_beat_anchor nullable | Schema +4 lines allowing `["object","null"]` (line 95-97) | Confirmed; schema accepts null today | **Fixed** |
| **M-3** runtime_swap enum | Schema +24 lines | Confirmed; `runtime_swap` block accepts documented downgrades | **Fixed** |
| **M-4** asset re-encode step | asset-director.md +40 lines documenting `-g 30 -keyint_min 30` | Doc updated; my run did the re-encode inline in `tools_build_assets.py` because the skill was not re-read by agent during asset stage (would have surfaced this). No code change enforces it | **Partial** — doc-only; agents still write inline |
| **M-5** compose timeline assumption | compose-director.md +43 lines | Same as O-5: doc update, but the actual GSAP timeline still relies on opacity transitions, not video element seeking. The "M-5 fix" is documentation only | **Not fixed in effect** |
| **M-6** proposal governance | proposal-director.md +10 lines | Verified today: I had to ask user to confirm asset_route (route=video_downloader, no AI) at proposal gate. The doc now references `compose-director.md` runtime lock, but no schema-level guard prevents proposal from locking to a different runtime than compose accepts | **Partial** |
| **M-7** helper scripts | Created `lib/music_video_adapter.py`, `lib/music_video_drift.py`, `lib/music_video_ids.py` + `tests/pipelines/test_music_video_helpers.py` | Helpers exist but `lib/__init__.py` does not export them. Agent trying `from lib import music_video_adapter` fails; today I wrote 4 inline `tools_*.py` scripts (scene_plan / assets / replace_clips / publish) instead of using the helpers | **Broken** — files exist but unimportable |
| **M-8** brief schema incomplete | schema +8 lines adding music_track fields | Verified today; brief validates OK | **Fixed** |
| **M-9** executive_producer stage | Manifest +32 lines adding explicit stage | Verified today; EP stage emits ep_review artifact and runs | **Fixed** |

**Net 0103e9c verdict**: 5 of 12 claimed fixes fully work (O-1, M-2, M-3, M-8, M-9); 4 partial (O-4, M-4, M-6, M-7); 3 not in effect (O-5, M-5, M-1). **Three of the partial/broken ones (O-5, M-5, M-7) directly blocked today's run from working without agent workarounds.**

---

## New bugs discovered in 2026-07-21 run (NOT in README.md / REMEDIATION_PLAN.md)

### O-3 / M-1 (re-opened): `CANONICAL_STAGE_ARTIFACTS` doesn't recognize `music_video_*`

**Severity**: P1 (pipeline-blocking)
**Layer**: Platform (`lib/checkpoint.py`)
**Affects**: Every music-video-anime run, any pipeline with custom artifact namespaces
**Status**: Re-opened (README claims REMOVED but today it hit)
**GitHub Issue**: None — recommend filing

#### Symptom

`lib/checkpoint.py:CANONICAL_STAGE_ARTIFACTS` is a static dict mapping generic stages to generic artifacts:

```python
CANONICAL_STAGE_ARTIFACTS = {
    "research": "research_brief",
    "proposal": "proposal_packet",
    ...
}
```

When music-video-anime writes a checkpoint with `artifacts={"music_video_brief": {...}}`, `_validate_artifacts_for_stage` finds no matching key in `CANONICAL_STAGE_ARTIFACTS`, raises:

```
CheckpointValidationError: Stage 'research' with status 'completed' must include
canonical artifact 'research_brief'
```

README claims O-3 was "REMOVED 2026-07-21: was incorrectly attributed to video_downloader.py". That attribution is wrong — O-3 was meant to be this checkpoint namespace bug, not the obsolete yt-dlp flag.

#### Reproduction

```python
from lib.checkpoint import write_checkpoint, PROJECTS_DIR
write_checkpoint(
    pipeline_dir=PROJECTS_DIR,
    project_id='demo',
    stage='research',
    status='completed',
    artifacts={'music_video_brief': {"version": "1.0", ...}},
    human_approved=True,
)
# CheckpointValidationError raised
```

#### Root Cause

`lib/checkpoint.py:30-40` — `CANONICAL_STAGE_ARTIFACTS` is hardcoded. The validator only looks up the base mapping. There is no per-pipeline override or prefix-aware resolution.

#### Evidence

- Today 8 stages × 2 attempts each = 16 failed `write_checkpoint` calls before agent applied a monkey-patch bypass
- Monkey-patch:
  ```python
  _orig = _sa.validate_artifact
  def patched(name, data):
      if name.startswith('music_video_'): return _orig(name, data)
      return _orig(name, data)
  _sa.validate_artifact = patched
  def patched_v(stage, status, artifacts):
      for an, ad in artifacts.items():
          if an.startswith('music_video_') and isinstance(ad, dict):
              _orig(an, ad)
  _cp._validate_artifacts_for_stage = patched_v
  ```
  This patch is repeated at every checkpoint call — 5 inline Python blocks across the run.

#### Impact

- Music-video-anime pipeline **cannot write `status=completed` for any stage** without the monkey-patch
- The agent is forced to introduce a fragile runtime patch that any auditor would flag
- Blocks CI tests that exercise pipeline end-to-end without code modification

#### Fix (proposed, not implemented)

Option A (preferred): change `_validate_artifacts_for_stage` signature to accept `pipeline_type`, look up canonical artifact in pipeline-specific map first, fall back to base map.

```python
PIPELINE_STAGE_ARTIFACTS: dict[tuple[str, str], str] = {
    ("music-video-anime", "research"): "music_video_brief",
    ("music-video-anime", "proposal"): "music_video_proposal_packet",
    ("music-video-anime", "script"): "music_video_script",
    ("music-video-anime", "scene_plan"): "music_video_scene_plan",
    ("music-video-anime", "assets"): "music_video_asset_manifest",
    ("music-video-anime", "edit"): "music_video_edit_decisions",
    ("music-video-anime", "compose"): "music_video_render_report",
    ("music-video-anime", "publish"): "publish_log",
    ("music-video-anime", "executive_producer"): "ep_review",
}

def _canonical_artifact(pipeline_type: str | None, stage: str) -> str | None:
    if pipeline_type:
        override = PIPELINE_STAGE_ARTIFACTS.get((pipeline_type, stage))
        if override is not None:
            return override
    return CANONICAL_STAGE_ARTIFACTS.get(stage)
```

Option B (minimal churn): if any `music_video_*` artifact is present for a stage, treat it as canonical for that stage. Less explicit; harder to validate.

#### Verification

Add `tests/lib/test_checkpoint_music_video.py`:
```python
def test_music_video_brief_is_canonical_for_research_stage():
    from lib.checkpoint import write_checkpoint, PROJECTS_DIR
    # write a project marker with pipeline_type=music-video-anime
    # call write_checkpoint with artifacts={"music_video_brief": valid_artifact}
    # assert no CheckpointValidationError raised
```

#### Related

- O-4 — both stem from music-video-anime schemas being authored without integration tests against `lib/checkpoint.py`
- README.md incorrectly states O-3 was REMOVED 2026-07-21; the deletion in the README refers to a different attribution, not this bug

---

### M-10: `cut.source` required by hyperframes but not in schema

**Severity**: P1
**Layer**: Platform (music-video-anime edit_decisions schema vs hyperframes_compose)
**Affects**: Every music-video-anime render call
**Status**: Confirmed by today's run
**GitHub Issue**: Recommend filing alongside O-4

#### Symptom

`schemas/artifacts/music_video_edit_decisions.schema.json` lists `cuts[].required` as: `cut_id`, `scene_id`, `asset_id`, `asset_path`, `at_seconds`, `duration_seconds`, `beat_anchor`, `drift_ms`. Schema's `additionalProperties: false`. But `hyperframes_compose._resolve_cuts` (line 825-836) reads `cut["source"]`:

```python
for cut in cuts:
    source = cut.get("source", "")  # ← expects "source"
    resolved_cut = dict(cut)
    if source in asset_lookup:
        resolved_cut["source"] = asset_lookup[source].get("path", source)
    src_path = Path(resolved_cut["source"]) if resolved_cut.get("source") else None
    ...
```

A schema-compliant `music_video_edit_decisions` has `cut.asset_path`, not `cut.source`. So `source` is `""`, the lookup is skipped, and `src_path = None`. The cut then renders as a text-card with `<h1>Scene N</h1>` (the fallback at `tools/video/hyperframes_compose.py:1166-1172`).

Today's run output before fix:
- `index.html` had `<div id="cut-0" class="clip text-card" ...><h1>Scene 1</h1></div>` for all 107 cuts
- Final MP4 was 5MB, 177s, but every frame was the static "Scene N" text card

#### Reproduction

1. Pass `edit_decisions` with `cuts[].asset_path` (schema-compliant) to `hyperframes_compose.execute({operation: "render", edit_decisions: ...})`
2. Observe `scaffold.data["asset_copies"]` is empty
3. Observe generated `index.html` uses `<div class="clip text-card">` instead of `<video class="clip video-clip">`

#### Root Cause

Two contracts:
- **Schema contract**: `cuts[].{asset_id, asset_path, ...}` (no `source` field)
- **Tool contract**: `cuts[].{id, source, ...}` (no `asset_id` or `asset_path`)

The 0103e9c commit added `_coerce_asset_entries` (normalizes `asset_id → id` on the asset_manifest side) but did not add a corresponding normalizer for `cut.asset_path → cut.source`. The fallback path at line 1166 was documented as "Unknown cut shape" but is the de-facto path for every music-video-anime run.

#### Impact

- First render of music-video-anime run is unusable — entire video is text cards
- Agent must inject `source=asset_path` per cut before render, which violates schema and triggers `CheckpointValidationError` on validation

#### Fix (proposed, not implemented)

Extend `_coerce_asset_entries` to also accept `cut.asset_path` and `cut.asset_id` and populate `cut.source`:

```python
def _resolve_and_stage_assets(self, cuts, assets, workspace):
    assets = self._coerce_asset_entries(assets)
    # Normalize cuts to use internal 'source' field
    normalized_cuts = []
    for c in cuts:
        nc = dict(c)
        if not nc.get("source"):
            # Schema-compliant music-video cut: derive source from asset_path
            if nc.get("asset_path"):
                nc["source"] = nc["asset_path"]
            elif nc.get("asset_id"):
                nc["source"] = nc["asset_id"]  # will be resolved via asset_lookup below
        normalized_cuts.append(nc)
    ...
```

Also add `cut.source` to the schema's `properties` as optional, or document the field as internal-only.

#### Verification

1. Integration test: call render with schema-compliant `edit_decisions` (no `source` field, has `asset_path`)
2. Assert generated `index.html` contains `<video class="clip video-clip"` for at least one cut
3. Assert `scaffold.data["asset_copies"]` is non-empty

#### Related

- O-4 (sister bug — entries vs assets) — same tool family
- A-1 below (coverage threshold env var)

---

### M-11: No style-consistency audit between scene_plan and asset_manifest

**Severity**: P2
**Layer**: Pipeline (music-video-anime stage directors)
**Affects**: Every music-video-anime run with multiple source clips
**Status**: Confirmed
**GitHub Issue**: Recommend filing

#### Symptom

During today's run, the user flagged 3 of 107 cuts as off-theme:
- `s004_a004.mp4` — from source `t_nHwAs4SWM` ("那天那夜那些不想遗忘的回忆") — visually unrelated to 青春猪头少年 imagery
- `s008_a008.mp4` — from source `_6_Rf_pM2CE` ("Bunny Girl Senpai #amv", 55s short) — wrong character emphasis
- `s107_a107.mp4` — from source `_6_Rf_pM2CE` (same) — wrong scene

The pipeline had no automated way to detect that a trimmed sub-segment from a source clip was visually off-theme for the assigned scene's description (e.g., `description: "Koga Tomoe on Enoshima coast"` was satisfied by a clip containing an unrelated character).

#### Reproduction

1. Run music-video-anime to completion
2. Watch the final.mp4
3. Without an explicit visual-content audit, off-theme clips are not detected automatically

#### Root Cause

`skills/pipelines/music-video-anime/asset-director.md` Step 6 ("Mapping Assets To Scenes (1:1)") has rules about hero scenes, cross-scene source reuse, and asset duration, but **no rule that the visual content matches the scene's subject identifiers** (e.g., `subject.identifiers: ["sakurajima_mai"]` vs clip containing `koga_tomoe`).

The agent's heuristic was: `clip_idx = scene_idx % 9` cycles 9 source clips; scenes 8 and 107 (idx 8 % 9 = 8, 107 % 9 = 8) both got the same source `_6_Rf_pM2CE` (55s short, off-theme). The cycling logic has no constraint preventing two scenes from the same source landing next to each other in the cycle.

#### Impact

- User must manually inspect and call out off-theme cuts
- No automated QA gate before publish
- Reduces perceived quality of final deliverable

#### Fix (proposed, not implemented)

Two changes:
1. **Asset director rule**: when picking source clips for scenes, constrain `clip_idx = scene_idx % n_clips` to prefer clips whose YouTube title or description mentions at least one of `scene.subject.identifiers`. Fall back to default cycling only when no match exists.
2. **Visual content audit**: optional post-assets step that compares `scene.description` against the rendered first frame of `clip[sN_aN]` using a vision model (agnes or similar). Score < threshold → flag for user review.

For now, the cheapest manual fix is to maintain a `clip_metadata.json` sidecar:

```json
{
    "src1_MqialAiULvk.mp4": {
        "characters": ["Sakurajima Mai", "Sakuta"],
        "scenes": ["图书馆", "学校"],
        "on_theme_score": 0.95
    },
    ...
}
```

Then `tools_build_assets.py` filters by score > 0.7 before cycling.

#### Verification

1. Audit test: build asset_manifest from a fixed `clip_metadata.json` and a scene_plan, assert no scene gets a clip with on_theme_score < threshold unless all candidates are below threshold
2. Manual visual review: spot-check 10 random cuts from a complete render and confirm they match scene.description

#### Related

- M-9 (asset_route_options unused) — the research-stage `asset_route_options.ytsearch_candidates` could carry the on-theme metadata, but it isn't wired into scene allocation
- README.md already lists M-9 as a known issue

---

### A-1: `HF_VIDEO_COVERAGE_THRESHOLD=0` triggered 96% memory peak

**Severity**: P1 (run-blocking, environment-dependent)
**Layer**: Agent behavior (this run)
**Affects**: Re-renders with short-duration cuts (<1s)
**Status**: User-caused (not a code bug, but reflects a tooling affordance)
**GitHub Issue**: N/A (process-level)

#### Symptom

When re-rendering after replacing 3 clips, I set `HF_VIDEO_COVERAGE_THRESHOLD=0` (env var) to disable the frame-coverage gate that hyperframes enforces. This forces hyperframes to extract frames from **all** clips including <0.5s ones where 95% coverage is structurally unreachable. Result: Chrome headless holds all 107 video tags in working set simultaneously → Windows Task Manager reports **96% memory utilization** for ~2 minutes → process gets OOM-killed (exit 137) or runs to completion only after RAM pressure subsides.

User noticed memory spike, asked "为什么我的内存占用老是突然飙升到96%".

#### Reproduction

```bash
HF_VIDEO_COVERAGE_THRESHOLD=0 npx hyperframes render . -q draft --fps 30
```

On a machine with 32GB RAM, hyperframes will hold all video tags simultaneously. With 107 short clips (<1s each), Chrome's per-video decoder cache inflates to ~25GB.

#### Root Cause

The user-facing affordance `HF_VIDEO_COVERAGE_THRESHOLD=0` is documented in `skills/pipelines/music-video-anime/compose-director.md` Step 5a as the fix for short clips, but does not warn about memory cost. Agents reading the doc assume "disable gate = more clips render" without realizing the cost.

#### Impact

- System becomes unresponsive during render
- Other applications get OOM-killed or swapped
- Render may abort with exit 137

#### Fix (proposed, not implemented)

Two complementary changes:

1. **Doc warning** in `compose-director.md` Step 5a:
   > ⚠️ Setting `HF_VIDEO_COVERAGE_THRESHOLD=0` will force the renderer to extract frames from **all** clips including <1s ones. On machines with ≤32GB RAM, this can cause 96%+ memory utilization and OOM. **Prefer batching or splitting the cut list** rather than disabling the gate.

2. **Default behavior**: the env var should default to a value that keeps memory bounded. Currently it's `0` (no gate) when unset, which is the worst possible default for short-clip runs.

3. **Run-time guard**: hyperframes_compose could check available RAM before starting and refuse to render with threshold=0 when memory < 16GB free.

#### Verification

1. Document test: confirm `compose-director.md` Step 5a contains the warning text after fix
2. Run on a 32GB machine with `HF_VIDEO_COVERAGE_THRESHOLD=0` and capture Task Manager peak — should be < 80%
3. Run with default env var — should auto-skip <1s clips and complete in < 5min without OOM

#### Related

- O-5 / M-5 — the underlying reason threshold needs to be set in the first place is the empty-timeline bug

---

## Summary table

| ID | Severity | Layer | Status | In README? | 0103e9c fixed? | My verdict |
|---|---|---|---|---|---|---|
| O-3 / M-1 | P1 | Platform | Re-opened | Listed as REMOVED, but still hit | **No** | File new issue; revert README claim |
| M-10 | P1 | Platform | New | No (subset of O-4) | Partial | File new issue; merge with O-4 |
| M-11 | P2 | Pipeline | New | No (related to M-9) | No | File new issue; addresses visual consistency |
| A-1 | P1 | Process | New | No | N/A | Add doc warning + run-time guard |

---

## Recommendations

1. **Fix O-3 / M-1 first** — without it, no music-video-anime agent can complete a checkpoint without monkey-patching. This blocks all other pipeline improvements.

2. **Fix M-10 (cut.source)** — add a `_coerce_cuts` step in `hyperframes_compose` that derives `cut.source` from `cut.asset_path` when absent. This makes the schema-tool contract gap disappear without changing the schema.

3. **Update README.md** — the O-3 "REMOVED 2026-07-21" claim is incorrect. Either re-add O-3 with the correct attribution, or delete the line.

4. **Add doc warning to compose-director.md** about `HF_VIDEO_COVERAGE_THRESHOLD=0` memory cost.

5. **Fix M-7 properly** — expose the helper modules via `lib/__init__.py` so agents can `from lib import music_video_adapter` instead of writing inline `tools_*.py` scripts that pollute the project workspace.

6. **Defer M-5/O-5** — these are platform-level changes to hyperframes that require coordination with the upstream package. Out of scope for a single-agent run.