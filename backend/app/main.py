"""Aurati Studio — FastAPI entrypoint."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_meta, routes_products
from app.config.settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)

settings = get_settings()

app = FastAPI(
    title="Aurati Studio",
    version="0.1.0",
    description="AI product-photography pipeline for Aurati Jewels.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        f"http://localhost:{settings.frontend_port}",
        f"http://127.0.0.1:{settings.frontend_port}",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_meta.router, prefix="/api")
app.include_router(routes_products.router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    from app.providers.registry import get_image_provider

    provider = get_image_provider()
    return {
        "status": "ok",
        "provider": provider.name,
        "model": provider.model,
        "dry_run": provider.name == "dryrun",
        "budget_cap_inr": settings.budget_cap_inr_per_product,
    }
