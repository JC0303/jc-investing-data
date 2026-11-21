"""Classify an admitted trade without substituting a price for a missing bar."""
import math

WINDOW_INCOMPLETE = "WINDOW_INCOMPLETE"
SETTLED = "SETTLED"
PERIOD_MISSING = "PERIOD_PRICE_MISSING"
EXIT_MISSING = "EXIT_PRICE_MISSING"


def valid_price(value):
    return math.isfinite(value) and value > 0


def holding_outcome(prices, entry, horizon, stop, *, target=None, next_close=True):
    """Use the maximum possible window to decide whether this cohort can be scored."""
    status, exit_index, reason = observed_exit(prices, entry, horizon, stop, target, next_close)
    latest_exit = entry + horizon + int(target is not None and next_close)
    if latest_exit >= len(prices):
        # Keep a known execution for position tracking, but never score its return.
        return WINDOW_INCOMPLETE, exit_index if status == SETTLED else None, reason
    return status, exit_index, reason


def observed_exit(prices, entry, horizon, stop, target, next_close):
    if not valid_price(prices[entry]):
        return PERIOD_MISSING, None, "missing_entry"
    end = entry + horizon
    # A-track tests its target/stop even on the last day; v2/v3 time-exit that day.
    for i in range(entry + 1, end + int(target is not None)):
        if i >= len(prices):
            return EXIT_MISSING if i == end else PERIOD_MISSING, None, "window_ended"
        if not valid_price(prices[i]):
            status = EXIT_MISSING if i == end else PERIOD_MISSING
            return status, i if i == end else None, "missing_close"
        if prices[i] <= prices[entry] * stop:
            reason = "stop"
        elif target is not None and prices[i] >= prices[entry] * target:
            reason = "target"
        else:
            continue
        end = i + int(next_close)
        break
    else:
        reason = "time"
    if end >= len(prices):
        return EXIT_MISSING, None, reason
    return (SETTLED if valid_price(prices[end]) else EXIT_MISSING), end, reason


def coverage(rows):
    counts = rows.status.value_counts()
    incomplete = counts.get(WINDOW_INCOMPLETE, 0)
    return (f"Admitted: {len(rows)}; complete windows: {len(rows) - incomplete}; "
            f"WINDOW_INCOMPLETE: {incomplete}; settled: {counts.get(SETTLED, 0)}; "
            f"period price missing: {counts.get(PERIOD_MISSING, 0)}; "
            f"exit price missing: {counts.get(EXIT_MISSING, 0)}")
