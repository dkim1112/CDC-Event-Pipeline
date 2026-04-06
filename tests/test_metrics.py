"""Tests for MetricsCollector — lag, out-of-order, windowing."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from consumer.metrics import MetricsCollector


def test_initial_state():
    m = MetricsCollector()
    assert m.events_processed == 0
    assert m.errors == 0
    assert m.out_of_order_count == 0
    assert m.max_lag_ms == 0


def test_record_event_increments_count():
    m = MetricsCollector()
    now = datetime.now(timezone.utc)
    m.record_event("public.orders", now - timedelta(milliseconds=100), now)
    assert m.events_processed == 1


def test_lag_calculation():
    m = MetricsCollector()
    source_ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    processed_at = datetime(2026, 1, 1, 12, 0, 0, 500_000, tzinfo=timezone.utc)  # +500ms
    m.record_event("public.orders", source_ts, processed_at)
    assert m.max_lag_ms == 500
    assert m.total_lag_ms == 500


def test_out_of_order_detection():
    m = MetricsCollector()
    t1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 1, 12, 0, 1, tzinfo=timezone.utc)
    now = datetime(2026, 1, 1, 12, 1, 0, tzinfo=timezone.utc)

    # First event: t2 (later timestamp)
    m.record_event("public.orders", t2, now)
    assert m.out_of_order_count == 0

    # Second event: t1 (earlier timestamp) → out of order!
    m.record_event("public.orders", t1, now)
    assert m.out_of_order_count == 1


def test_out_of_order_is_per_table():
    """Events from different tables don't trigger out-of-order."""
    m = MetricsCollector()
    t1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 1, 12, 0, 1, tzinfo=timezone.utc)
    now = datetime(2026, 1, 1, 12, 1, 0, tzinfo=timezone.utc)

    m.record_event("public.orders", t2, now)
    m.record_event("public.inventory", t1, now)  # different table, earlier ts → NOT out of order
    assert m.out_of_order_count == 0


def test_record_error():
    m = MetricsCollector()
    m.record_error()
    m.record_error()
    assert m.errors == 2


def test_should_flush_respects_window():
    m = MetricsCollector()
    assert not m.should_flush()  # just created

    # Force window_start to be old
    m.window_start = datetime.now(timezone.utc) - timedelta(seconds=120)
    assert m.should_flush()


def test_reset_clears_everything():
    m = MetricsCollector()
    now = datetime.now(timezone.utc)
    m.record_event("public.orders", now, now)
    m.record_error()
    assert m.events_processed == 1
    assert m.errors == 1

    m.reset()
    assert m.events_processed == 0
    assert m.errors == 0
    assert m.out_of_order_count == 0
    assert m.max_lag_ms == 0
    assert m._last_source_ts == {}
