"""Provider interface.

Deliberately narrow: generate an image from text (+ optional reference images),
or edit an existing image. Everything Aurati Studio needs from an AI vendor goes
through these two calls, so swapping Gemini for fal.ai — or adding a video
provider in v2 — means writing one class, not touching the pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ReferenceImage:
    """An image handed to the model as context (product cut-out, scene, etc.)."""

    data: bytes
    mime_type: str = "image/png"
    role: str = "reference"


@dataclass
class GenerationRequest:
    prompt: str
    aspect_ratio: str = "1:1"
    references: list[ReferenceImage] = field(default_factory=list)
    seed: int | None = None
    # For edit/harmonize passes: how far the model may move from the input.
    # The composite pipeline (§4E) keeps this low so the product cannot drift.
    strength: float = 0.25
    negative_prompt: str | None = None


@dataclass
class GenerationResult:
    data: bytes
    mime_type: str
    provider: str
    model: str
    usd: float
    prompt: str
    dry_run: bool = False


class ImageProvider(ABC):
    """Contract every image backend implements."""

    name: str = "base"

    @property
    @abstractmethod
    def model(self) -> str: ...

    @abstractmethod
    async def generate(self, req: GenerationRequest) -> GenerationResult:
        """Text (+ references) -> new image."""

    @abstractmethod
    async def edit(self, req: GenerationRequest, image: ReferenceImage) -> GenerationResult:
        """Existing image + instruction -> modified image."""

    @abstractmethod
    def estimate_usd(self, req: GenerationRequest) -> float:
        """Cost of running `req`, checked against the cap *before* the call."""


class ProviderError(RuntimeError):
    """Vendor call failed after retries. Carries enough context to surface in UI."""

    def __init__(self, provider: str, operation: str, detail: str):
        self.provider = provider
        self.operation = operation
        self.detail = detail
        super().__init__(f"[{provider}] {operation} failed: {detail}")
