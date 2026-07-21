# O-1: beat_anchor.py subprocess fails on Windows with WinError 2

**Severity**: P0
**Layer**: Platform (tool: `tools/analysis/beat_anchor.py`)
**Affects**: Every pipeline that calls `beat_anchor` (music-video-anime, any music-driven workflow)
**Status**: Confirmed (verified live during run)
**GitHub Issue**: None directly — recommend filing. Related: #396 (Windows + WSL2: 6+ hours, 15+ issues)

## Symptom

`BeatAnchor().execute({...})` returns `ToolResult(success=False, error="hyperframes beats wrapper error: [WinError 2] 系统找不到指定的文件。")` on Windows native Python.

## Reproduction

```python
from tools.analysis.beat_anchor import BeatAnchor
t = BeatAnchor()
r = t.execute({
    "audio_path": r"D:\path\to\track.wav",
    "output_path": r"D:\path\to\audiomap.json",
})
# r.success == False
# r.error == "hyperframes beats wrapper error: [WinError 2] ..."
```

## Root Cause

`tools/analysis/beat_anchor.py` line 293-294:

```python
beats_run = subprocess.run(
    ["npx", "--yes", "hyperframes", "beats", str(tmp_path)],
    capture_output=True, text=True, timeout=timeout,
)
```

Python's `subprocess.run` on Windows uses `CreateProcess` directly without consulting `PATHEXT`. `npx` exists as `npx.CMD` but Python's `subprocess` does not auto-resolve `.CMD` extensions. `CreateProcess` returns `ERROR_FILE_NOT_FOUND` (WinError 2).

Verified: `shutil.which("npx")` returns `D:\programming\devtools\nodejs\npx.CMD`, so the binary is on PATH; the issue is subprocess resolution, not PATH.

## Evidence

- Live error during 2026-07-20 run (capture in `projects/seisyun-amv/scripts/write_proposal.py` → beat_anchor subprocess call)
- Direct repro: `python -c "import subprocess; subprocess.run(['npx', '--version'])"` → `FileNotFoundError: [WinError 2]`
- Confirmed fix at runtime: `subprocess.run(..., shell=True)` OR `subprocess.run(["npx.cmd", ...])` both succeed

## Impact

- Blocks **every music-driven analysis** on Windows
- Forces agents to bypass the tool and re-implement `npx hyperframes beats` invocation manually
- No test coverage on Windows (CI likely Linux/macOS — Windows-only path never exercised)

## Fix

**Option A (minimal, recommended)**: in `tools/analysis/beat_anchor.py`, change all `subprocess.run(["npx", ...])` to `subprocess.run(["npx.cmd", ...])`. Single-line edit, zero behavior change on non-Windows.

**Option B (cross-platform safe)**: detect OS at module load:

```python
import sys
NPM_CMD = "npx.cmd" if sys.platform == "win32" else "npx"
```

Then use `subprocess.run([NPM_CMD, ...])`.

**Option C (most portable, robust)**: use `shutil.which("npx")` at call time and resolve to whichever form exists.

```python
npx_path = shutil.which("npx") or shutil.which("npx.cmd")
if not npx_path:
    return ToolResult(success=False, error="npx not found on PATH")
subprocess.run([npx_path, "--yes", "hyperframes", "beats", str(tmp_path)], ...)
```

## Verification

1. Write a failing test: `tests/analysis/test_beat_anchor.py::test_windows_npx_resolution` that imports `BeatAnchor` and verifies it does not raise `FileNotFoundError` on Windows.
2. Apply Option C fix.
3. Run the test on Windows native: should pass.
4. Run the test on Linux CI: should still pass (Option C falls through to `npx`).

## Related

- O-3 (yt-dlp CLI flag drift) — same family of "Windows / external-CLI boundary issues"
- Issue #396 (Windows + WSL2) — broader Windows compatibility report; this bug is a subset
- Issue #237 (Local zero-key rendering) — similar Windows asset-path issues

## Workaround Applied This Run

Agent bypassed `BeatAnchor.execute()` and called `npx hyperframes beats` directly with `shell=True`, then normalized the JSON output to `audiomap.json` schema by hand. The workaround is recorded in `audiomap.json` `diagnostics.note` field.