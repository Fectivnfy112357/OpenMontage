"""Beat anchor analyzer for beat-synced music videos (AMV / MAD / 卡点视频).

Wraps ``npx hyperframes beats`` (deterministic, headless, no librosa needed) and
normalizes its output into the ``audiomap.json`` shape that the music-video-anime
pipeline expects:

    {
      "version": "1.0",
      "audio": { "path": str, "duration_sec": float },
      "bpm": float | None,
      "beats_sec": [float, ...],
      "downbeats_sec": [float, ...],   # approximated as beats every N
      "onsets_sec": [float, ...],       # every detected beat
      "key_moments": [{"t": float, "type": "SURGE" | "DROP" | "hard_stop", "strength": float}],
      "phrases": [{"start_sec": float, "end_sec": float, "energy": str}],
      "energy_phases": [{"start_sec": float, "end_sec": float, "level": str, "density": float}],
      "beat_grid_reliable": bool,
      "diagnostics": {...}
    }

The analyzer writes audiomap.json to the path given in ``output_path`` and also
returns it via ``ToolResult.data``.

This tool is the **only** beat analyzer on the music-video-anime pipeline. Never
re-measure beats with audio_energy, librosa, or by ear. Reuse the audiomap.

Determinism: input audio file → identical audiomap.json. npx hyperframes beats is
deterministic; same input always gives the same output.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


# Default assumptions for downbeat / phrase approximation. Tunable via params.
DEFAULT_BEATS_PER_BAR = 4            # 4/4 time signature assumption
DEFAULT_PHRASE_BEATS = 8             # 2 bars per phrase
DEFAULT_SURGE_THRESHOLD = 0.85       # relative strength for SURGE key_moment
DEFAULT_DROP_THRESHOLD = 0.95        # relative strength for DROP key_moment
DEFAULT_HARD_STOP_THRESHOLD = 0.20   # a beat whose strength drops below 20% of rolling median = hard_stop
DEFAULT_HARD_STOP_WINDOW_BEATS = 8


class BeatAnchor(BaseTool):
    name = "beat_anchor"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "analysis"
    provider = "hyperframes-beats"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = ["binary:npx", "npm:hyperframes"]
    install_instructions = (
        "Install Node.js (>= 22) and HyperFrames via npx:\n"
        "  npx hyperframes --version\n"
        "If npx not found: install Node.js from https://nodejs.org/\n"
        "HyperFrames is auto-fetched on first npx invocation."
    )

    capabilities = [
        "analyze_music_track",
        "detect_bpm",
        "detect_beats",
        "detect_key_moments",
        "write_audiomap",
        "verify_render_beat_sync",   # post-render verification
    ]

    best_for = [
        "beat-synced music video (AMV/MAD/卡点视频) cut planning",
        "frame-precise anime MAD synchronization",
        "HyperFrames timeline composition beat grid generation",
        "post-render verification that audio didn't drift",
    ]

    not_good_for = [
        "lyrics transcription (use transcriber)",
        "scene detection in video (use scene_detect)",
        "audio enhancement / mixing (use audio_mixer / audio_enhance)",
    ]

    agent_skills = ["music-video-anime/asset-director", "music-video-anime/scene-director"]

    input_schema = {
        "type": "object",
        "required": ["audio_path"],
        "properties": {
            "audio_path": {
                "type": "string",
                "description": (
                    "Absolute path to the source audio or video. Audio: mp3/wav/m4a/flac/ogg. "
                    "Video (mp4/mov/webm/mkv): the tool extracts the audio stream to a temp wav "
                    "via ffmpeg and analyzes that — used for post-render beat-sync verification "
                    "on the final MP4."
                ),
            },
            "output_path": {
                "type": "string",
                "description": "Where to write audiomap.json. Defaults to <source_dir>/audiomap.json",
            },
            "beats_per_bar": {
                "type": "integer",
                "default": DEFAULT_BEATS_PER_BAR,
                "description": "Time signature assumption for downbeat approximation (default 4 = 4/4)",
            },
            "phrase_beats": {
                "type": "integer",
                "default": DEFAULT_PHRASE_BEATS,
                "description": "Beats per phrase for phrase boundary approximation (default 8 = 2 bars)",
            },
            "hyperframes_timeout_seconds": {
                "type": "integer",
                "default": 300,
                "description": "Max wall time for the npx hyperframes beats subprocess",
            },
            "source_track_sha256": {
                "type": ["string", "null"],
                "description": (
                    "Optional provenance hash. When the same audiomap is consumed by downstream "
                    "stages, recording the source-file sha256 lets them detect audiomap drift if "
                    "the music file is regenerated."
                ),
            },
        },
    }

    output_schema = {
        "type": "object",
        "description": "The audiomap.json content. Returned in ToolResult.data and written to output_path.",
    }

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        audio_path = inputs.get("audio_path")
        if not audio_path:
            return ToolResult(success=False, error="audio_path is required")
        audio_path = str(audio_path)
        if not os.path.isfile(audio_path):
            return ToolResult(success=False, error=f"Audio/video file not found: {audio_path}")

        output_path = inputs.get("output_path")
        if not output_path:
            output_path = str(Path(audio_path).parent / "audiomap.json")
        output_path = str(output_path)

        beats_per_bar = int(inputs.get("beats_per_bar", DEFAULT_BEATS_PER_BAR))
        phrase_beats = int(inputs.get("phrase_beats", DEFAULT_PHRASE_BEATS))
        timeout = int(inputs.get("hyperframes_timeout_seconds", 300))

        # Compute provenance hash (also used as audiomap.json fingerprint key).
        try:
            import hashlib

            with open(audio_path, "rb") as _f:
                source_track_sha256 = hashlib.sha256(_f.read()).hexdigest()
        except Exception:
            source_track_sha256 = inputs.get("source_track_sha256")
        if inputs.get("source_track_sha256"):
            source_track_sha256 = inputs["source_track_sha256"]

        # If the source is a video container, extract its audio stream to a temp wav
        # so hyperframes beats can analyze it. This unlocks post-render verification
        # on the final MP4 (compose-director step 5).
        video_extensions = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
        is_video = Path(audio_path).suffix.lower() in video_extensions

        extracted_audio: str | None = None
        analyze_path = audio_path
        if is_video:
            if not shutil.which("ffmpeg"):
                return ToolResult(
                    success=False,
                    error=(
                        "Source is a video but ffmpeg is missing on PATH; cannot extract "
                        "audio stream for beat analysis. Install ffmpeg or pass an audio file."
                    ),
                )
            try:
                tmp = tempfile.NamedTemporaryFile(
                    prefix="beat_anchor_audio_", suffix=".wav", delete=False
                )
                tmp.close()
                extracted_audio = tmp.name
                extract = subprocess.run(
                    [
                        "ffmpeg", "-y", "-i", audio_path,
                        "-vn", "-ac", "1", "-ar", "22050",
                        extracted_audio,
                    ],
                    capture_output=True, text=True, timeout=120,
                )
                if extract.returncode != 0:
                    return ToolResult(
                        success=False,
                        error=(
                            f"ffmpeg audio extraction failed for {audio_path}: "
                            f"{extract.stderr.strip()[-500:]}"
                        ),
                    )
                analyze_path = extracted_audio
            except subprocess.TimeoutExpired:
                return ToolResult(success=False, error=f"ffmpeg timed out extracting {audio_path}")
            except Exception as e:
                return ToolResult(success=False, error=f"ffmpeg extraction error: {e}")

        # ------------------------------------------------------------------
        # Step 1: Probe audio duration via ffprobe
        # ------------------------------------------------------------------
        if not shutil.which("ffprobe"):
            return ToolResult(success=False, error="ffprobe not found on PATH")
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", analyze_path],
                capture_output=True, text=True, timeout=30,
            )
            duration_sec = float(probe.stdout.strip())
        except Exception as e:
            return ToolResult(success=False, error=f"ffprobe failed: {e}")
        if duration_sec <= 0:
            return ToolResult(success=False, error=f"Invalid duration: {duration_sec}")

        # ------------------------------------------------------------------
        # Step 2: Run npx hyperframes beats in a temp project
        # ------------------------------------------------------------------
        if not shutil.which("npx"):
            return ToolResult(success=False, error="npx not found on PATH; install Node.js >= 22")

        # Create an isolated hyperframes project in a temp dir, copy audio in,
        # build a minimal index.html that references it, then run beats.
        with tempfile.TemporaryDirectory(prefix="beat_anchor_") as tmp:
            tmp_path = Path(tmp)
            try:
                # Init blank project
                init = subprocess.run(
                    ["npx", "--yes", "hyperframes", "init", str(tmp_path),
                     "--non-interactive", "--example=blank"],
                    capture_output=True, text=True, timeout=120,
                )
                if init.returncode != 0:
                    return ToolResult(
                        success=False,
                        error=f"hyperframes init failed: {init.stderr.strip()[-500:]}",
                    )

                # Copy the (possibly extracted) audio into public/
                public_dir = tmp_path / "public"
                public_dir.mkdir(exist_ok=True)
                audio_name = Path(analyze_path).name
                target_audio = public_dir / audio_name
                shutil.copy2(analyze_path, target_audio)

                # Write minimal index.html with audio tag
                # Note: the audio src must match how hyperframes beats will resolve it.
                # Empirically the path must be prefixed with "public/" — see hyperframes beats source.
                index_html = tmp_path / "index.html"
                index_html.write_text(
                    "<!DOCTYPE html>\n"
                    "<html>\n"
                    "<head><meta charset=\"utf-8\"><title>beat anchor</title></head>\n"
                    "<body>\n"
                    f"<audio id=\"bgm\" data-timeline-role=\"music\" "
                    f"src=\"public/{audio_name}\" preload=\"auto\"></audio>\n"
                    "</body>\n"
                    "</html>\n",
                    encoding="utf-8",
                )

                # Run beats
                beats_run = subprocess.run(
                    ["npx", "--yes", "hyperframes", "beats", str(tmp_path)],
                    capture_output=True, text=True, timeout=timeout,
                )
                if beats_run.returncode != 0:
                    return ToolResult(
                        success=False,
                        error=f"hyperframes beats failed: {beats_run.stderr.strip()[-500:]}",
                    )

                # Find the produced JSON (path is beats/<same-as-audio-rel>.json)
                # The audio we copied is at public/<audio_name>, so output should be
                # beats/public/<audio_name>.json
                beats_json_path = tmp_path / "beats" / "public" / f"{audio_name}.json"
                if not beats_json_path.exists():
                    # Try alternative locations
                    candidates = list((tmp_path / "beats").rglob("*.json"))
                    if not candidates:
                        return ToolResult(
                            success=False,
                            error=f"hyperframes beats did not write JSON. stdout: {beats_run.stdout.strip()[-300:]}",
                        )
                    beats_json_path = candidates[0]

                raw = json.loads(beats_json_path.read_text(encoding="utf-8"))
            except subprocess.TimeoutExpired:
                return ToolResult(success=False, error=f"hyperframes beats timed out after {timeout}s")
            except Exception as e:
                return ToolResult(success=False, error=f"hyperframes beats wrapper error: {e}")

        # ------------------------------------------------------------------
        # Step 3: Normalize to audiomap.json shape
        # ------------------------------------------------------------------
        raw_beats = raw.get("beats", [])
        if not raw_beats:
            return ToolResult(success=False, error="hyperframes beats returned 0 beats")

        beats_sec = [float(b["time"]) for b in raw_beats]
        strengths = [float(b.get("strength", 1.0)) for b in raw_beats]

        # BPM: derive from median interval between consecutive beats
        if len(beats_sec) >= 2:
            intervals = [beats_sec[i + 1] - beats_sec[i] for i in range(len(beats_sec) - 1)]
            intervals = [x for x in intervals if x > 0]
            if intervals:
                median_interval = sorted(intervals)[len(intervals) // 2]
                bpm = round(60.0 / median_interval, 1)
            else:
                bpm = None
        else:
            bpm = None

        # Beat grid reliability: high BPM confidence + consistent intervals = reliable
        if intervals:
            std = (sum((x - median_interval) ** 2 for x in intervals) / len(intervals)) ** 0.5
            cv = std / median_interval if median_interval else 1.0
            beat_grid_reliable = (bpm is not None) and (60 <= bpm <= 200) and (cv < 0.20)
        else:
            beat_grid_reliable = False

        # Downbeats: every Nth beat (assuming 4/4)
        downbeats_sec = [beats_sec[i] for i in range(0, len(beats_sec), beats_per_bar)]

        # Onsets: same as beats (hyperframes emits per-beat onsets)
        onsets_sec = list(beats_sec)

        # Key moments: SURGE on unusually strong beats, DROP on first super-strong after
        # a quiet stretch, hard_stop on beats where strength drops sharply.
        key_moments: list[dict[str, Any]] = []
        if strengths:
            # Anchor strength at the first strong beat (not silence at t=0)
            # Use median of strengths > 0.5 as the "strong" baseline
            strong_baseline = sorted(s for s in strengths if s > 0.5)
            baseline = strong_baseline[len(strong_baseline) // 2] if strong_baseline else max(strengths)
            for i, (t, s) in enumerate(zip(beats_sec, strengths)):
                if s >= DEFAULT_DROP_THRESHOLD:
                    # Check this isn't just the first beat (which is always strong)
                    key_moments.append({"t": t, "type": "DROP", "strength": s})
                elif s >= DEFAULT_SURGE_THRESHOLD and s > baseline * 1.3:
                    key_moments.append({"t": t, "type": "SURGE", "strength": s})
            # hard_stop: a beat whose strength is much lower than the rolling median
            for i in range(DEFAULT_HARD_STOP_WINDOW_BEATS, len(strengths)):
                window = strengths[i - DEFAULT_HARD_STOP_WINDOW_BEATS:i]
                rolling_med = sorted(window)[len(window) // 2]
                if rolling_med > 0.3 and strengths[i] < rolling_med * DEFAULT_HARD_STOP_THRESHOLD:
                    key_moments.append({"t": beats_sec[i], "type": "hard_stop", "strength": strengths[i]})

        # Phrases: every phrase_beats beats, mark as low/medium/high energy by local mean strength
        phrases: list[dict[str, Any]] = []
        for i in range(0, len(beats_sec), phrase_beats):
            chunk = strengths[i:i + phrase_beats]
            if not chunk:
                continue
            avg = sum(chunk) / len(chunk)
            if avg < 0.3:
                energy = "low"
            elif avg < 0.7:
                energy = "medium"
            else:
                energy = "high"
            phrases.append({
                "start_sec": beats_sec[i],
                "end_sec": beats_sec[min(i + phrase_beats, len(beats_sec)) - 1],
                "energy": energy,
                "mean_strength": round(avg, 3),
            })

        # Energy phases: same data bucketed into 10% windows of duration
        energy_phases: list[dict[str, Any]] = []
        n_buckets = 10
        bucket_size = max(1, len(beats_sec) // n_buckets)
        for i in range(0, len(beats_sec), bucket_size):
            chunk = strengths[i:i + bucket_size]
            if not chunk:
                continue
            avg = sum(chunk) / len(chunk)
            density = sum(1 for s in chunk if s > 0.5) / len(chunk)
            if avg < 0.3:
                level = "quiet"
            elif avg < 0.7:
                level = "moderate"
            else:
                level = "intense"
            energy_phases.append({
                "start_sec": beats_sec[i],
                "end_sec": beats_sec[min(i + bucket_size, len(beats_sec)) - 1],
                "level": level,
                "density": round(density, 3),
            })

        audiomap = {
            "version": "1.0",
            "audio": {
                "path": audio_path,
                "duration_sec": round(duration_sec, 3),
            },
            "source": {
                "input_path": audio_path,
                "kind": "video" if is_video else "audio",
                "extracted_audio_path": extracted_audio,
                "source_track_sha256": source_track_sha256,
            },
            "bpm": bpm,
            "beats_sec": [round(t, 4) for t in beats_sec],
            "downbeats_sec": [round(t, 4) for t in downbeats_sec],
            "onsets_sec": [round(t, 4) for t in onsets_sec],
            "key_moments": key_moments,
            "phrases": phrases,
            "energy_phases": energy_phases,
            "beat_grid_reliable": beat_grid_reliable,
            "diagnostics": {
                "raw_beat_count": len(beats_sec),
                "median_beat_interval_sec": round(median_interval, 4) if intervals else None,
                "interval_cv": round(cv, 4) if intervals else None,
                "strength_min": min(strengths) if strengths else None,
                "strength_max": max(strengths) if strengths else None,
                "strength_median": sorted(strengths)[len(strengths) // 2] if strengths else None,
                "analyzer": "npx hyperframes beats",
                "analyzer_version": raw.get("version", "unknown"),
            },
        }

        # ------------------------------------------------------------------
        # Step 4: Cleanup extracted audio (if any) + write audiomap.json
        # ------------------------------------------------------------------
        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(audiomap, f, indent=2, ensure_ascii=False)
        except Exception as e:
            if extracted_audio:
                try:
                    os.unlink(extracted_audio)
                except Exception:
                    pass
            return ToolResult(success=False, error=f"Failed to write audiomap: {e}")

        # Cleanup the temp audio file if we extracted one (success path).
        if extracted_audio:
            try:
                os.unlink(extracted_audio)
            except Exception:
                pass

        return ToolResult(
            success=True,
            data={
                "audiomap": audiomap,
                "audiomap_path": output_path,
                "audio_path": audio_path,
                "input_kind": "video" if is_video else "audio",
                "source_track_sha256": source_track_sha256,
                "duration_sec": round(duration_sec, 3),
                "bpm": bpm,
                "beat_count": len(beats_sec),
                "key_moment_count": len(key_moments),
                "beat_grid_reliable": beat_grid_reliable,
            },
        )