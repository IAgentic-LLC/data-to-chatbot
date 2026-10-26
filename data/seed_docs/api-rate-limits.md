# Public API Rate Limits
Owner: Platform.

## Limits
Partner API keys get 100 requests per minute using a token bucket that refills at 100 tokens per minute with a burst of 20. The checkout endpoint for customers is limited separately to 5 attempts per minute per user.

## When a limit is hit
The API returns HTTP 429 with a Retry-After header. Partners should back off with exponential backoff and jitter.
