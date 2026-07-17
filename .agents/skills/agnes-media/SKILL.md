# Agnes AI Media — Agent Skill (Layer 3)

Agnes AI provides image generation (Agnes Image 2.1 Flash) and video generation (Agnes Video V2.0) via a REST API at `https://apihub.agnes-ai.com`.

## Quick Reference

| Capability | Model | Endpoint | Mode |
|---|---|---|---|
| text-to-image | `agnes-image-2.1-flash` | `POST /v1/images/generations` | sync |
| image-to-image | `agnes-image-2.1-flash` | `POST /v1/images/generations` | sync |
| text-to-video | `agnes-video-v2.0` | `POST /v1/videos` → `GET /agnesapi?video_id=` | async |
| image-to-video | `agnes-video-v2.0` | `POST /v1/videos` → `GET /agnesapi?video_id=` | async |
| multi-image video | `agnes-video-v2.0` | `POST /v1/videos` → `GET /agnesapi?video_id=` | async |
| keyframe animation | `agnes-video-v2.0` | `POST /v1/videos` → `GET /agnesapi?video_id=` | async |

## Image Generation

**Tool**: `agnes_image` in OpenMontage (`tools/graphics/agnes_image.py`)

### Key Rules

1. `response_format` MUST go in `extra_body`, NOT top-level
2. Image-to-image: put input images in `extra_body.image` array, do NOT pass `tags: ["img2img"]`
3. Supports both public URL and Data URI Base64 input
4. `data[0].url` for URL output, `data[0].b64_json` for base64 output
5. Recommended timeout: 60-360s

### Prompt Structure

```
[Subject] + [Scene/Environment] + [Style] + [Lighting] + [Composition] + [Quality]
```

Example: "a futuristic city market with flying vehicles, holographic signs, neon lights, cinematic realism, ultra-detailed, high-density composition"

For img2img: "[what to change] + [new style/scene] + [elements to add/remove] + [elements to preserve]"

## Video Generation

**Tool**: `agnes_video` in OpenMontage (`tools/video/agnes_video.py`)

### Key Rules

1. **Async API**: POST to create task → poll `GET /agnesapi?video_id=<ID>` every 5s
2. **8n+1 frames**: `num_frames` must be 25, 33, 41, 49, 57, 65, 73, 81, 89, 97, 105, 113, 121, ..., 441
3. **Modes**: `txt2vid` (default), `img2vid` (single image), `multi-img` (extra_body.image array), `keyframes` (extra_body.mode: "keyframes")
4. **Size mapping**: submitted dimensions are auto-mapped to nearest preset (480p/720p/1080p × 16:9/9:16/1:1/4:3/3:4). Check response `size` field for actual output.
5. **Duration**: `seconds = num_frames / frame_rate`

### Prompt Structure (txt2vid)

```
[Subject] + [Action] + [Scene] + [Camera Movement] + [Lighting] + [Style]
```

Example: "a young astronaut walking across a red desert planet, dust blowing in the wind, slow cinematic tracking shot, dramatic sunset lighting, realistic sci-fi style"

### Prompt Structure (img2vid)

Describe what should MOVE, what should stay STABLE:
```
[animate X] + [motion type] + [while keeping Y stable]
```

Example: "the character's hair moves gently in the wind, background lights flicker softly, camera slowly zooms in, while keeping the face and outfit consistent"

**IMPORTANT for img2vid**: Do NOT stack style descriptors (makoto shinkai, kyoto animation, etc.) in the prompt — the reference image already locks the style. Only describe motion and camera.

### Content Policy

These trigger 400 content_policy_violation:
- Skin: `porcelain skin`, `flawless skin`, `smooth skin`, `perfect skin`
- Lips: `glossy lips`, `soft lips`, `full lips`, `plump lips`
- Tears + emotion: `tears of happiness`, `tears streaming`, `crying with joy`
- Body: `slim graceful figure`, `curvy figure`, `perfect body`

These are safe:
- `beautiful anime girl`, `handsome anime boy`
- `bright expressive eyes`, `warm bright smile`
- `long chestnut hair with soft highlights`
- `wearing cream coat`, `stylish urban outfit`
- `elegant feminine features`, `chiseled face`

### Known API Quirks

1. **`error` field is null on success, not absent**: Always check `result.get("error")` truthy, NOT `"error" in result`
2. **Middle states use `internal_status`, not `status`**: Polling must read `result.get("status") or result.get("internal_status")`
3. **Video URL**: v2.0 puts it in `url` field; old docs say `remixed_from_video_id`. Check both.
4. **400 vs 500**: 400 is content policy (fix prompt), 500 is provider transient (retry or change payload)

## Tool Selection

- Need a still image? → `agnes_image`
- Need a video clip? → `agnes_video`
- Need anime/cinematic style locked to reference? → `agnes_video` with `mode: "img2vid"` + `image_path`
- Need smooth transition between keyframes? → `agnes_video` with `mode: "keyframes"` + `image_urls`