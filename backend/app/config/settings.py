"""Central configuration. Everything tunable lives here or in .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- providers ---
    google_api_key: str = ""
    gemini_image_model: str = "gemini-2.5-flash-image"
    image_provider: str = "gemini"  # "gemini" | "dryrun"

    # --- budget guardrail (§11) ---
    budget_cap_inr_per_product: float = 100.0
    usd_to_inr: float = 88.0

    # --- background removal ---
    rembg_model: str = "birefnet-general"

    # --- server ---
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    frontend_port: int = 5173

    # --- storage ---
    data_dir: Path = REPO_ROOT / "data"
    output_dir: Path = REPO_ROOT / "outputs"

    # --- campaign consistency (§6) ---
    campaign_seed: int = 20260101
    campaign_style: str = (
        "editorial fine-jewellery campaign, soft directional daylight, "
        "shallow depth of field, muted navy and platinum grade, no harsh specular clipping"
    )

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def cutouts_dir(self) -> Path:
        return self.data_dir / "cutouts"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.output_dir, self.uploads_dir, self.cutouts_dir):
            d.mkdir(parents=True, exist_ok=True)

    @property
    def is_dry_run(self) -> bool:
        return self.image_provider.lower() == "dryrun"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
