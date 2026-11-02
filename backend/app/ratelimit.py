"""
Rate limiting: "no more than N actions in M seconds".

WHY: without it, a bot could try 10,000 passwords against one account,
or flood someone with messages. With it, they get "429 Too Many Requests".

HOW (a "sliding window"): for each key (e.g. "login:shobhit@test.com") we keep
the times of recent attempts. Before allowing a new one, we throw away attempts
older than the window, then check how many are left.

LIMITATION, on purpose: this lives in the server's memory. That's fine while we run
ONE server (Render free tier). If we ever run several servers, we'd move this into
a shared store like Redis. Restarting the server also resets all counters.
"""
import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, status

_hits: dict[str, deque] = defaultdict(deque)
_lock = Lock()  # FastAPI can handle several requests at once; the lock stops them clashing


def check_rate_limit(key: str, max_hits: int, window_seconds: int, message: str) -> None:
    """Record one attempt for `key`. Raises 429 if the limit is exceeded."""
    now = time.monotonic()
    with _lock:
        hits = _hits[key]
        while hits and now - hits[0] > window_seconds:
            hits.popleft()
        if len(hits) >= max_hits:
            retry_after = int(window_seconds - (now - hits[0])) + 1
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                message,
                headers={"Retry-After": str(retry_after)},  # tells the app how long to wait
            )
        hits.append(now)


def reset_rate_limits() -> None:
    """Used by tests to start with clean counters."""
    with _lock:
        _hits.clear()


# The limits, in one place so they're easy to tune.
LOGIN_LIMIT = (10, 5 * 60)        # 10 attempts per 5 minutes, per email
REQUEST_LIMIT = (10, 60 * 60)     # 10 buy requests per hour, per user
MESSAGE_LIMIT = (20, 60)          # 20 messages per minute, per user
REPORT_LIMIT = (10, 60 * 60)      # 10 reports per hour, per user
RESEND_CODE_LIMIT = (1, 60)       # 1 new verification code per minute, per user
RESEND_CODE_HOURLY = (5, 60 * 60) # ...and 5 per hour
FORGOT_LIMIT = (3, 15 * 60)       # 3 reset emails per 15 minutes, per email address
