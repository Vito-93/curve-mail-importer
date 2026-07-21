from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import httpx


@dataclass(frozen=True)
class FireflyTransaction:
    id: str
    description: str
    amount: Decimal
    date: date
    journal_id: str | None = None


class FireflyClient:

    def __init__(self, base_url: str, access_token: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    def create_withdrawal(
        self,
        *,
        description: str,
        amount: Decimal,
        date: date,
        source_account: str,
        destination_account: str,
        notes: str = "",
        currency: str = "EUR",
        tags: list[str] | None = None,
    ) -> str:
        txn: dict = {
            "type": "withdrawal",
            "date": date.isoformat(),
            "amount": str(amount),
            "description": description,
            "source_name": source_account,
            "destination_name": destination_account,
            "notes": notes,
            "currency_code": currency,
        }
        if tags:
            txn["tags"] = tags
        payload = {
            "fire_webhooks": True,
            "transactions": [txn],
        }
        response = self._client.post(
            f"{self._base_url}/api/v1/transactions", json=payload
        )
        response.raise_for_status()
        return response.json()["data"]["id"]

    def search_transactions(
        self, *, description: str, date: date, source_account: str
    ) -> list[FireflyTransaction]:
        query = f'description:"{description}" date:{date.isoformat()} source:"{source_account}"'
        results: list[FireflyTransaction] = []
        page = 1
        while True:
            response = self._client.get(
                f"{self._base_url}/api/v1/search/transactions",
                params={"query": query, "page": page},
            )
            response.raise_for_status()
            data = response.json().get("data", [])
            if not data:
                break
            for item in data:
                txns = item.get("attributes", {}).get("transactions", [])
                for txn in txns:
                    results.append(
                        FireflyTransaction(
                            id=item["id"],
                            description=txn.get("description", ""),
                            amount=Decimal(txn["amount"]).quantize(Decimal("0.01")),
                            date=date,
                            journal_id=txn.get("transaction_journal_id"),
                        )
                    )
            page += 1
            if page > 10:
                break
        return results

    def update_transaction_amount(self, transaction_id: str, amount: Decimal) -> None:
        payload = {
            "fire_webhooks": False,
            "apply_rules": False,
            "transactions": [
                {"amount": str(amount)},
            ],
        }
        response = self._client.put(
            f"{self._base_url}/api/v1/transactions/{transaction_id}",
            json=payload,
        )
        response.raise_for_status()

    def close(self) -> None:
        self._client.close()
