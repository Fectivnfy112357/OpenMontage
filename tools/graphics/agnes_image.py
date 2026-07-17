"""Agnes Image 2.1 Flash — text-to-image and image-to-image generation.

Provider: Agnes AI (Sapiens AI)
API: https://apihub.agnes-ai.com/v1/images/generations
Model: agnes-image-2.1-flash

Key contract notes:
- response_format goes in extra_body, NOT top-level
- img2img uses extra_body.image array, NOT tags: ["img2img"]
- Supports both URL and Data URI Base64 input images
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


class AgnesImage(BaseTool):
    name = "agnes_image"
    version = "0.2.0"
    tier = ToolTier.GENERATE
    capability = "image_generation"
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
        "generate_image",
        "text_to_image",
        "image_to_image",
        "style_transfer",
    ]
    supports = {
        "negative_prompt": False,
        "seed": False,
        "custom_size": True,
        "reference_image": True,
        "data_uri_input": True,
    }
    best_for = [
        "high-density complex images",
        "anime/manga style generation",
        "image-to-image with composition preservation",
        "cinematic concept art",
    ]
    not_good_for = [
        "text rendering in images",
        "offline generation",
        "images with exact seed reproducibility",
    ]

    input_schema = {
        "type": "object",
        "required": ["prompt"],
        "properties": {
            "prompt": {"type": "string"},
            "size": {"type": "string", "default": "1024x768"},
            "image_url": {
                "type": "string",
                "description": "Public URL of input image for img2img",
            },
            "image_path": {
                "type": "string",
                "description": "Local path to input image (auto-converted to data URI)",
            },
            "return_base64": {"type": "boolean", "default": False},
            "output_path": {"type": "string"},
            "timeout": {"type": "integer", "default": 360},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=512, vram_mb=0, disk_mb=100, network_required=True
    )
    retry_policy = RetryPolicy(
        max_retries=2, retryable_errors=["rate_limit", "timeout"]
    )
    idempotency_key_fields = ["prompt", "size", "image_url", "image_path"]
    side_effects = [
        "writes image file to output_path",
        "calls Agnes AI API (costs credits)",
    ]
    user_visible_verification = [
        "Inspect generated image for quality and prompt alignment"
    ]

    AGNES_IMAGE_BASE = "https://apihub.agnes-ai.com"
    AGNES_IMAGE_MODEL = "agnes-image-2.1-flash"

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
            "gif": "image/gif",
        }
        mime = mime_map.get(ext, "image/png")
        data = p.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{b64}"

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.02  # approximate per-image cost

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        import requests

        api_key = self._get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                error="No AGNES_API_KEY found. " + self.install_instructions,
            )

        start = time.time()
        prompt = inputs["prompt"]
        size = inputs.get("size", "1024x768")
        return_base64 = inputs.get("return_base64", False)
        timeout = inputs.get("timeout", 360)

        # Build payload
        payload: dict[str, Any] = {
            "model": self.AGNES_IMAGE_MODEL,
            "prompt": prompt,
            "size": size,
        }

        # Image input (img2img)
        image_url = inputs.get("image_url")
        image_path = inputs.get("image_path")
        if image_path:
            image_url = self._resolve_local_image(image_path)

        if image_url:
            payload.setdefault("extra_body", {})["image"] = [image_url]

        # Output format
        if return_base64:
            payload["return_base64"] = True
        else:
            payload.setdefault("extra_body", {})["response_format"] = "url"

        try:
            response = requests.post(
                f"{self.AGNES_IMAGE_BASE}/v1/images/generations",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Agnes image generation failed: {e}",
            )

        # Extract result
        if return_base64:
            image_data = data.get("data", [{}])[0].get("b64_json")
            if not image_data:
                return ToolResult(
                    success=False,
                    error="Agnes returned no b64_json data",
                )
            image_bytes = base64.b64decode(image_data)
            output_path = Path(
                inputs.get("output_path", "agnes_image.png")
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_bytes)
        else:
            image_url = data.get("data", [{}])[0].get("url")
            if not image_url:
                return ToolResult(
                    success=False,
                    error="Agnes returned no image URL",
                )
            image_response = requests.get(image_url, timeout=60)
            image_response.raise_for_status()
            output_path = Path(
                inputs.get("output_path", "agnes_image.png")
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_response.content)

        return ToolResult(
            success=True,
            data={
                "provider": "agnes",
                "model": self.AGNES_IMAGE_MODEL,
                "prompt": prompt,
                "size": size,
                "output": str(output_path),
                "image_url": image_url if not return_base64 else None,
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost(inputs),
            duration_seconds=round(time.time() - start, 2),
            model=f"agnes/{self.AGNES_IMAGE_MODEL}",
        )