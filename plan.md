# Image Generation Tool — Implementation Plan

## Overview
Add `image_gen` tool to Saladbox with **mflux** (FLUX.1-schnell via MLX) as primary backend and **Draw Things** HTTP API as fallback. Generated images are served via HTTP and displayed in Electron + Telegram.

## Files to Create/Modify

### 1. Install mflux
```bash
pip install mflux
```
Add `mflux>=0.9` to `pyproject.toml` dependencies.

### 2. NEW: `saladbox/tools/image_gen.py`
The image generation tool extending BaseTool.

**Parameters:**
- `prompt` (str, required) — image description
- `width` (int, default 1024) — image width
- `height` (int, default 1024) — image height
- `backend` (str, default "mflux") — "mflux" or "drawthings"
- `steps` (int, default 2) — inference steps (schnell=2-4, dev=20-25)
- `seed` (int, optional) — for reproducibility

**Flow:**
1. Load mflux model lazily on first call (singleton — ~6GB RAM at 4-bit)
2. Generate image to `/tmp/saladbox_generated_images/gen_TIMESTAMP.png`
3. Return `GENERATED_IMAGE:filename.png\nImage generated successfully.`
4. Falls back to Draw Things API at `localhost:7860` if mflux unavailable

**Draw Things fallback:**
- POST to `http://localhost:7860/sdapi/v1/txt2img`
- Decode base64 response, save to same directory

### 3. MODIFY: `saladbox/core/engine.py`
Add image gen detection in tool execution loop (same pattern as screen_capture):
- Detect `GENERATED_IMAGE:` marker in result
- Don't compress the result
- Build URL: `http://127.0.0.1:8765/generated/filename.png`
- Prepend `![Generated](url)` to final response
- NO vision model escalation (unlike screen_capture — the LLM already knows what it generated)

### 4. MODIFY: `saladbox/adapters/http.py`
Add route: `GET /generated/{filename}` serving from `/tmp/saladbox_generated_images/`
(same pattern as `/screenshots/{filename}`)

### 5. MODIFY: `saladbox/core/tool_filter.py`
Add to TOOL_KEYWORDS:
- primary: "generate image", "create image", "draw", "make a picture", "image of", etc.
- secondary: "illustration", "artwork", "photo of", "painting"
- weight: 2.5

Add to RECOGNITION_PATTERNS:
- `\b(generate|create|make|draw)\s+(an?\s+)?(image|picture|photo|illustration)\b`
- `\b(image|picture)\s+of\b`
- etc.

Add to DEFAULT_ARGS: `"image_gen": {"prompt": ""}`

### 6. MODIFY: `saladbox/core/tool_registry.py`
Add normalization for `image_gen` args.

### 7. MODIFY: `saladbox/tools/__init__.py`
Import and register `ImageGenTool`.

### 8. MODIFY: `config.yaml`
Add `image_gen: true` to tools section.

### 9. MODIFY: `saladbox/adapters/telegram.py`
Update `_send_long_message` to also detect `![Generated](url)` image markdown and send as Telegram photo (same pattern as screenshot handling, just different URL prefix).
