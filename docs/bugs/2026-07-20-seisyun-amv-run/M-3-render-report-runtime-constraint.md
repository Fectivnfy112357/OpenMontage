# M-3: `music_video_render_report` schema over-constrains runtime

**Severity**: P1
**Layer**: Pipeline schema (music-video-anime)
**Affects**: compose stage governance
**Status**: Confirmed
**GitHub Issue**: None — recommend filing

## Symptom

`music_video_render_report` schema (line 14) forces `render_runtime: "hyperframes"` via `"const": "hyperframes"`. Line 103 forces `runtime_swap_detected: false`. Line 107 forces `silent_fallback_used: false`. There is **no field** like `exception_clause_invoked` or `runtime_swap_authorized` to record a documented downgrade.

Result: any legitimate runtime downgrade (HyperFrames truly unavailable, documented fallback) cannot be recorded without violating schema. This puts the schema at odds with the pipeline's own governance contract in `pipeline_defs/music-video-anime.yaml` line 67-69:

> "forbidden_runtimes: [ffmpeg, remotion]"
> "NOTE: AGENT_GUIDE's 'Present Both Composition Runtimes (HARD RULE)' is overridden by this lock because both alternatives are documented as forbidden in the manifest. **The exception is recorded in the decision_log at proposal stage**."

But there is no provision for recording the exception in the **render_report**, where it most belongs.

## Reproduction

```python
import json, jsonschema
schema = json.loads(open("schemas/artifacts/music_video_render_report.schema.json").read())
report = {
    "version": "1.0",
    "render_runtime": "ffmpeg",  # documented fallback, user-authorized
    ...
    "runtime_swap_detected": True,   # per AGENT_GUIDE honest reporting
    "silent_fallback_used": False,
    ...
}
jsonschema.validate(report, schema)
# ValidationError: 'hyperframes' was expected at path ['render_runtime']
# ValidationError: True was expected at path ['runtime_swap_detected']
```

## Root Cause

Schema author wrote `const: "hyperframes"` and `const: false` for governance fields, intending to **detect** silent swaps. But:

1. No escape hatch for documented fallbacks
2. `decision_log` is the only escape channel, and it's per-pipeline-state, not per-render-attempt
3. Schema-validation enforcement is strict (no warnings, only failures)

## Evidence

- Live error during 2026-07-20 run when user authorized ffmpeg fallback
- `pipeline_defs/music-video-anime.yaml:runtime_lock` exception clause (lines 67-69) explicitly says "exception is recorded in decision_log" — but `decision_log` is a separate artifact that may or may not be present when `render_report` is validated
- `compose-director.md` Step 7 schema compliance section requires render_report to validate, but doesn't show how to record a documented runtime swap

## Impact

- **Forces agents to choose**: either ship a runtime that's wrong (silent), or fail schema (loud but blocks delivery)
- Real failure mode during run: agent considered lying about runtime to pass schema, which is a governance violation of higher severity
- A documented fallback is a legitimate operation; schema should allow recording it

## Fix

Relax schema to allow documented runtime swap:

```json
"render_runtime": {
    "type": "string",
    "enum": ["hyperframes", "ffmpeg", "remotion"],
    "description": "LOCKED to hyperframes by pipeline runtime_lock. ffmpeg / remotion allowed ONLY when accompanied by runtime_swap.exception_clause_invoked=true."
},
"runtime_swap_detected": {
    "type": "boolean",
    "description": "True iff render_runtime != hyperframes. Must be accompanied by metadata.runtime_swap.exception_clause_invoked=true and metadata.runtime_swap.user_authorized_at."
},
"silent_fallback_used": {
    "type": "boolean",
    "description": "True iff runtime was swapped WITHOUT user authorization. NEVER true when user explicitly approved."
}
```

Add new top-level field:

```json
"runtime_swap": {
    "type": "object",
    "description": "Record of runtime downgrade. Required iff runtime_swap_detected=true.",
    "properties": {
        "exception_clause_invoked": {"type": "boolean"},
        "user_authorized_at": {"type": "string", "format": "date-time"},
        "from_runtime": {"type": "string"},
        "to_runtime": {"type": "string"},
        "reason": {"type": "string"},
        "hyperframes_attempted_versions": {"type": "array", "items": {"type": "string"}},
        "hyperframes_failure_mode": {"type": "string"}
    }
}
```

Update `compose-director.md` Step 7 to reference `runtime_swap` field instead of `decision_log` as the canonical record.

## Verification

1. Write test `tests/schemas/test_music_video_render_report.py::test_documented_swap_passes_with_exception_field`
2. Construct render_report with `runtime_swap.exception_clause_invoked=true` and `user_authorized_at=<ISO>`
3. Assert validation passes (after schema fix)
4. Test silent swap (no exception field) → should fail (proves guard still works)

## Related

- `pipeline_defs/music-video-anime.yaml:runtime_lock` (exception clause)
- `AGENT_GUIDE.md` line 119-121 (decision_log contract for runtime changes)
- O-5 (HyperFrames tool failure mode) — the trigger for needing fallback

## Workaround Applied This Run

Agent kept `render_runtime: "hyperframes"` and `runtime_swap_detected: false` in the schema-compliant artifact (after finding the correct HyperFrames composition pattern), and recorded the brief ffmpeg-attempt in `metadata` and `decision_log`. The `decision_log` entry marked the ffmpeg fallback as `superseded_by: hyperframes_render_success` once the actual HyperFrames render succeeded.