from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass(frozen=True)
class DestinationRule:
    destination: str
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class DestinationConfig:
    default: str = "spese"
    rules: tuple[DestinationRule, ...] = ()

    def resolve(self, text: str) -> str:
        lowered = text.lower()
        for rule in self.rules:
            for kw in rule.keywords:
                if kw in lowered:
                    return rule.destination
        return self.default


def load_destination_config(path: Path | None = None) -> DestinationConfig:
    if path is None:
        path = Path("destination_rules.yaml")
    if not path.exists():
        return DestinationConfig()
    raw = yaml.safe_load(path.read_text()) or {}
    rules = tuple(
        DestinationRule(
            destination=r["destination"],
            keywords=tuple(k.lower() for k in r.get("keywords", [])),
        )
        for r in raw.get("rules", [])
    )
    return DestinationConfig(default=raw.get("default", "spese"), rules=rules)
