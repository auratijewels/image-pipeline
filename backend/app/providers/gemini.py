"""Google AI Studio provider — Gemini 2.5 Flash Image ("Nano Banana").

The only live provider in v1 (§11).
"""

from __future__ import annotations

import logging

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config.settings import get_settings
from app.core.costs import GEMINI_IMAGE_USD
from app.providers.base import (
    GenerationRequest,
    GenerationResult,
    ImageProvider,
    ProviderError,
    ReferenceImage,
)

log = logging.getLogger(__name__)

# Aspect ratios Gemini accepts natively. Anything else is generated at the
# nearest supported ratio and smart-cropped downstream by the format exporter.
SUPPORTED_RATIOS = {"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}


class GeminiImageProvider(ImageProvider):
    name = "gemini"

    def __init__(self) -> None:
        s = get_settings()
        if not s.google_api_key:
            raise ProviderError(
                self.name,
                "init",
                "GOOGLE_API_KEY is empty. Add it to .env, or set IMAGE_PROVIDER=dryrun.",
            )
        # Imported lazily so `dryrun` mode works without the SDK installed.
        from google import genai

        self._genai = genai
        self._client = genai.Client(api_key=s.google_api_key)
        self._model = s.gemini_image_model

    @property
    def model(self) -> str:
        return self._model

    def estimate_usd(self, req: GenerationRequest) -> float:
        return GEMINI_IMAGE_USD

    # --- public API ---------------------------------------------------------

    async def generate(self, req: GenerationRequest) -> GenerationResult:
        return await self._call(req, req.references, operation="generate")

    async def edit(self, req: GenerationRequest, image: ReferenceImage) -> GenerationResult:
        # The image being edited must lead, so the model treats the rest as context.
        return await self._call(req, [image, *req.references], operation="edit")

    # --- internals ----------------------------------------------------------

    def _config(self, req: GenerationRequest):
        from google.genai import types

        ratio = req.aspect_ratio if req.aspect_ratio in SUPPORTED_RATIOS else "1:1"
        if ratio != req.aspect_ratio:
            log.warning("Unsupported ratio %s; generating at %s", req.aspect_ratio, ratio)

        kwargs = {
            "response_modalities": ["IMAGE"],
            "image_config": types.ImageConfig(aspect_ratio=ratio),
        }
        if req.seed is not None:
            kwargs["seed"] = req.seed
        return types.GenerateContentConfig(**kwargs)

    def _contents(self, req: GenerationRequest, refs: list[ReferenceImage]) -> list:
        from google.genai import types

        prompt = req.prompt
        if req.negative_prompt:
            prompt = f"{prompt}\n\nAvoid: {req.negative_prompt}"
        parts: list = [
            types.Part.from_bytes(data=r.data, mime_type=r.mime_type) for r in refs
        ]
        parts.append(prompt)
        return parts

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        reraise=True,
    )
    async def _request(self, req: GenerationRequest, refs: list[ReferenceImage]):
        return await self._client.aio.models.generate_content(
            model=self._model,
            contents=self._contents(req, refs),
            config=self._config(req),
        )

    async def _call(
        self, req: GenerationRequest, refs: list[ReferenceImage], *, operation: str
    ) -> GenerationResult:
        try:
            resp = await self._request(req, refs)
        except Exception as exc:  # noqa: BLE001 — surfaced verbatim to the UI
            raise ProviderError(self.name, operation, str(exc)) from exc

        data, mime = self._extract_image(resp)
        if data is None:
            raise ProviderError(
                self.name,
                operation,
                f"No image in response (likely a safety block). Text: {self._extract_text(resp)!r}",
            )

        return GenerationResult(
            data=data,
            mime_type=mime,
            provider=self.name,
            model=self._model,
            usd=GEMINI_IMAGE_USD,
            prompt=req.prompt,
        )

    @staticmethod
    def _extract_image(resp) -> tuple[bytes | None, str]:
        for cand in getattr(resp, "candidates", None) or []:
            content = getattr(cand, "content", None)
            for part in getattr(content, "parts", None) or []:
                inline = getattr(part, "inline_data", None)
                if inline and getattr(inline, "data", None):
                    return inline.data, getattr(inline, "mime_type", None) or "image/png"
        return None, "image/png"

    @staticmethod
    def _extract_text(resp) -> str:
        chunks: list[str] = []
        for cand in getattr(resp, "candidates", None) or []:
            content = getattr(cand, "content", None)
            for part in getattr(content, "parts", None) or []:
                if getattr(part, "text", None):
                    chunks.append(part.text)
        return " ".join(chunks)[:500]
