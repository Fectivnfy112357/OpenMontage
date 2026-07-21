# M-6: `proposal-director` ignores governance schema coupling

**Severity**: P2
**Layer**: Pipeline skill (music-video-anime)
**Affects**: proposal → compose transition
**Status**: Confirmed
**GitHub Issue**: None — recommend filing

## Symptom

`skills/pipelines/music-video-anime/proposal-director.md` Step 4-5 instructs the agent to lock `render_runtime: hyperframes` in `music_video_proposal_packet.production_plan`. But the skill does NOT inform the agent that:

1. The corresponding `music_video_render_report` schema (line 14) uses `const: "hyperframes"` (per M-3) — meaning a fallback would break schema at compose time
2. There is no `runtime_swap_authorized` field in render_report schema (per M-3)
3. The decision_log exception clause (per `pipeline_defs/music-video-anime.yaml:runtime_lock` lines 67-69) is the ONLY documented escape channel, but it's not surfaced as required reading in compose-director

Net: agents lock hyperframes at proposal without understanding the governance trap that locks them at compose too.

## Reproduction

```python
# Agent follows proposal-director.md literally:
packet = {
    "production_plan": {"render_runtime": "hyperframes", ...},
    "runtime_lock_record": {"locked_choice": "hyperframes", ...},
}
# approved by user

# ... later, at compose stage, agent tries to use ffmpeg fallback ...
# ... render_report schema rejects ffmpeg runtimes (per M-3) ...
# Agent must either fail schema or lie about runtime
```

## Root Cause

The proposal-director skill is written in isolation from the compose-director skill. Cross-stage governance coupling (proposal locks → compose must honor) is implicit in the schema but not surfaced in the director docs.

## Evidence

- `proposal-director.md` Step 5: "production_plan.render_runtime: hyperframes" — no mention of compose-stage consequences
- `compose-director.md` Step 7 ("Record The Render Report"): includes `render_runtime: hyperframes` but doesn't reference back to proposal
- Live run during 2026-07-20: when user authorized ffmpeg fallback, agent hit the trap described in M-3 and had to fall back to a successful HyperFrames render instead

## Impact

- Agents can't make informed decisions about runtime lock severity
- "Fallback" pathways are undocumented
- Pipeline feels rigid in unexpected ways

## Fix

**Option A (minimal)**: in `proposal-director.md` Step 5, add explicit note:

```markdown
> **NOTE**: This lock is enforced by `music_video_render_report` schema (line 14).
> Any runtime other than "hyperframes" requires `runtime_swap_detected=true`
> and a `runtime_swap` field in render_report — see compose-director Step 7.
> No graceful fallback path exists; the only escape is the decision_log exception clause.
```

**Option B (recommended)**: refactor M-3 fix to add a `runtime_swap` field in render_report schema. Then update both director docs to reference the new field as the canonical exception record.

## Verification

Per M-3 verification. This bug is fixed transitively.

## Related

- M-3 (render_report schema over-constrains runtime)
- `pipeline_defs/music-video-anime.yaml:runtime_lock` exception clause

## Workaround Applied This Run

None — agent hit the trap and had to fall back to making HyperFrames work (which it did, after M-5 workaround). Documented in `decision_log.json` entry `hyperframes_render_success`.