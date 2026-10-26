# Postmortem INC-2051: Checkout 503 errors during the Volt Runner drop
Date: 2026-05-08 (Friday, 10:00). Severity: SEV-1. Owner: Platform.

## What happened
Traffic peaked at 3,000 requests per second. Bots retried checkout in tight loops, the checkout queue overflowed, and 18% of checkout requests returned HTTP 503 for 11 minutes.

## Fixes
1. A virtual waiting room in front of drop product pages.
2. A checkout rate limit of 5 attempts per minute per user, returning error E-4029.
3. Checkout scaled to 40 pods before every drop (see the drop-day runbook).
