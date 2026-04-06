"""Tests for snapshot helper functions (no DB needed)."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from decimal import Decimal
from consumer.snapshots import _safe_decimal


def test_safe_decimal_string():
    assert _safe_decimal("123.45") == Decimal("123.45")


def test_safe_decimal_int():
    assert _safe_decimal(100) == Decimal("100")


def test_safe_decimal_float():
    result = _safe_decimal(99.99)
    assert result is not None
    assert float(result) == 99.99


def test_safe_decimal_none():
    assert _safe_decimal(None) is None


def test_safe_decimal_garbage():
    """Base64 or random strings return None instead of crashing."""
    assert _safe_decimal("AAAA==") is None


def test_safe_decimal_negative():
    assert _safe_decimal("-50.00") == Decimal("-50.00")


def test_safe_decimal_zero():
    assert _safe_decimal("0") == Decimal("0")
    assert _safe_decimal(0) == Decimal("0")
