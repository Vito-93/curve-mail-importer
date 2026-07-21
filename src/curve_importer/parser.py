from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

_MONTH_TO_NUMBER = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

_PURCHASE_MARKERS = (
    "You made a purchase at:",
    "Hai fatto un acquisto da:",
)

_UPDATE_MARKERS = (
    "There's been an update to your transaction",
    "C'è stato un aggiornamento alla tua transazione",
    "aggiornamento",
)

_STATEMENT_MARKERS = (
    "This Transaction will appear on your bank statement as:",
    "Questa transazione apparirà sull'estratto conto come:",
)

_CARD_MARKERS = (
    "On this card:",
    "Per questa carta:",
)

_AMOUNT_PATTERN = re.compile(
    r"(?:€\s*(\d[\d.,]*))|(?:(\d[\d.,]*)\s*€)"
)

_DATE_PATTERN = re.compile(
    r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(\d{4})",
    re.IGNORECASE,
)


class CurveParseError(RuntimeError):
    pass


@dataclass(frozen=True)
class CurveReceipt:
    merchant_pretty: str
    amount: Decimal
    currency: str
    transaction_date: date
    bank_statement_line: str
    receipt_variant: str


def _detect_variant(text: str) -> str:
    for marker in _UPDATE_MARKERS:
        if marker.lower() in text.lower():
            return "updated"
    return "initial"


def _find_after_marker(text: str, markers: tuple[str, ...]) -> str | None:
    text_lower = text.lower()
    for marker in markers:
        pos = text_lower.find(marker.lower())
        if pos >= 0:
            after = text[pos + len(marker):]
            line = after.strip().split("\n")[0].strip()
            if line:
                return line
    return None


def _extract_merchant_and_amount(text: str) -> tuple[str, Decimal]:
    text_lower = text.lower()
    purchase_pos = -1
    for marker in _PURCHASE_MARKERS:
        pos = text_lower.find(marker.lower())
        if pos >= 0:
            purchase_pos = pos + len(marker)
            break

    if purchase_pos < 0:
        raise CurveParseError("No purchase marker found")

    after_marker = text[purchase_pos:].strip()
    lines = [l.strip() for l in after_marker.split("\n") if l.strip()]

    merchant = None
    amount = None

    for line in lines[:5]:
        match = _AMOUNT_PATTERN.search(line)
        if match:
            raw_amount = match.group(1) or match.group(2)
            if "," in raw_amount and "." in raw_amount:
                raw_amount = raw_amount.replace(".", "").replace(",", ".")
            else:
                raw_amount = raw_amount.replace(",", ".")
            amount = Decimal(raw_amount)

            line_merchant = line[:match.start()].strip()
            if not line_merchant:
                line_merchant = line[match.end():].strip()
            if line_merchant:
                merchant = line_merchant
            break
        elif merchant is None:
            merchant = re.sub(r"\s+", " ", line).strip()

    if amount is None:
        raise CurveParseError(f"No amount found after purchase marker")
    if not merchant:
        raise CurveParseError(f"No merchant found after purchase marker")

    return merchant, amount


def _extract_date(text: str) -> date:
    match = _DATE_PATTERN.search(text)
    if not match:
        raise CurveParseError("No date found")

    day = int(match.group(1))
    month = _MONTH_TO_NUMBER[match.group(2).lower()]
    year = int(match.group(3))
    return date(year, month, day)


def _extract_date_after_purchase(text: str) -> date:
    text_lower = text.lower()
    purchase_pos = -1
    for marker in _PURCHASE_MARKERS:
        pos = text_lower.find(marker.lower())
        if pos >= 0:
            purchase_pos = pos + len(marker)
            break

    if purchase_pos < 0:
        raise CurveParseError("No purchase marker found for date extraction")

    after_marker = text[purchase_pos:]
    lines = after_marker.strip().split("\n")
    if len(lines) < 2:
        raise CurveParseError("No date line after merchant line")

    for line in lines[1:]:
        match = _DATE_PATTERN.search(line)
        if match:
            day = int(match.group(1))
            month = _MONTH_TO_NUMBER[match.group(2).lower()]
            year = int(match.group(3))
            return date(year, month, day)

    raise CurveParseError("No date found after purchase marker")


_STATEMENT_NOISE = re.compile(
    r"\s*(?:generato in data|generated on)\b.*$", re.IGNORECASE
)


def _extract_bank_statement_line(text: str) -> str | None:
    raw = _find_after_marker(text, _STATEMENT_MARKERS)
    if raw is None:
        return None
    cleaned = _STATEMENT_NOISE.sub("", raw).strip()
    return cleaned or None


def parse_curve_email(body: str) -> CurveReceipt:
    variant = _detect_variant(body)
    merchant, amount = _extract_merchant_and_amount(body)
    transaction_date = _extract_date_after_purchase(body)
    bank_statement_line = _extract_bank_statement_line(body)

    if bank_statement_line is None:
        raise CurveParseError("No bank statement line found")

    return CurveReceipt(
        merchant_pretty=merchant,
        amount=amount,
        currency="EUR",
        transaction_date=transaction_date,
        bank_statement_line=" ".join(bank_statement_line.split()),
        receipt_variant=variant,
    )
