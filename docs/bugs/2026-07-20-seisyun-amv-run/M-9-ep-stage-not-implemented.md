# M-9: EP (executive-producer) stage not implemented as explicit stage

**Severity**: P2
**Layer**: Pipeline structure (music-video-anime)
**Affects**: Orchestration
**Status**: Confirmed
**GitHub Issue**: None — recommend filing

## Symptom

`pipeline_defs/music-video-anime.yaml:orchestration` (lines 28-36) declares:

```yaml
orchestration:
  mode: executive-producer
  skill: pipelines/music-video-anime/executive-producer
  budget_default_usd: 0.50
  max_revisions_per_stage: 3
  max_send_backs: 2
  max_wall_time_minutes: 45
```

But `stages:` (line 103-320) only lists 8 stages: `research, proposal, script, scene_plan, assets, edit, compose, publish`. The `executive-producer` role is **not** listed as a stage.

There's a `skills/pipelines/music-video-anime/executive-producer.md` skill file (in `required_skills` at line 47), but it's not tied to any explicit stage or tool flow.

During the 2026-07-20 run, the EP role was implicitly performed by the agent (me) — orchestrating stage transitions, recording decisions, applying user pre-authorization. But:

1. No `checkpoint_executive_producer.json` exists
2. No `decision_log.ep_decision` field exists
3. No `human_approval_default` for EP-stage gates

Result: EP behavior is undocumented and non-reproducible. Different agents may make different EP-style decisions.

## Reproduction

```bash
ls skills/pipelines/music-video-anime/executive-producer.md
# exists

ls pipeline_defs/music-video-anime.yaml | xargs grep "executive-producer"
# orchestration.mode: executive-producer
# orchestration.skill: pipelines/music-video-anime/executive-producer
# But no stages[].name: executive-producer
```

## Root Cause

`orchestration.mode` and `orchestration.skill` are declarative pointers but no stage is defined to invoke the skill. The EP is treated as a "side effect" of agent reading, not as a checkable gate.

## Evidence

- `pipeline_defs/music-video-anime.yaml:orchestration` lines 28-36
- `pipeline_defs/music-video-anime.yaml:stages` lines 103-320 (no EP stage)
- `skills/pipelines/music-video-anime/executive-producer.md` exists
- Live run: 8 `checkpoint_<stage>.json` files, no `checkpoint_executive_producer.json`

## Impact

- EP behavior is "in the agent's head" — different agents may make different decisions
- Budget tracking (`budget_default_usd: 0.50`) is meaningless without an EP gate
- `max_wall_time_minutes: 45` not enforced
- `decision_log.ep_decision` not consistently populated

## Fix

Add explicit EP stage to `pipeline_defs/music-video-anime.yaml`:

```yaml
stages:
  # ... existing stages ...
  
  - name: executive_producer
    skill: pipelines/music-video-anime/executive-producer
    produces:
      - decision_log
      - ep_review  # new artifact for budget/timeline/revisions tracking
    checkpoint_required: true
    human_approval_default: false  # EP auto-runs unless human flags intervention
    tools_available:
      - checkpoint
      - decision_log
    review_focus:
      - "Budget consumption within $0.50 default"
      - "Wall time within 45 minutes"
      - "Revision count within 3 per stage"
      - "Send-back count within 2"
    success_criteria:
      - "Schema-valid ep_review artifact"
      - "All stages within budget/time/revision limits"
```

Add `ep_review` schema in `schemas/artifacts/ep_review.schema.json`.

## Verification

1. Add EP stage to manifest
2. Run end-to-end production
3. Assert `checkpoint_executive_producer.json` exists
4. Assert `decision_log.ep_decision` field is populated
5. Assert `ep_review.budget_consumed_usd <= 0.50` and `ep_review.wall_time_minutes <= 45`

## Related

- M-7 (missing helper scripts) — EP orchestration would live in `lib/pipelines/music_video_anime/orchestrator.py`
- `pipeline_defs/music-video-anime.yaml:orchestration` (the existing partial implementation)
- `skills/pipelines/music-video-anime/executive-producer.md` (the skill with no caller)

## Workaround Applied This Run

Agent (acting as EP) made decisions ad-hoc:
- Recorded `decision_log.json#approval_policy_full_run` (full-run pre-authorization)
- Updated `decision_log.json#runtime_swap_hyperframes_to_ffmpeg` (later superseded)
- Manually tracked budget ($0.00, all tools local/free) and time (9.5h) in conversation

These are not reproducible from artifacts alone — only from the conversation log.