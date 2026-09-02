"""Generation orchestrator — runs a product through all seven asset types.

Two routes through here, decided by the asset registry:

- DIRECT assets go cut-out -> Gemini -> output. The model may compose freely
  because no human body is involved and there is nothing to scale against.
- COMPOSITE assets run the hybrid pipeline of §4: generate the scene *without*
  the jewellery, measure it, then scale and place the real cut-out. The model
  never sees the product until after it has been placed.

Every vendor call is preceded by a budget check, never followed by one — the cap
is a stop, not a report.
"""

from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from app.config import prompts as P
from app.config.anatomy import MountPoint, mount_for_category
from app.config.settings import get_settings
from app.core.assets import ASSET_TYPES, ASSET_TYPES_BY_KEY, AssetType, Pipeline
from app.core.costs import BudgetExceeded, CostEntry, get_ledger, usd_to_inr
from app.core.jobs import AssetResult, Job, JobCancelled, JobStatus, Level
from app.models.product import Product
from app.pipeline import landmarks as L
from app.pipeline.composite import composite
from app.pipeline.cutout import CutoutError, cutout_async, cutout_path
from app.providers.base import GenerationRequest, ProviderError, ReferenceImage
from app.providers.registry import get_image_provider

log = logging.getLogger(__name__)

#: How far the harmonization pass may move the product region before we treat it
#: as having redesigned the piece (§4E). SSIM over the product's bounding box.
HARMONIZE_SSIM_FLOOR = 0.92

MOUNT_AREA_PHRASE = {
    MountPoint.EARLOBE: "earlobe",
    MountPoint.NECK: "base of the neck and collarbone",
    MountPoint.RING_FINGER: "ring finger",
    MountPoint.WRIST: "wrist",
    MountPoint.ANKLE: "ankle",
}

VIEW_PHRASE = {
    MountPoint.EARLOBE: "head turned to a three-quarter profile so one ear is fully visible",
    MountPoint.NECK: "facing camera, chin slightly raised, shoulders bare",
    MountPoint.RING_FINGER: "one hand raised and relaxed, fingers slightly apart",
    MountPoint.WRIST: "one forearm resting across the frame, wrist facing camera",
    MountPoint.ANKLE: "seated, one ankle visible and unobstructed",
}


class GenerationError(RuntimeError):
    pass


@dataclass
class AssetOutcome:
    result: AssetResult
    image: Image.Image | None = None


def output_path(product_id: str, asset_key: str) -> Path:
    d = get_settings().output_dir / product_id
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{asset_key}.png"


def dry_run_active() -> bool:
    """Whether placeholders are in play — decided by the provider, not settings.

    The registry falls back to the dry-run provider when GOOGLE_API_KEY is
    missing, while `settings.image_provider` still reads "gemini". Trusting
    settings here would feed placeholder images into real landmark detection and
    fail with "no face detected", which is a baffling error for a user whose
    actual problem is a missing key.
    """
    return get_image_provider().name == "dryrun"


# --- prompts ----------------------------------------------------------------


def render_prompt(asset: AssetType, product: Product) -> str:
    """Fill a template with everything any of them might reference.

    All templates get the full parameter set rather than a per-template subset:
    a missing key raises at render time, which would surface as a failed asset
    halfway through a paid run.
    """
    mount = mount_for_category(product.category)
    template = P.get_prompt(asset.prompt_key)
    return template.render(
        name=product.name,
        desc=product.description or "",
        dimensions=product.dimensions_phrase(),
        category=product.category.value,
        view=VIEW_PHRASE[mount],
        mount_area=MOUNT_AREA_PHRASE[mount],
        concept=product.concept or P.DEFAULT_CONCEPT,
    )


def pick_cutout(product: Product, asset: AssetType) -> Path:
    """Choose the best available cut-out for an asset type."""
    for angle in (*asset.preferred_angles, "front", "left", "right", "back", "extra"):
        path = cutout_path(product.id, angle)
        if path.exists():
            return path
    raise GenerationError(
        f"No cut-out available for {asset.key}. Run background removal first."
    )


# --- vendor calls -----------------------------------------------------------


async def _generate(job: Job, product: Product, req: GenerationRequest, asset_key: str) -> tuple[Image.Image, float]:
    provider = get_image_provider()
    ledger = get_ledger()
    estimate = provider.estimate_usd(req)

    # Check before spending, never after.
    ledger.check_budget(product.id, estimate)
    job.raise_if_cancelled()

    result = await provider.generate(req)
    ledger.record(
        CostEntry(
            product_id=product.id,
            asset_key=asset_key,
            provider=result.provider,
            model=result.model,
            operation="generate",
            usd=result.usd,
            inr=usd_to_inr(result.usd),
            dry_run=result.dry_run,
        )
    )
    if not result.dry_run:
        job.spend_inr += usd_to_inr(result.usd)
    return Image.open(io.BytesIO(result.data)).convert("RGBA"), result.usd


# --- asset routes -----------------------------------------------------------


async def _run_direct(job: Job, product: Product, asset: AssetType) -> AssetOutcome:
    cut = pick_cutout(product, asset)
    job.emit(asset.key, f"Generating from {cut.stem} cut-out", asset_key=asset.key)

    req = GenerationRequest(
        prompt=render_prompt(asset, product),
        aspect_ratio=asset.native_ratio,
        references=[ReferenceImage(cut.read_bytes(), "image/png", "product")],
        seed=get_settings().campaign_seed,
        negative_prompt=P.get_prompt(asset.prompt_key).negative,
    )
    image, usd = await _generate(job, product, req, asset.key)

    path = output_path(product.id, asset.key)
    image.save(path)
    return AssetOutcome(
        AssetResult(asset.key, asset.label, "ok", str(path), usd=usd), image
    )


async def _run_composite(job: Job, product: Product, asset: AssetType) -> AssetOutcome:
    settings = get_settings()
    mount = mount_for_category(product.category)
    cut = pick_cutout(product, asset)

    # Step B — the scene only. The product is deliberately absent.
    job.emit(asset.key, "Generating scene without jewellery", asset_key=asset.key)
    req = GenerationRequest(
        prompt=render_prompt(asset, product),
        aspect_ratio=asset.native_ratio,
        seed=settings.campaign_seed,
        negative_prompt=P.get_prompt(asset.prompt_key).negative,
    )
    scene, usd = await _generate(job, product, req, asset.key)

    # Step C — measure it.
    if dry_run_active():
        reading = L.synthetic_reading(scene.size, mount)
        job.emit(asset.key, "Dry run: using a pinned calibration (no real face)",
                 Level.WARN, asset.key)
    else:
        reading = await asyncio.to_thread(L.read, np.array(scene.convert("RGB")), mount)
        job.emit(
            asset.key,
            f"{reading.primary.span.label}: {reading.primary.pixels:.0f}px "
            f"-> {reading.px_per_mm:.3f} px/mm",
            asset_key=asset.key,
        )
        if reading.agreement_pct is not None:
            job.emit(asset.key, f"Cross-check agrees within {reading.agreement_pct:+.1f}%",
                     asset_key=asset.key)

    job.raise_if_cancelled()

    # Steps D–E — place the real product and verify it measures right.
    result = await asyncio.to_thread(
        composite, scene, cut, reading, product.category.value, product.dimensions_mm
    )
    job.emit(asset.key, result.plan.describe(), asset_key=asset.key)
    job.emit(
        asset.key,
        result.check.describe(),
        Level.INFO if result.passed else Level.WARN,
        asset.key,
    )

    path = output_path(product.id, asset.key)
    result.image.save(path)
    return AssetOutcome(
        AssetResult(
            asset.key,
            asset.label,
            "ok" if result.passed else "failed",
            str(path),
            None if result.passed else f"Scale check failed: {result.check.describe()}",
            scale_check=result.check.__dict__ | {"passed": result.passed},
            px_per_mm=round(reading.px_per_mm, 4),
            usd=usd,
        ),
        result.image,
    )


# --- entry point ------------------------------------------------------------


async def run_job(job: Job, product: Product) -> Job:
    """Execute a generation job. Never raises — failures land in the job."""
    job.status = JobStatus.RUNNING
    job.emit(
        "start",
        f"{product.code} — {len(job.asset_keys)} assets, "
        f"{'dry run (no spend)' if dry_run_active() else get_image_provider().model}",
    )

    try:
        await _ensure_cutouts(job, product)

        for key in job.asset_keys:
            job.raise_if_cancelled()
            asset = ASSET_TYPES_BY_KEY[key]
            try:
                outcome = (
                    await _run_composite(job, product, asset)
                    if asset.pipeline is Pipeline.COMPOSITE
                    else await _run_direct(job, product, asset)
                )
                job.assets[key] = outcome.result
                job.emit(key, f"{asset.label} ready", Level.DONE, key)

            except BudgetExceeded as exc:
                # Stop the whole run: every remaining asset would hit the same wall.
                job.assets[key] = AssetResult(key, asset.label, "skipped", error=str(exc))
                job.emit(key, str(exc), Level.ERROR, key)
                job.finish(JobStatus.FAILED, str(exc))
                return job

            except (ProviderError, GenerationError, CutoutError, L.LandmarkError, Exception) as exc:
                if isinstance(exc, JobCancelled):
                    raise
                # One bad asset should not cost the user the other six.
                log.exception("Asset %s failed", key)
                job.assets[key] = AssetResult(key, asset.label, "failed", error=str(exc))
                job.emit(key, f"{asset.label} failed: {exc}", Level.ERROR, key)

        ok = sum(1 for a in job.assets.values() if a.status == "ok")
        job.finish(
            JobStatus.COMPLETE if ok else JobStatus.FAILED,
            None if ok else "Every asset failed.",
        )

    except JobCancelled:
        job.finish(JobStatus.CANCELLED, "Cancelled.")
    except Exception as exc:  # noqa: BLE001 — a crash here must not lose the job
        log.exception("Job %s crashed", job.id)
        job.finish(JobStatus.FAILED, str(exc))

    return job


async def _ensure_cutouts(job: Job, product: Product) -> None:
    job.emit("cutout", f"Removing background from {len(product.angles)} angle(s)")
    built = 0
    for angle, uploaded in product.angles.items():
        job.raise_if_cancelled()
        try:
            res = await cutout_async(uploaded.stored_path, product.id, angle.value)
            built += 1
            if not res.looks_plausible:
                job.emit(
                    "cutout",
                    f"{angle.value}: kept {res.coverage:.1%} of the frame — check the source",
                    Level.WARN,
                )
        except CutoutError as exc:
            job.emit("cutout", f"{angle.value}: {exc}", Level.WARN)
    if not built:
        raise GenerationError("No angle could be cut out — cannot generate anything.")
    job.emit("cutout", f"{built} cut-out(s) ready", Level.DONE)


def default_asset_keys() -> list[str]:
    return [a.key for a in ASSET_TYPES]
