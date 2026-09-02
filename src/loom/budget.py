"""Crash-safe, campaign-scoped OpenRouter spending guard."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BudgetState:
    spent_usd: Decimal
    warning: bool
    nonessential_blocked: bool
    remaining_usd: Decimal


class CampaignBudget:
    """Separate official/exploratory ledgers with checks before and after calls."""

    def __init__(
        self,
        directory: str | Path,
        campaign_id: str,
        *,
        kind: Literal["official", "exploratory"],
        warning_usd: Decimal = Decimal(8),
        nonessential_usd: Decimal = Decimal(9),
        limit_usd: Decimal = Decimal(10),
    ) -> None:
        if not campaign_id or "/" in campaign_id or ".." in campaign_id:
            raise ValueError("campaign_id must be a safe non-empty token")
        if not Decimal(0) <= warning_usd <= nonessential_usd <= limit_usd:
            raise ValueError("budget thresholds must be ordered")
        self.directory = Path(directory)
        self.path = self.directory / kind / f"{campaign_id}.json"
        self.warning_usd = warning_usd
        self.nonessential_usd = nonessential_usd
        self.limit_usd = limit_usd

    @property
    def spent(self) -> Decimal:
        if not self.path.exists():
            return Decimal(0)
        data = json.loads(self.path.read_text())
        return Decimal(str(data["spent_usd"]))

    def state(self) -> BudgetState:
        spent = self.spent
        return BudgetState(
            spent,
            spent >= self.warning_usd,
            spent >= self.nonessential_usd,
            max(Decimal(0), self.limit_usd - spent),
        )

    def authorize_campaign(self, projected_usd: Decimal) -> BudgetState:
        """Refuse a campaign whose complete estimate is over the warning threshold."""
        if projected_usd < 0:
            raise ValueError("projected cost cannot be negative")
        if projected_usd > self.warning_usd:
            raise BudgetExceeded(f"projected campaign cost exceeds ${self.warning_usd}")
        return self.state()

    def authorize(self, estimated_usd: Decimal, *, essential: bool = True) -> BudgetState:
        if estimated_usd < 0:
            raise ValueError("estimated cost cannot be negative")
        state = self.state()
        if not essential and state.nonessential_blocked:
            raise BudgetExceeded(f"nonessential runs stop at ${self.nonessential_usd}")
        if state.spent_usd + estimated_usd > self.limit_usd:
            raise BudgetExceeded(f"campaign hard limit is ${self.limit_usd}")
        return state

    def record(self, cost_usd: Decimal) -> BudgetState:
        if cost_usd < 0:
            raise ValueError("cost cannot be negative")
        spent = self.spent + cost_usd
        if spent > self.limit_usd:
            raise BudgetExceeded(f"response would exceed campaign hard limit ${self.limit_usd}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = (
            json.dumps({"schema_version": "1", "spent_usd": str(spent)}, sort_keys=True) + "\n"
        )
        fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}.")
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return self.state()
