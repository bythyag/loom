from decimal import Decimal

import pytest

from loom.budget import BudgetExceeded, CampaignBudget


def ledger(tmp_path, campaign="campaign", kind="official"):
    return CampaignBudget(tmp_path, campaign, kind=kind)


def test_persists_cost_after_every_response(tmp_path):
    first = ledger(tmp_path)
    assert first.record(Decimal("1.25")).spent_usd == Decimal("1.25")
    assert ledger(tmp_path).record(Decimal("0.75")).spent_usd == Decimal("2.00")


def test_refuses_projection_over_eight_dollars(tmp_path):
    budget = ledger(tmp_path)
    with pytest.raises(BudgetExceeded, match="projected"):
        budget.authorize_campaign(Decimal("8.01"))


def test_warns_at_eight_and_blocks_nonessential_at_nine(tmp_path):
    budget = ledger(tmp_path)
    assert budget.record(Decimal(8)).warning
    state = budget.record(Decimal(1))
    assert state.nonessential_blocked
    with pytest.raises(BudgetExceeded, match="nonessential"):
        budget.authorize(Decimal(0), essential=False)


def test_hard_stop_before_exceeding_ten(tmp_path):
    budget = ledger(tmp_path)
    budget.record(Decimal("9.99"))
    with pytest.raises(BudgetExceeded, match="hard limit"):
        budget.record(Decimal("0.02"))


def test_official_and_exploratory_ledgers_are_separate(tmp_path):
    ledger(tmp_path, kind="official").record(Decimal(2))
    assert ledger(tmp_path, kind="exploratory").spent == 0
