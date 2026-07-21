from datetime import date
from decimal import Decimal

from unittest.mock import MagicMock

from curve_importer.parser import CurveReceipt
from curve_importer.batch import deduplicate_batch, process_batch
from curve_importer.destinations import DestinationConfig, DestinationRule
from curve_importer.firefly import FireflyTransaction


def _receipt(
    merchant="Tap Go",
    amount="3.50",
    dt=date(2026, 7, 17),
    variant="initial",
    statement="TAP GO TORINO ITA",
) -> CurveReceipt:
    return CurveReceipt(
        merchant_pretty=merchant,
        amount=Decimal(amount),
        currency="EUR",
        transaction_date=dt,
        bank_statement_line=statement,
        receipt_variant=variant,
    )


def test_dedup_keeps_updated_over_initial_same_merchant_date():
    initial = _receipt(variant="initial", amount="3.50")
    updated = _receipt(variant="updated", amount="3.80")

    result = deduplicate_batch([initial, updated])

    assert len(result) == 1
    assert result[0].amount == Decimal("3.80")
    assert result[0].receipt_variant == "updated"


def test_dedup_keeps_both_when_different_merchants():
    tap = _receipt(merchant="Tap Go", statement="TAP GO TORINO ITA")
    oscar = _receipt(
        merchant="Oscar Calzature Snc",
        statement="OSCAR CALZATURE SNC TORINO ITA",
        amount="133.92",
    )

    result = deduplicate_batch([tap, oscar])

    assert len(result) == 2


def test_dedup_keeps_both_when_same_merchant_different_dates():
    day1 = _receipt(dt=date(2026, 7, 17))
    day2 = _receipt(dt=date(2026, 7, 18))

    result = deduplicate_batch([day1, day2])

    assert len(result) == 2


def test_process_batch_initial_creates_on_firefly():
    receipt = _receipt(variant="initial", amount="3.50")
    firefly = MagicMock()
    firefly.create_withdrawal.return_value = "42"

    result = process_batch([receipt], firefly, source_account="Revolut")

    assert result.created == 1
    assert result.updated == 0
    firefly.create_withdrawal.assert_called_once_with(
        description="TAP GO TORINO ITA",
        amount=Decimal("3.50"),
        date=date(2026, 7, 17),
        source_account="Revolut",
        destination_account="spese",
        notes="Tap Go",
        currency="EUR",
        tags=["auto-curve-receipts"],
    )


def test_process_batch_updated_searches_and_updates_lifo():
    receipt = _receipt(variant="updated", amount="3.80")
    firefly = MagicMock()
    firefly.search_transactions.return_value = [
        FireflyTransaction(id="10", description="TAP GO TORINO ITA", amount=Decimal("3.00"), date=date(2026, 7, 17)),
        FireflyTransaction(id="11", description="TAP GO TORINO ITA", amount=Decimal("3.50"), date=date(2026, 7, 17)),
    ]

    result = process_batch([receipt], firefly, source_account="Revolut")

    assert result.updated == 1
    assert result.created == 0
    firefly.update_transaction_amount.assert_called_once_with("11", Decimal("3.80"))


def test_process_batch_updated_no_match_creates_new():
    receipt = _receipt(variant="updated", amount="3.80")
    firefly = MagicMock()
    firefly.search_transactions.return_value = []
    firefly.create_withdrawal.return_value = "99"

    result = process_batch([receipt], firefly, source_account="Revolut")

    assert result.created == 1
    assert result.updated == 0
    firefly.create_withdrawal.assert_called_once()


def test_process_batch_routes_to_correct_destination():
    receipt = _receipt(
        merchant="Ryanair",
        statement="RYANAIR DUBLIN IRL",
        variant="initial",
        amount="49.99",
    )
    firefly = MagicMock()
    firefly.create_withdrawal.return_value = "50"
    rules = DestinationConfig(
        default="spese",
        rules=(DestinationRule(destination="ryanair", keywords=("ryanair", "easyjet")),),
    )

    result = process_batch([receipt], firefly, source_account="Revolut", destinations=rules)

    assert result.created == 1
    firefly.create_withdrawal.assert_called_once()
    call_kwargs = firefly.create_withdrawal.call_args.kwargs
    assert call_kwargs["destination_account"] == "ryanair"
