"""The budget guardrail (§11).

The cap has to fire *before* a call, and the ledger has to survive a crash —
if the running total resets on restart, the cap silently stops capping.
"""

from __future__ import annotations

import pytest

from app.config.settings import get_settings
from app.core.costs import (
    GEMINI_IMAGE_USD,
    BudgetExceeded,
    CostEntry,
    CostLedger,
)


@pytest.fixture
def ledger(tmp_path) -> CostLedger:
    return CostLedger(tmp_path / "costs.jsonl")


def entry(product="p1", usd=GEMINI_IMAGE_USD, dry=False) -> CostEntry:
    return CostEntry(
        product_id=product,
        asset_key="white_hero",
        provider="gemini",
        model="gemini-2.5-flash-image",
        operation="generate",
        usd=usd,
        inr=usd * get_settings().usd_to_inr,
        dry_run=dry,
    )


def test_an_image_costs_about_three_and_a_half_rupees():
    """Seven assets plus retries must fit inside the ₹100 default cap."""
    inr = GEMINI_IMAGE_USD * get_settings().usd_to_inr
    assert 2.5 < inr < 5.0, inr
    assert inr * 7 < 100, "seven assets should not approach the cap"


def test_spend_accumulates_per_product(ledger):
    for _ in range(3):
        ledger.record(entry())
    ledger.record(entry(product="p2"))

    assert ledger.spent_inr("p1") == pytest.approx(3 * GEMINI_IMAGE_USD * 88, rel=0.01)
    assert ledger.spent_inr("p2") < ledger.spent_inr("p1")


def test_dry_run_entries_are_logged_but_never_charged(ledger):
    ledger.record(entry(dry=True))
    ledger.record(entry(dry=True))

    assert len(ledger.entries("p1")) == 2, "dry-run calls should still be visible"
    assert ledger.spent_inr("p1") == 0.0


def test_the_cap_blocks_the_call_that_would_exceed_it(ledger, monkeypatch):
    """One image is ~₹3.41, so a ₹10 cap affords two and refuses the third."""
    monkeypatch.setattr(get_settings(), "budget_cap_inr_per_product", 10.0)

    ledger.record(entry())
    ledger.check_budget("p1", GEMINI_IMAGE_USD)  # 3.41 + 3.41 = 6.82, allowed
    ledger.record(entry())

    with pytest.raises(BudgetExceeded) as exc:
        ledger.check_budget("p1", GEMINI_IMAGE_USD)  # would reach 10.22

    assert exc.value.cap_inr == 10.0
    assert exc.value.spent_inr == pytest.approx(6.81, abs=0.05)
    assert "Budget cap reached" in str(exc.value)


def test_a_call_that_exactly_fits_is_allowed(ledger, monkeypatch):
    """The cap is a ceiling, not a fence one image short of it."""
    one = GEMINI_IMAGE_USD * get_settings().usd_to_inr
    monkeypatch.setattr(get_settings(), "budget_cap_inr_per_product", one * 2)

    ledger.record(entry())
    ledger.check_budget("p1", GEMINI_IMAGE_USD)  # lands exactly on the cap


def test_the_cap_message_names_the_numbers(ledger, monkeypatch):
    """The user has to know how much was spent and on what, not just 'blocked'."""
    monkeypatch.setattr(get_settings(), "budget_cap_inr_per_product", 1.0)
    with pytest.raises(BudgetExceeded, match=r"₹0\.00 of ₹1\.00"):
        ledger.check_budget("p1", GEMINI_IMAGE_USD * 100)


def test_the_running_total_survives_a_restart(tmp_path):
    """File-backed on purpose: an in-memory total resets on a crash, and the
    cap would silently stop capping."""
    path = tmp_path / "costs.jsonl"
    first = CostLedger(path)
    first.record(entry())
    first.record(entry())

    reopened = CostLedger(path)
    assert reopened.spent_inr("p1") == pytest.approx(first.spent_inr("p1"))


def test_totals_across_products(ledger):
    ledger.record(entry(product="p1"))
    ledger.record(entry(product="p2"))
    assert ledger.total_inr() == pytest.approx(2 * GEMINI_IMAGE_USD * 88, rel=0.01)


def test_an_empty_ledger_reads_as_zero(ledger):
    assert ledger.entries() == []
    assert ledger.total_inr() == 0.0
    assert ledger.spent_inr("anything") == 0.0
