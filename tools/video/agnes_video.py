"""Agnes Video V2.0 — text-to-video, image-to-video, multi-image, keyframes.

Provider: Agnes AI (Sapiens AI)
API: POST https://apihub.agnes-ai.com/v1/videos (create)
     GET  https://apihub.agnes-ai.com/agnesapi?video_id=<ID> (poll)
Model: agnes-video-v2.0

Key contract notes:
- Async API: create task → poll with video_id until completed
- num_frames must follow 8n+1 rule (25/33/41/49/57/65/73/81/89/97/105/113/121/.../441)
- Supports img2vid (single image), multi-img (extra_body.image array), keyframes (extra_body.mode: "keyframes")
- Response has "error": null at top level — use truthy check, NOT "error" in result
- Middle states have internal_status, NOT status — read both
- Video URL is in "url" field (v2.0), fallback to "remixed_from_video_id"
- 400 content_policy_violation: rephrase prompt, avoid triggering words
- 500 Unknown error: provider-side transient, retry with different payload
"""

from __future__ import annotations

import base64
import os
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


class AgnesVideo(BaseTool):
    name = "agnes_video"
    version = "0.2.0"
    tier = ToolTier.GENERATE
    capability = "video_generation"
    provider = "agnes"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["env:AGNES_API_KEY"]
    install_instructions = (
        "Set AGNES_API_KEY to your Agnes AI API key.\n"
        "  Get one from https://wiki.agnes-ai.com"
    )
    agent_skills = ["agnes-media"]

    capabilities = [
        "text_to_video",
        "image_to_video",
        "multi_image_video",
        "keyframe_animation",
    ]
    supports = {
        "reference_image": True,
        "multi_image": True,
        "keyframes": True,
        "offline": False,
        "native_audio": False,
    }
    best_for = [
        "anime-style video generation",
        "cinematic concept clips",
        "image-to-video with style preservation",
        "keyframe-driven animations",
    ]
    not_good_for = [
        "real-time generation",
        "long-form videos (>18s)",
        "text rendering in video",
        "exact seed reproducibility",
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string"},
            "mode": {
                "type": "string",
                "enum": ["txt2vid", "img2vid", "multi-img", "keyframes"],
                "default": "txt2vid",
            },
            "image_url": {
                "type": "string",
                "description": "Single public image URL for img2vid mode",
            },
            "image_path": {
                "type": "string",
                "description": "Single local image path for img2vid (auto-converted to data URI)",
            },
            "image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Multiple public image URLs for multi-img or keyframes",
            },
            "image_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Multiple local image paths (each converted to data URI)",
            },
            "width": {"type": "integer", "default": 1152},
            "height": {"type": "integer", "default": 768},
            "num_frames": {"type": "integer", "default": 121},
            "frame_rate": {"type": "integer", "default": 24},
            "num_inference_steps": {"type": "integer"},
            "seed": {"type": "integer"},
            "negative_prompt": {"type": "string"},
            "output_path": {"type": "string"},
            "poll_interval": {"type": "integer", "default": 5},
            "max_wait": {"type": "integer", "default": 600},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=500, network_required=True
    )
    retry_policy = RetryPolicy(
        max_retries=2, retryable_errors=["rate_limit", "timeout", "poll_timeout"]
    )
    idempotency_key_fields = [
        "prompt", "mode", "image_url", "image_path",
        "width", "height", "num_frames", "seed",
    ]
    side_effects = [
        "writes video file to output_path",
        "calls Agnes AI API (costs credits)",
        "may poll for up to max_wait seconds",
    ]
    user_visible_verification = [
        "Watch generated video for motion quality and artifacts",
        "Verify style consistency with reference image if img2vid",
    ]

    AGNES_API_BASE = "https://apihub.agnes-ai.com"
    AGNES_VIDEO_MODEL = "agnes-video-v2.0"

    # Valid num_frames: 8n+1, max 441
    VALID_NUM_FRAMES = frozenset(
        n for n in range(25, 442) if (n - 1) % 8 == 0
    )

    def _get_api_key(self) -> str | None:
        return os.environ.get("AGNES_API_KEY")

    def get_status(self) -> ToolStatus:
        if self._get_api_key():
            return ToolStatus.AVAILABLE
        return ToolStatus.UNAVAILABLE

    def _resolve_local_image(self, image_path: str) -> str:
        """Convert a local image file to a data URI for Agnes API."""
        p = Path(image_path)
        if not p.is_file():
            raise FileNotFoundError(f"Image not found: {image_path}")
        ext = p.suffix.lower().lstrip(".")
        mime_map = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "webp": "image/webp",
        }
        mime = mime_map.get(ext, "image/png")
        data = p.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"

    def _clamp_num_frames(self, num_frames: int) -> int:
        """Clamp to nearest valid 8n+1 value."""
        if num_frames in self.VALID_NUM_FRAMES:
            return num_frames
        valid = sorted(self.VALID_NUM_FRAMES)
        # Find nearest valid value
        for v in valid:
            if v >= num_frames:
                return v
        return valid[-1]  # max 441

    def _prepare_payload(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Build the Agnes video creation payload."""
        import requests as _requests  # only for importing; unused

        prompt = inputs["prompt"]
        mode = inputs.get("mode", "txt2vid")
        width = inputs.get("width", 1152)
        height = inputs.get("height", 768)
        num_frames = inputs.get("num_frames", 121)
        frame_rate = inputs.get("frame_rate", 24)

        num_frames = self._clamp_num_frames(num_frames)

        payload: dict[str, Any] = {
            "model": self.AGNES_VIDEO_MODEL,
            "prompt": prompt,
            "width": width,
            "height": height,
            "num_frames": num_frames,
            "frame_rate": frame_rate,
        }

        if inputs.get("num_inference_steps"):
            payload["num_inference_steps"] = inputs["num_inference_steps"]
        if inputs.get("seed") is not None:
            payload["seed"] = inputs["seed"]
        if inputs.get("negative_prompt"):
            payload["negative_prompt"] = inputs["negative_prompt"]

        # Image input handling
        image_url = inputs.get("image_url")
        image_path = inputs.get("image_path")
        image_urls = inputs.get("image_urls")
        image_paths = inputs.get("image_paths")

        if mode in ("img2vid",):
            if image_path:
                image_url = self._resolve_local_image(image_path)
            if image_url:
                payload["image"] = image_url

        elif mode in ("multi-img", "keyframes"):
            urls: list[str] = list(image_urls or [])
            if image_paths:
                for p in image_paths:
                    urls.append(self._resolve_local_image(p))
            if urls:
                payload.setdefault("extra_body", {})["image"] = urls
            if mode == "keyframes":
                payload.setdefault("extra_body", {})["mode"] = "keyframes"

        return payload

    def _poll(self, video_id: str, api_key: str, max_wait: int, poll_interval: int) -> dict[str, Any]:
        """Poll for video completion. Returns the final result dict."""
        import requests

        deadline = time.time() + max_wait

        while time.time() < deadline:
            try:
                resp = requests.get(
                    f"{self.AGNES_API_BASE}/agnesapi",
                    params={"video_id": video_id},
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=30,
                )
                resp.raise_for_status()
                result = resp.json()
            except Exception as e:
                # Transient network error — retry after interval
                time.sleep(poll_interval)
                continue

            # BUGFIX: middle states have internal_status, not status
            status = result.get("status") or result.get("internal_status")

            if status == "completed":
                return result
            elif status == "failed":
                return result
            elif status in ("queued", "in_progress", "inference", None):
                time.sleep(poll_interval)
                continue
            else:
                # Unknown status — wait
                time.sleep(poll_interval)

        return {"status": "poll_timeout", "error": "Max wait time exceeded"}

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        num_frames = inputs.get("num_frames", 121)
        # Rough estimate: ~$0.04 per 25 frames
        return round(num_frames / 25 * 0.04, 2)

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        import requests

        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error="No AGNES_API_KEY found. " + self.install_instructions,
            )

        start = time.time()
        max_wait = inputs.get("max_wait", 600)
        poll_interval = inputs.get("poll_interval", 5)

        # Build and submit payload
        try:
            payload = self._prepare_payload(inputs)
        except FileNotFoundError as e:
            return ToolResult(success=False, error=str(e))

        # Submit creation task
        try:
            response = requests.post(
                f"{self.AGNES_API_BASE}/v1/videos",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
            )
            if response.status_code == 400:
                resp_json = response.json()
                if resp_json.get("code") == "content_policy_violation":
                    return ToolResult(
                        success=False,
                        error=(
                            f"Content policy violation: {resp_json.get('message', '')}. "
                            "Try rephrasing the prompt to avoid triggering words."
                        ),
                    )
            response.raise_for_status()
            create_data = response.json()
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Agnes video creation failed: {e}",
            )

        video_id = create_data.get("video_id")
        if not video_id:
            return ToolResult(
                success=False,
                error=f"Agnes did not return a video_id. Response: {create_data}",
            )

        # Poll for completion
        result = self._poll(video_id, api_key, max_wait, poll_interval)

        if result.get("status") == "poll_timeout":
            return ToolResult(
                success=False,
                error=(
                    f"Agnes video polling timed out after {max_wait}s. "
                    f"video_id={video_id} may still be processing."
                ),
                data={"video_id": video_id},
            )

        if result.get("status") == "failed":
            return ToolResult(
                success=False,
                error=f"Agnes video generation failed: {result.get('error', 'unknown error')}",
                data={"video_id": video_id},
            )

        # BUGFIX: use truthy check, not "error" in result
        # Response has "error": null at top level for successful tasks
        if result.get("error"):
            return ToolResult(
                success=False,
                error=f"Agnes video generation error: {result['error']}",
                data={"video_id": video_id},
            )

        # Extract video URL
        # v2.0 puts URL in "url" field, fallback to "remixed_from_video_id"
        video_url = (
            result.get("url")
            or result.get("video_url")
            or result.get("remixed_from_video_id")
        )
        if not video_url:
            return ToolResult(
                success=False,
                error=f"Agnes completed but returned no video URL. Response keys: {list(result.keys())}",
                data={"video_id": video_id, "result": result},
            )

        # Download video
        output_path = Path(
            inputs.get("output_path", f"agnes_video_{video_id}.mp4")
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            video_response = requests.get(video_url, timeout=120, stream=True)
            video_response.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in video_response.iter_content(chunk_size=8192):
                    f.write(chunk)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Agnes video download failed: {e}",
                data={"video_url": video_url, "video_id": video_id},
            )

        return ToolResult(
            success=True,
            data={
                "provider": "agnes",
                "model": self.AGNES_VIDEO_MODEL,
                "video_id": video_id,
                "prompt": inputs["prompt"],
                "mode": inputs.get("mode", "txt2vid"),
                "output": str(output_path),
                "size": result.get("size"),
                "seconds": result.get("seconds"),
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=f"agnes/{self.AGNES_VIDEO_MODEL}",
        )