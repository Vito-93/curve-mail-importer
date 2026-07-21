from datetime import date
from decimal import Decimal

import httpx
import pytest

from curve_importer.firefly import FireflyClient


def test_create_withdrawal_sends_correct_payload(httpx_mock):
    httpx_mock.add_response(
        url="http://firefly:8080/api/v1/transactions",
        method="POST",
        json={"data": {"id": "42", "type": "transactions", "attributes": {"transactions": [{"transaction_journal_id": "99"}]}}},
        status_code=200,
    )

    client = FireflyClient(
        base_url="http://firefly:8080",
        access_token="test-token",
    )
    result = client.create_withdrawal(
        description="TAP GO TORINO ITA",
        amount=Decimal("3.80"),
        date=date(2026, 7, 17),
        source_account="Revolut",
        destination_account="Tap Go",
        notes="Tap Go",
        currency="EUR",
    )

    assert result == "42"
    request = httpx_mock.get_request()
    assert request.headers["authorization"] == "Bearer test-token"
    payload = request.read().decode()
    import json
    body = json.loads(payload)
    txn = body["transactions"][0]
    assert txn["type"] == "withdrawal"
    assert txn["amount"] == "3.80"
    assert txn["date"] == "2026-07-17"
    assert txn["description"] == "TAP GO TORINO ITA"
    assert txn["source_name"] == "Revolut"
    assert txn["destination_name"] == "Tap Go"
    assert txn["notes"] == "Tap Go"
    assert txn["currency_code"] == "EUR"
    assert body["fire_webhooks"] is True


def test_search_transactions_returns_matches(httpx_mock):
    httpx_mock.add_response(
        url=httpx.URL(
            "http://firefly:8080/api/v1/search/transactions",
            params={"query": 'description:"TAP GO TORINO ITA" date:2026-07-17 source:"Revolut"', "page": "1"},
        ),
        json={
            "data": [
                {
                    "id": "10",
                    "attributes": {
                        "transactions": [
                            {
                                "transaction_journal_id": "100",
                                "description": "TAP GO TORINO ITA",
                                "amount": "3.50",
                                "date": "2026-07-17",
                            }
                        ]
                    },
                },
                {
                    "id": "11",
                    "attributes": {
                        "transactions": [
                            {
                                "transaction_journal_id": "101",
                                "description": "TAP GO TORINO ITA",
                                "amount": "4.00",
                                "date": "2026-07-17",
                            }
                        ]
                    },
                },
            ]
        },
    )
    httpx_mock.add_response(
        url=httpx.URL(
            "http://firefly:8080/api/v1/search/transactions",
            params={"query": 'description:"TAP GO TORINO ITA" date:2026-07-17 source:"Revolut"', "page": "2"},
        ),
        json={"data": []},
    )

    client = FireflyClient(base_url="http://firefly:8080", access_token="t")
    results = client.search_transactions(
        description="TAP GO TORINO ITA",
        date=date(2026, 7, 17),
        source_account="Revolut",
    )

    assert len(results) == 2
    assert results[0].id == "10"
    assert results[0].amount == Decimal("3.50")
    assert results[1].id == "11"
    assert results[1].amount == Decimal("4.00")


def test_update_transaction_amount(httpx_mock):
    httpx_mock.add_response(
        url="http://firefly:8080/api/v1/transactions/10",
        method="PUT",
        json={"data": {"id": "10"}},
    )

    client = FireflyClient(base_url="http://firefly:8080", access_token="t")
    client.update_transaction_amount("10", Decimal("3.80"))

    request = httpx_mock.get_request()
    import json
    body = json.loads(request.read().decode())
    assert body["transactions"][0]["amount"] == "3.80"
    assert body["fire_webhooks"] is False
