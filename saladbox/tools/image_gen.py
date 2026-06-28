"""Image generation tool using mflux (MLX FLUX) with Draw Things fallback."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import random
import tempfile
import time

import aiohttp

from saladbox.tools.base import BaseTool

logger = logging.getLogger(__name__)

GENERATED_IMAGE_DIR = os.path.join(tempfile.gettempdir(), "saladbox_generated_images")
GENERATED_IMAGE_MARKER = "GENERATED_IMAGE:"

# Singleton mflux model instance (lazy loaded, ~6GB RAM at 4-bit)
_flux_model = None
_flux_lock = asyncio.Lock()
_flux_model_name: str = "schnell"
_flux_quantize: int = 4


def _load_mflux_model(model_name: str = "schnell", quantize: int = 4):
    """Load mflux model lazily. Returns model instance or None.

    Args:
        model_name: "schnell" or "dev"
        quantize: 4 or 8 bit quantization
    """
    global _flux_model, _flux_model_name, _flux_quantize

    # If model is already loaded with same config, reuse it
    if (
        _flux_model is not None
        and _flux_model_name == model_name
        and _flux_quantize == quantize
    ):
        return _flux_model

    # If config changed, force reload
    if _flux_model is not None:
        logger.info(
            f"[IMAGE_GEN] Model config changed "
            f"({_flux_model_name}/{_flux_quantize} → {model_name}/{quantize}), "
            f"reloading..."
        )
        _flux_model = None

    try:
        from mflux.models.common.config.model_config import ModelConfig
        from mflux.models.flux.variants.txt2img.flux import Flux1

        logger.info(
            f"[IMAGE_GEN] Loading FLUX.1-{model_name} model "
            f"({quantize}-bit quantized)..."
        )
        _flux_model = Flux1(
            model_config=ModelConfig.from_name(
                model_name=model_name, base_model=None
            ),
            quantize=quantize,
        )
        _flux_model_name = model_name
        _flux_quantize = quantize
        logger.info("[IMAGE_GEN] FLUX model loaded successfully")
        return _flux_model
    except Exception as e:
        logger.error(f"[IMAGE_GEN] Failed to load mflux model: {e}")
        return None


class ImageGenTool(BaseTool):
    """Generate images from text prompts using local AI models."""

    max_output_chars = 500  # Small output — just the marker + status

    # Class-level config — set by app.py after loading config
    _config_backend: str = "mflux"
    _config_model: str = "schnell"
    _config_quantize: int = 4
    _config_width: int = 1024
    _config_height: int = 1024
    _config_steps: int = 2
    _config_drawthings_url: str = "http://localhost:7860"

    @classmethod
    def configure(cls, image_gen_config) -> None:
        """Apply settings from ImageGenConfig dataclass."""
        cls._config_backend = image_gen_config.backend
        cls._config_model = image_gen_config.model
        cls._config_quantize = image_gen_config.quantize
        cls._config_width = image_gen_config.default_width
        cls._config_height = image_gen_config.default_height
        cls._config_steps = image_gen_config.default_steps
        cls._config_drawthings_url = image_gen_config.drawthings_url

    @property
    def name(self) -> str:
        return "image_gen"

    @property
    def description(self) -> str:
        return (
            "Generate images from text descriptions using local AI models. "
            "Uses FLUX.1-schnell (fast, 2-4 steps) via MLX as primary backend, "
            "with Draw Things app as fallback. Returns the generated image."
        )

    @property
    def compact_description(self) -> str:
        return "Generate images from text prompts locally using FLUX or Draw Things."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Detailed description of the image to generate",
                },
                "width": {
                    "type": "integer",
                    "description": "Image width in pixels (must be multiple of 16, default 1024)",
                },
                "height": {
                    "type": "integer",
                    "description": "Image height in pixels (must be multiple of 16, default 1024)",
                },
                "steps": {
                    "type": "integer",
                    "description": "Number of inference steps (2-4 for schnell, default 2)",
                },
                "seed": {
                    "type": "integer",
                    "description": "Random seed for reproducibility (optional)",
                },
                "backend": {
                    "type": "string",
                    "enum": ["mflux", "drawthings"],
                    "description": "Backend to use: mflux (default) or drawthings",
                },
            },
            "required": ["prompt"],
        }

    async def execute(
        self,
        prompt: str = "",
        width: int = 0,
        height: int = 0,
        steps: int = 0,
        seed: int | None = None,
        backend: str = "",
    ) -> str:
        if not prompt:
            return "Error: prompt is required."

        # Apply config defaults when args not explicitly provided
        width = width or self._config_width
        height = height or self._config_height
        steps = steps or self._config_steps
        backend = backend or self._config_backend

        # Ensure dimensions are multiples of 16
        width = max(256, (width // 16) * 16)
        height = max(256, (height // 16) * 16)
        steps = max(1, min(steps, 50))

        if seed is None:
            seed = random.randint(0, 2**32 - 1)

        os.makedirs(GENERATED_IMAGE_DIR, exist_ok=True)
        self._cleanup_old_images()

        timestamp = int(time.time())
        filename = f"gen_{timestamp}_{seed}.png"
        save_path = os.path.join(GENERATED_IMAGE_DIR, filename)

        # Try primary backend first, fallback to other
        if backend == "drawthings":
            result = await self._generate_drawthings(
                prompt, width, height, steps, seed, save_path
            )
            if result is None:
                result = await self._generate_mflux(
                    prompt, width, height, steps, seed, save_path
                )
        else:
            result = await self._generate_mflux(
                prompt, width, height, steps, seed, save_path
            )
            if result is None:
                result = await self._generate_drawthings(
                    prompt, width, height, steps, seed, save_path
                )

        if result is None:
            return (
                "Error: Image generation failed. "
                "Neither mflux nor Draw Things backend is available. "
                "Make sure mflux is installed (pip install mflux) or "
                "Draw Things is running with HTTP API enabled on port 7860."
            )

        file_size = os.path.getsize(save_path)
        return (
            f"{GENERATED_IMAGE_MARKER}{filename}\n"
            f"Image generated successfully ({width}x{height}, {file_size:,} bytes, "
            f"seed={seed}, backend={result})."
        )

    async def _generate_mflux(
        self,
        prompt: str,
        width: int,
        height: int,
        steps: int,
        seed: int,
        save_path: str,
    ) -> str | None:
        """Generate image using mflux (MLX FLUX). Returns backend name or None."""
        try:
            # Load model in thread pool (heavy operation)
            loop = asyncio.get_event_loop()
            model = await loop.run_in_executor(
                None, _load_mflux_model, self._config_model, self._config_quantize
            )
            if model is None:
                return None

            logger.info(
                f"[IMAGE_GEN] Generating with mflux: "
                f"{width}x{height}, steps={steps}, seed={seed}"
            )

            def _generate():
                image = model.generate_image(
                    seed=seed,
                    prompt=prompt,
                    num_inference_steps=steps,
                    height=height,
                    width=width,
                    guidance=4.0,
                )
                image.save(path=save_path)

            await loop.run_in_executor(None, _generate)
            logger.info(f"[IMAGE_GEN] mflux generation complete: {save_path}")
            return "mflux"

        except Exception as e:
            logger.error(f"[IMAGE_GEN] mflux generation failed: {e}")
            return None

    async def _generate_drawthings(
        self,
        prompt: str,
        width: int,
        height: int,
        steps: int,
        seed: int,
        save_path: str,
    ) -> str | None:
        """Generate image using Draw Things HTTP API. Returns backend name or None."""
        try:
            payload = {
                "prompt": prompt,
                "width": width,
                "height": height,
                "steps": steps,
                "seed": seed,
                "cfg_scale": 4.0,
                "sampler_name": "Euler",
            }

            async with aiohttp.ClientSession() as session, session.post(
                f"{self._config_drawthings_url}/sdapi/v1/txt2img",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300),
            ) as resp:
                if resp.status != 200:
                    logger.warning(
                        f"[IMAGE_GEN] Draw Things returned status {resp.status}"
                    )
                    return None

                data = await resp.json()
                images = data.get("images", [])
                if not images:
                    logger.warning("[IMAGE_GEN] Draw Things returned no images")
                    return None

                # Decode first image and save
                image_data = base64.b64decode(images[0])
                with open(save_path, "wb") as f:
                    f.write(image_data)

                logger.info(
                    f"[IMAGE_GEN] Draw Things generation complete: {save_path}"
                )
                return "drawthings"

        except Exception as e:
            logger.error(f"[IMAGE_GEN] Draw Things generation failed: {e}")
            return None

    def _cleanup_old_images(self) -> None:
        """Remove generated images older than 1 hour."""
        try:
            cutoff = time.time() - 3600
            for fname in os.listdir(GENERATED_IMAGE_DIR):
                fpath = os.path.join(GENERATED_IMAGE_DIR, fname)
                if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff:
                    os.remove(fpath)
        except OSError:
            pass
