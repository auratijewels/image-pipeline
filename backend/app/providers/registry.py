"""Provider selection and graceful fallback."""

from __future__ import annotations

import logging

from app.config.settings import get_settings
from app.providers.base import ImageProvider, ProviderError
from app.providers.dryrun import DryRunProvider

log = logging.getLogger(__name__)

_PROVIDERS: dict[str, type[ImageProvider]] = {"dryrun": DryRunProvider}


def _register_gemini() -> None:
    from app.providers.gemini import GeminiImageProvider

    _PROVIDERS["gemini"] = GeminiImageProvider


_register_gemini()

_instance: ImageProvider | None = None


def get_image_provider(force: str | None = None) -> ImageProvider:
    """Return the configured provider, falling back to dry-run if it can't init.

    Falling back rather than crashing keeps the app usable with no API key —
    you can still explore the UI and the format pipeline.
    """
    global _instance
    name = (force or get_settings().image_provider).lower()
    if _instance is not None and force is None and _instance.name == name:
        return _instance

    cls = _PROVIDERS.get(name)
    if cls is None:
        raise ProviderError("registry", "select", f"Unknown provider {name!r}. Known: {sorted(_PROVIDERS)}")

    try:
        provider = cls()
    except ProviderError as exc:
        log.warning("Provider %s unavailable (%s) — falling back to dry-run.", name, exc.detail)
        provider = DryRunProvider()

    if force is None:
        _instance = provider
    return provider


def reset_provider_cache() -> None:
    """Called after settings change at runtime."""
    global _instance
    _instance = None
