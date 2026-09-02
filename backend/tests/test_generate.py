"""Orchestration, budget enforcement and the progress stream.

Runs entirely in dry-run mode, which is what dry-run exists for: the whole
pipeline including the §10 scale check executes at zero API cost.
"""

from __future__ import annotations

import json

import pytest

from app.core.assets import ASSET_TYPES, SCALE_CRITICAL
from app.core.jobs import JobStatus
from tests.conftest import make_image

EARRING = {
    "code": "G100",
    "name": "Cascade Drop Earrings",
    "category": "earrings",
    "description": "Waterproof gold-tone with a freshwater pearl.",
    "dimensions_mm": {"drop": 36, "width": 12},
}


@pytest.fixture
def ready_product(client, stub_rembg):
    pid = client.post("/api/products", json=EARRING).json()["id"]
    for angle in ("front", "left"):
        client.put(
            f"/api/products/{pid}/angles/{angle}",
            files={"file": (f"{angle}.jpg", make_image(900, 900), "image/jpeg")},
        )
    return pid


def run_to_completion(client, pid, asset_keys=None) -> dict:
    """Start a job and drain its event stream, which ends when the job does."""
    started = client.post(
        f"/api/products/{pid}/generate", json={"asset_keys": asset_keys or []}
    )
    assert started.status_code == 202, started.text
    job_id = started.json()["job_id"]

    with client.stream("GET", f"/api/jobs/{job_id}/events") as stream:
        for line in stream.iter_lines():
            if line.startswith("data: ") and '"status"' in line:
                payload = json.loads(line[6:])
                if payload.get("id") == job_id:
                    return payload
    return client.get(f"/api/jobs/{job_id}").json()


# --- happy path -------------------------------------------------------------


def test_all_seven_assets_generate(client, ready_product):
    job = run_to_completion(client, ready_product)

    assert job["status"] == JobStatus.COMPLETE.value, job["error"]
    assert len(job["assets"]) == 7
    assert all(a["status"] == "ok" for a in job["assets"].values()), {
        k: v["error"] for k, v in job["assets"].items() if v["status"] != "ok"
    }

    listed = client.get(f"/api/products/{ready_product}/assets").json()
    assert all(listed.values())


def test_generated_assets_are_downloadable(client, ready_product):
    run_to_completion(client, ready_product)
    for asset in ASSET_TYPES:
        res = client.get(f"/api/products/{ready_product}/assets/{asset.key}/raw")
        assert res.status_code == 200, asset.key
        assert res.headers["content-type"] == "image/png"


def test_scale_critical_assets_report_a_scale_check(client, ready_product):
    """The §10 criterion must be recorded per asset, not just logged."""
    job = run_to_completion(client, ready_product)

    for key in SCALE_CRITICAL:
        check = job["assets"][key]["scale_check"]
        assert check is not None, key
        assert check["passed"] is True, check
        assert check["expected_mm"] == pytest.approx(36.0)
        assert abs(check["error_pct"]) <= 8.0
        assert job["assets"][key]["px_per_mm"] > 0


def test_direct_assets_have_no_scale_check(client, ready_product):
    """Nothing to scale against without a body in frame — a check here would
    be meaningless rather than reassuring."""
    job = run_to_completion(client, ready_product)
    assert job["assets"]["white_hero"]["scale_check"] is None


def test_generating_a_subset_only_builds_that_subset(client, ready_product):
    job = run_to_completion(client, ready_product, ["white_hero"])
    assert list(job["assets"]) == ["white_hero"]


# --- progress ---------------------------------------------------------------


def test_the_event_log_narrates_the_pipeline(client, ready_product):
    job = run_to_completion(client, ready_product)
    steps = {e["step"] for e in job["events"]}
    assert "cutout" in steps
    assert "on_model" in steps

    text = " ".join(e["message"] for e in job["events"])
    assert "px/mm" in text          # calibration reported
    assert "mm" in text             # scale check reported


def test_subscribing_to_a_finished_job_replays_and_then_ends(client, ready_product):
    """Reconnecting after a job is over must replay the log and close.

    Regression guard: the sentinel that ends the stream is broadcast once, when
    the job finishes. A subscriber created afterwards never saw it and hung.
    """
    job = run_to_completion(client, ready_product)
    replayed = client.get(f"/api/jobs/{job['id']}/events")
    assert replayed.status_code == 200
    assert "cutout" in replayed.text
    assert "event: end" in replayed.text


# --- budget -----------------------------------------------------------------


def test_hitting_the_cap_stops_the_whole_run(client, ready_product, monkeypatch):
    """Once the cap is reached every remaining asset would hit the same wall,
    so the run stops rather than failing seven times over."""
    from app.core import costs

    ledger = costs.get_ledger()
    monkeypatch.setattr(
        ledger,
        "check_budget",
        lambda pid, usd: (_ for _ in ()).throw(costs.BudgetExceeded(pid, 98.0, 100.0, 3.4)),
    )

    job = run_to_completion(client, ready_product)

    assert job["status"] == JobStatus.FAILED.value
    assert "cap" in (job["error"] or "").lower()
    # First asset is marked skipped; the rest are never attempted at all.
    assert any(a["status"] == "skipped" for a in job["assets"].values())
    assert len(job["assets"]) < 7, "run continued past the cap"


def test_the_budget_is_checked_before_every_call(client, ready_product, monkeypatch):
    """A cap checked after the call has already spent the money."""
    from app.core import costs

    order: list[str] = []
    ledger = costs.get_ledger()
    real_check, real_record = ledger.check_budget, ledger.record

    monkeypatch.setattr(ledger, "check_budget", lambda pid, usd: (order.append("check"), real_check(pid, usd))[1])
    monkeypatch.setattr(ledger, "record", lambda entry: (order.append("spend"), real_record(entry))[1])

    run_to_completion(client, ready_product, ["white_hero"])

    assert order[:2] == ["check", "spend"], order


def test_dry_run_records_zero_spend(client, ready_product):
    job = run_to_completion(client, ready_product)
    assert job["spend_inr"] == 0.0


# --- guard rails ------------------------------------------------------------


def test_a_product_with_blockers_cannot_generate(client, stub_rembg):
    pid = client.post("/api/products", json={**EARRING, "code": "G101"}).json()["id"]
    res = client.post(f"/api/products/{pid}/generate", json={})
    assert res.status_code == 400
    assert "Missing required angle" in res.text


def test_unknown_asset_keys_are_rejected(client, ready_product):
    res = client.post(
        f"/api/products/{ready_product}/generate", json={"asset_keys": ["nope"]}
    )
    assert res.status_code == 400
    assert "nope" in res.text


def test_generating_a_missing_product_is_404(client):
    assert client.post("/api/products/ghost/generate", json={}).status_code == 404


def test_cancelling_a_finished_job_is_harmless(client, ready_product):
    job = run_to_completion(client, ready_product)
    res = client.post(f"/api/jobs/{job['id']}/cancel")
    assert res.status_code == 200
    assert "already finished" in res.json()["message"]


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/deadbeef").status_code == 404
