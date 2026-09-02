"""Generation trigger, live progress stream, and result access."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.assets import ASSET_TYPES_BY_KEY
from app.core.jobs import Job, JobStatus, get_registry
from app.core.store import ProductNotFound, get_store
from app.pipeline.orchestrator import default_asset_keys, output_path, run_job

log = logging.getLogger(__name__)

router = APIRouter(tags=["generate"])


class GenerateRequest(BaseModel):
    #: Subset of asset keys to build. Empty means all seven — used by
    #: "regenerate this one" in the results view.
    asset_keys: list[str] = Field(default_factory=list)


def _product(product_id: str):
    try:
        return get_store().get(product_id)
    except ProductNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


def _job(job_id: str) -> Job:
    job = get_registry().get(job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No job {job_id}.")
    return job


@router.post("/products/{product_id}/generate", status_code=status.HTTP_202_ACCEPTED)
async def start_generation(product_id: str, payload: GenerateRequest | None = None) -> dict:
    product = _product(product_id)
    registry = get_registry()

    if existing := registry.active_for_product(product_id):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Generation already running for this product (job {existing.id}).",
        )

    if product.blockers:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            {"message": "Product is not ready to generate.", "blockers": product.blockers},
        )

    keys = (payload.asset_keys if payload else None) or default_asset_keys()
    unknown = [k for k in keys if k not in ASSET_TYPES_BY_KEY]
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown asset key(s): {unknown}")

    job = registry.create(product_id, keys)
    # Progress is observed through the event stream, so the POST returns as soon
    # as the job is scheduled. The task reference is kept on the job: asyncio
    # holds only weak references, and an unreferenced task can be collected
    # mid-run, stalling the job with no error anywhere.
    job.task = asyncio.create_task(run_job(job, product))
    return {"job_id": job.id, "asset_keys": keys}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    return _job(job_id).dump()


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    job = _job(job_id)
    if job.status in (JobStatus.COMPLETE, JobStatus.FAILED, JobStatus.CANCELLED):
        return {"status": job.status.value, "message": "Job already finished."}
    job.cancel()
    return {"status": "cancelling"}


@router.get("/jobs/{job_id}/events")
async def stream_events(job_id: str) -> StreamingResponse:
    """Server-sent events for the processing view.

    Subscribing replays the job's history first, so a client that connects late
    or reconnects sees the whole log rather than a blank panel.
    """
    job = _job(job_id)

    async def gen():
        queue = job.subscribe()
        try:
            while True:
                event = await queue.get()
                if event is None:  # sentinel: job finished
                    yield f"event: end\ndata: {json.dumps(job.dump())}\n\n"
                    return
                yield f"data: {json.dumps(event.dump())}\n\n"
        except asyncio.CancelledError:
            raise
        finally:
            job.unsubscribe(queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/products/{product_id}/assets/{asset_key}/raw")
def get_asset_image(product_id: str, asset_key: str) -> FileResponse:
    _product(product_id)
    if asset_key not in ASSET_TYPES_BY_KEY:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown asset {asset_key!r}.")
    path = output_path(product_id, asset_key)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{asset_key} has not been generated yet.")
    return FileResponse(path, media_type="image/png")


@router.get("/products/{product_id}/assets")
def list_assets(product_id: str) -> dict:
    _product(product_id)
    return {
        key: output_path(product_id, key).exists() for key in ASSET_TYPES_BY_KEY
    }
