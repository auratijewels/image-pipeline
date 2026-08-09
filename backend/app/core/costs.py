"""Per-call cost ledger and the per-product budget guardrail (§6, §11)."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.config.settings import get_settings

# Gemini 2.5 Flash Image bills images as output tokens: 1290 tokens per image
# at $30 / 1M output tokens ≈ $0.039 per generated image.
GEMINI_IMAGE_TOKENS = 1290
GEMINI_OUTPUT_USD_PER_MTOK = 30.0
GEMINI_IMAGE_USD = GEMINI_IMAGE_TOKENS / 1_000_000 * GEMINI_OUTPUT_USD_PER_MTOK


class BudgetExceeded(RuntimeError):
    """Raised before a call that would push a product past its cap."""

    def __init__(self, product_id: str, spent_inr: float, cap_inr: float, next_call_inr: float):
        self.product_id = product_id
        self.spent_inr = spent_inr
        self.cap_inr = cap_inr
        self.next_call_inr = next_call_inr
        super().__init__(
            f"Budget cap reached for {product_id}: spent ₹{spent_inr:.2f} of ₹{cap_inr:.2f}; "
            f"next call would add ₹{next_call_inr:.2f}."
        )


@dataclass
class CostEntry:
    product_id: str
    asset_key: str
    provider: str
    model: str
    operation: str  # "generate" | "edit" | "harmonize"
    usd: float
    inr: float
    dry_run: bool = False
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CostLedger:
    """Append-only spend log, one JSONL file for the whole install.

    Kept deliberately simple and file-backed: the running total has to survive a
    crash mid-generation, otherwise the cap silently resets and over-spends.
    """

    def __init__(self, path: Path | None = None):
        s = get_settings()
        self.path = path or (s.data_dir / "costs.jsonl")
        self._lock = threading.Lock()

    def record(self, entry: CostEntry) -> CostEntry:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(entry)) + "\n")
        return entry

    def entries(self, product_id: str | None = None) -> list[CostEntry]:
        if not self.path.exists():
            return []
        out: list[CostEntry] = []
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                if product_id is None or data.get("product_id") == product_id:
                    out.append(CostEntry(**data))
        return out

    def spent_inr(self, product_id: str) -> float:
        return sum(e.inr for e in self.entries(product_id) if not e.dry_run)

    def total_inr(self) -> float:
        return sum(e.inr for e in self.entries() if not e.dry_run)

    def check_budget(self, product_id: str, next_call_usd: float) -> None:
        """Raise before spending, not after — the cap is a stop, not a report."""
        s = get_settings()
        if s.is_dry_run:
            return
        spent = self.spent_inr(product_id)
        next_inr = next_call_usd * s.usd_to_inr
        if spent + next_inr > s.budget_cap_inr_per_product:
            raise BudgetExceeded(product_id, spent, s.budget_cap_inr_per_product, next_inr)


_ledger: CostLedger | None = None


def get_ledger() -> CostLedger:
    global _ledger
    if _ledger is None:
        _ledger = CostLedger()
    return _ledger


def usd_to_inr(usd: float) -> float:
    return usd * get_settings().usd_to_inr
