"""Tests for event_log module — dedup and event ID generation."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from consumer.event_log import build_event_id


def test_same_input_gives_same_id():
    """Deterministic: same WAL position → same event_id."""
    source = {"table": "orders", "lsn": 12345, "txId": 100}
    key = {"id": 1}
    id1 = build_event_id(source, key)
    id2 = build_event_id(source, key)
    assert id1 == id2


def test_different_lsn_gives_different_id():
    """Different LSN → different event_id."""
    source1 = {"table": "orders", "lsn": 12345, "txId": 100}
    source2 = {"table": "orders", "lsn": 99999, "txId": 100}
    key = {"id": 1}
    assert build_event_id(source1, key) != build_event_id(source2, key)


def test_different_table_gives_different_id():
    """Same LSN but different table → different event_id."""
    source1 = {"table": "orders", "lsn": 12345, "txId": 100}
    source2 = {"table": "inventory", "lsn": 12345, "txId": 100}
    key = {"id": 1}
    assert build_event_id(source1, key) != build_event_id(source2, key)


def test_different_key_gives_different_id():
    """Same WAL position but different record key → different event_id."""
    source = {"table": "orders", "lsn": 12345, "txId": 100}
    assert build_event_id(source, {"id": 1}) != build_event_id(source, {"id": 2})


def test_missing_fields_dont_crash():
    """Handles missing source fields gracefully."""
    event_id = build_event_id({}, {})
    assert event_id is not None
    assert len(event_id) == 36  # UUID format


def test_key_ordering_doesnt_matter():
    """JSON keys are sorted, so {"a":1,"b":2} == {"b":2,"a":1}."""
    source = {"table": "orders", "lsn": 100, "txId": 1}
    id1 = build_event_id(source, {"a": 1, "b": 2})
    id2 = build_event_id(source, {"b": 2, "a": 1})
    assert id1 == id2
