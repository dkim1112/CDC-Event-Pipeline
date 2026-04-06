"""
Processing Metrics — tracks consumer health per time window.

Records events/second, lag, errors, and out-of-order counts
in 1-minute windows.
"""

import logging
from datetime import datetime, timezone, timedelta

from consumer.config import METRICS_WINDOW_SECONDS

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects metrics for the current time window and flushes to DB."""

    def __init__(self):
        self.reset()

    def reset(self):
        now = datetime.now(timezone.utc)
        self.window_start = now
        self.events_processed = 0
        self.errors = 0
        self.out_of_order_count = 0
        self.max_lag_ms = 0
        self.total_lag_ms = 0
        self._last_source_ts = {}  # per-table tracking for out-of-order detection

    def record_event(self, source_table: str, source_ts: datetime, processed_at: datetime):
        """Record a successfully processed event."""
        self.events_processed += 1

        # Calculate lag
        if source_ts and processed_at:
            lag_ms = int((processed_at - source_ts).total_seconds() * 1000)
            self.total_lag_ms += max(lag_ms, 0)
            self.max_lag_ms = max(self.max_lag_ms, lag_ms)

        # Detect out-of-order events
        if source_ts and source_table:
            last = self._last_source_ts.get(source_table)
            if last and source_ts < last:
                self.out_of_order_count += 1
                logger.warning("Out-of-order event on %s: %s < %s", source_table, source_ts, last)
            self._last_source_ts[source_table] = source_ts

    def record_error(self):
        self.errors += 1

    def should_flush(self) -> bool:
        elapsed = (datetime.now(timezone.utc) - self.window_start).total_seconds()
        return elapsed >= METRICS_WINDOW_SECONDS

    def flush(self, cursor):
        """Write current window metrics to DB and reset."""
        now = datetime.now(timezone.utc)
        elapsed = max((now - self.window_start).total_seconds(), 0.01)
        eps = self.events_processed / elapsed

        avg_lag = (self.total_lag_ms // self.events_processed) if self.events_processed > 0 else 0

        cursor.execute("""
            INSERT INTO processing_metrics
                (window_start, window_end, events_processed, events_per_second,
                 max_lag_ms, avg_lag_ms, errors, out_of_order_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            self.window_start,
            now,
            self.events_processed,
            round(eps, 2),
            self.max_lag_ms,
            avg_lag,
            self.errors,
            self.out_of_order_count,
        ))

        logger.info(
            "Metrics window: %d events, %.1f eps, max_lag=%dms, errors=%d, ooo=%d",
            self.events_processed, eps, self.max_lag_ms, self.errors, self.out_of_order_count,
        )

        self.reset()
