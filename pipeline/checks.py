"""Episode 4: data quality checks. Each returns a name, pass/fail and a plain detail. The DAG fails the run if a blocking check fails.
Rule: a check that nobody reads is decoration. Every failure here says what to look at."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    blocking: bool = True

    def __str__(self):
        return f"[{'PASS' if self.ok else 'FAIL'}{'' if self.blocking or self.ok else ' (warning)'}] {self.name}: {self.detail}"


def feed_freshness(records, max_age_hours: float, now: datetime | None = None) -> Check:
    """A feed that has delivered nothing new for too long is probably broken upstream, even if our code is fine."""
    now = now or datetime.now(timezone.utc)
    newest: dict[str, datetime] = {}
    for r in records:
        newest[r.source] = max(newest.get(r.source, r.fetched_at), r.fetched_at)
    stale = [f"{s} ({(now - t) / timedelta(hours=1):.0f}h old)" for s, t in sorted(newest.items()) if now - t > timedelta(hours=max_age_hours)]
    return Check("feed freshness", not stale, "all feeds delivered within %gh" % max_age_hours if not stale else "no new files for: " + ", ".join(stale), blocking=False)


def silver_contract(docs) -> Check:
    """The shape every silver document must have before anything downstream trusts it."""
    bad = [d.doc_key for d in docs if not d.title.strip() or not d.text.strip() or len(d.text_sha256) != 64]
    return Check("silver contract (title, text, hash present)", not bad, f"{len(docs)} documents ok" if not bad else "broken: " + ", ".join(bad[:5]))


def reject_rate(rejected: int, total: int, max_share: float = 0.5) -> Check:
    share = rejected / total if total else 0.0
    return Check("reject rate", share <= max_share, f"{rejected} of {total} files rejected ({share:.0%}); limit {max_share:.0%}")


def has_content(curated) -> Check:
    n = sum(1 for c in curated if c.status == "accepted")
    return Check("something is searchable", n > 0, f"{n} accepted documents")


def no_unreviewed_injection(curated) -> Check:
    """Quarantined documents are fine (they are held back). This guards against one slipping through as accepted."""
    from . import injection
    leaked = [c.doc_key for c in curated if c.status == "accepted" and "approved-by-reviewer" not in c.flags and injection.scan(c.text)]
    return Check("no instruction-like text in accepted documents", not leaked, "clean" if not leaked else "found in: " + ", ".join(leaked))


def no_personal_data(curated) -> Check:
    from . import pii
    left = [c.doc_key for c in curated if c.status == "accepted" and pii.scrub(c.text)[1]]
    return Check("no emails or phone numbers in accepted documents", not left, "clean" if not left else "found in: " + ", ".join(left))


def run_all(manifest_records, silver_docs, rejects, curated) -> list[Check]:
    return [
        feed_freshness(manifest_records, max_age_hours=48),
        silver_contract(silver_docs),
        reject_rate(len(rejects), len(silver_docs) + len(rejects)),
        has_content(curated),
        no_unreviewed_injection(curated),
        no_personal_data(curated),
    ]
