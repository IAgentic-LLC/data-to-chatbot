"""Governance: read data/governance/policy.yaml and answer questions about it in code."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from . import config

POLICY_FILE = config.ROOT / "governance" / "policy.yaml"


@dataclass
class SourcePolicy:
    classification: str
    owner: str
    retention_days: int | None
    purpose: str


def load(path: Path = POLICY_FILE) -> dict[str, SourcePolicy]:
    import yaml
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return {name: SourcePolicy(v["classification"], v["owner"], v.get("retention_days"), v["purpose"]) for name, v in raw["sources"].items()}


def is_expired(policy: SourcePolicy, doc_date: str | None, today: date) -> bool:
    """A document is past its retention period when its own date is older than the limit. No date or no limit: not expired
    (and a missing date on a limited source is a finding for the data owner, reported by `unknown_dates`)."""
    if policy.retention_days is None or not doc_date:
        return False
    try:
        d = datetime.strptime(doc_date[:10], "%Y-%m-%d").date()
    except ValueError:
        return False
    return today - d > timedelta(days=policy.retention_days)
