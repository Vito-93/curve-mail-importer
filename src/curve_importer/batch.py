from __future__ import annotations

import logging
from dataclasses import dataclass

from curve_importer.destinations import DestinationConfig
from curve_importer.firefly import FireflyClient
from curve_importer.parser import CurveReceipt

logger = logging.getLogger(__name__)

AUTO_TAG = "auto-curve-receipts"


def _normalize_key(text: str) -> str:
    return " ".join(text.lower().split())


def deduplicate_batch(receipts: list[CurveReceipt]) -> list[CurveReceipt]:
    by_key: dict[tuple[str, str], CurveReceipt] = {}
    for r in receipts:
        key = (_normalize_key(r.bank_statement_line), r.transaction_date.isoformat())
        existing = by_key.get(key)
        if existing is None or r.receipt_variant == "updated":
            by_key[key] = r
    return list(by_key.values())


@dataclass
class BatchResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0


def process_batch(
    receipts: list[CurveReceipt],
    firefly: FireflyClient,
    source_account: str,
    destinations: DestinationConfig | None = None,
) -> BatchResult:
    deduped = deduplicate_batch(receipts)
    result = BatchResult()
    dest_config = destinations or DestinationConfig()

    for receipt in deduped:
        try:
            if receipt.receipt_variant == "initial":
                _handle_initial(receipt, firefly, source_account, dest_config)
                result.created += 1
            else:
                _handle_updated(receipt, firefly, source_account, dest_config, result)
        except Exception:
            logger.exception("Failed to process receipt: %s", receipt.merchant_pretty)
            result.errors += 1

    return result


def _resolve_destination(receipt: CurveReceipt, dest_config: DestinationConfig) -> str:
    search_text = f"{receipt.bank_statement_line} {receipt.merchant_pretty}"
    return dest_config.resolve(search_text)


def _handle_initial(
    receipt: CurveReceipt,
    firefly: FireflyClient,
    source_account: str,
    dest_config: DestinationConfig,
) -> None:
    destination = _resolve_destination(receipt, dest_config)
    firefly.create_withdrawal(
        description=receipt.bank_statement_line,
        amount=receipt.amount,
        date=receipt.transaction_date,
        source_account=source_account,
        destination_account=destination,
        notes=receipt.merchant_pretty,
        currency=receipt.currency,
        tags=[AUTO_TAG],
    )
    logger.info(
        "Created: %s → %s %s%s",
        receipt.merchant_pretty, destination, receipt.currency, receipt.amount,
    )


def _handle_updated(
    receipt: CurveReceipt,
    firefly: FireflyClient,
    source_account: str,
    dest_config: DestinationConfig,
    result: BatchResult,
) -> None:
    matches = firefly.search_transactions(
        description=receipt.bank_statement_line,
        date=receipt.transaction_date,
        source_account=source_account,
    )

    if not matches:
        destination = _resolve_destination(receipt, dest_config)
        firefly.create_withdrawal(
            description=receipt.bank_statement_line,
            amount=receipt.amount,
            date=receipt.transaction_date,
            source_account=source_account,
            destination_account=destination,
            notes=receipt.merchant_pretty,
            currency=receipt.currency,
            tags=[AUTO_TAG],
        )
        result.created += 1
        logger.info(
            "Created (from updated, no prior match): %s → %s %s%s",
            receipt.merchant_pretty, destination, receipt.currency, receipt.amount,
        )
        return

    last = matches[-1]
    firefly.update_transaction_amount(last.id, receipt.amount)
    result.updated += 1
    logger.info(
        "Updated (LIFO): %s %s→%s",
        receipt.merchant_pretty, last.amount, receipt.amount,
    )
