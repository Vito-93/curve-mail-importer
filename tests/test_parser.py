from datetime import date
from decimal import Decimal

import pytest

from curve_importer.parser import parse_curve_email, CurveParseError, CurveReceipt


ITALIAN_INITIAL_BODY = """\
Ricevuta email
Ciao Vito,


Hai fatto un acquisto da:
Oscar Calzature Snc    133.92€
20 July 2026
Per questa carta:

Vito Vattiata
Mastercard Debit
XXXX-4616
Questa transazione apparirà sull'estratto conto come:
OSCAR CALZATURE SNC TORINO ITA
Generato in data 20 July 2026 09:56 UTC
"""


ENGLISH_UPDATED_BODY = """\
Email Receipt
Hello Vito,


There's been an update to your transaction, below are the new details.

You made a purchase at:
Tap Go    €3.80
17 July 2026 08:22:05
On this card:

Vito Vattiata
Mastercard Debit
XXXX-4616
Receipt for the purchase (add it using the Curve App):


This Transaction will appear on your bank statement as:
TAP GO TORINO ITA
"""


def test_parse_italian_initial_receipt():
    receipt = parse_curve_email(ITALIAN_INITIAL_BODY)

    assert receipt.merchant_pretty == "Oscar Calzature Snc"
    assert receipt.amount == Decimal("133.92")
    assert receipt.currency == "EUR"
    assert receipt.transaction_date == date(2026, 7, 20)
    assert receipt.bank_statement_line == "OSCAR CALZATURE SNC TORINO ITA"
    assert receipt.receipt_variant == "initial"


def test_parse_english_updated_receipt():
    receipt = parse_curve_email(ENGLISH_UPDATED_BODY)

    assert receipt.merchant_pretty == "Tap Go"
    assert receipt.amount == Decimal("3.80")
    assert receipt.currency == "EUR"
    assert receipt.transaction_date == date(2026, 7, 17)
    assert receipt.bank_statement_line == "TAP GO TORINO ITA"
    assert receipt.receipt_variant == "updated"


NON_EUR_BODY = """\
Email Receipt
Hello Vito,

You made a purchase at:
Some Shop    £25.00
10 July 2026
On this card:

Vito Vattiata
Mastercard Debit
XXXX-4616
This Transaction will appear on your bank statement as:
SOME SHOP LONDON GBR
"""


COMMA_AMOUNT_BODY = """\
Ricevuta email
Ciao Vito,

Hai fatto un acquisto da:
Ristorante Da Mario    1.234,56€
5 August 2026
Per questa carta:

Vito Vattiata
Mastercard Debit
XXXX-4616
Questa transazione apparirà sull'estratto conto come:
RISTORANTE DA MARIO ROMA ITA
"""


UPDATED_MERCHANT_SEPARATE_LINE = """\
Email Receipt
Hello Vito,


There's been an update to your transaction, below are the new details.

You made a purchase at:
Tap   Go
€3.80
17 July 2026 08:22:05
On this card:

Vito Vattiata
Mastercard Debit
XXXX-4616
This Transaction will appear on your bank statement as:
TAP GO TORINO ITA
"""


def test_parse_merchant_and_amount_on_separate_lines():
    receipt = parse_curve_email(UPDATED_MERCHANT_SEPARATE_LINE)

    assert receipt.merchant_pretty == "Tap Go"
    assert receipt.amount == Decimal("3.80")
    assert receipt.receipt_variant == "updated"
    assert receipt.bank_statement_line == "TAP GO TORINO ITA"


def test_reject_non_eur_currency():
    with pytest.raises(CurveParseError):
        parse_curve_email(NON_EUR_BODY)


def test_parse_amount_with_comma_decimal():
    receipt = parse_curve_email(COMMA_AMOUNT_BODY)

    assert receipt.amount == Decimal("1234.56")
    assert receipt.merchant_pretty == "Ristorante Da Mario"
