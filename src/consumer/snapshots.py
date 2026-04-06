"""
Materialized Snapshots — current-state views derived from events.

These tables represent "what does the data look like right now?"
rebuilt from the event log. Unlike the source DB (which mutates rows),
snapshots here are updated by applying events in order.
"""

import json
import logging
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


def _safe_decimal(value) -> Decimal | None:
    """Convert a value to Decimal, handling base64 and string formats."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def update_order_snapshot(cursor, event: dict, event_log_id: int):
    """Update order_snapshots from an orders table event."""
    op = event.get("op")
    after = event.get("after")
    before = event.get("before")

    if op == "d":
        # Delete: remove snapshot
        if before and before.get("id"):
            cursor.execute("DELETE FROM order_snapshots WHERE order_id = %s", (before["id"],))
        return

    if not after:
        return

    order_id = after.get("id")
    if not order_id:
        return

    # Count items for this order (from existing snapshot or default 0)
    cursor.execute("SELECT item_count FROM order_snapshots WHERE order_id = %s", (order_id,))
    row = cursor.fetchone()
    item_count = row[0] if row else 0

    cursor.execute("""
        INSERT INTO order_snapshots
            (order_id, customer_id, status, total_amount, item_count,
             created_at, last_updated_at, snapshot_version, computed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (order_id) DO UPDATE SET
            customer_id = EXCLUDED.customer_id,
            status = EXCLUDED.status,
            total_amount = EXCLUDED.total_amount,
            item_count = order_snapshots.item_count,
            last_updated_at = EXCLUDED.last_updated_at,
            snapshot_version = EXCLUDED.snapshot_version,
            computed_at = NOW()
    """, (
        order_id,
        after.get("customer_id"),
        after.get("status"),
        _safe_decimal(after.get("total_amount")),
        item_count,
        after.get("created_at"),
        after.get("updated_at"),
        event_log_id,
    ))


def update_order_item_count(cursor, event: dict):
    """When an order_item is inserted, increment the item count on the order snapshot."""
    op = event.get("op")
    after = event.get("after")

    if op in ("c", "r") and after:
        order_id = after.get("order_id")
        if order_id:
            cursor.execute("""
                UPDATE order_snapshots
                SET item_count = item_count + 1, computed_at = NOW()
                WHERE order_id = %s
            """, (order_id,))


def update_inventory_snapshot(cursor, event: dict, event_log_id: int):
    """Update inventory_snapshots from an inventory table event."""
    op = event.get("op")
    after = event.get("after")
    before = event.get("before")

    if op == "d":
        if before and before.get("product_id"):
            cursor.execute("DELETE FROM inventory_snapshots WHERE product_id = %s",
                           (before["product_id"],))
        return

    if not after:
        return

    product_id = after.get("product_id")
    if not product_id:
        return

    # Get product name from existing snapshot or leave null
    cursor.execute("SELECT product_name FROM inventory_snapshots WHERE product_id = %s",
                   (product_id,))
    row = cursor.fetchone()
    product_name = row[0] if row else None

    cursor.execute("""
        INSERT INTO inventory_snapshots
            (product_id, product_name, quantity, reserved,
             last_updated_at, snapshot_version, computed_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (product_id) DO UPDATE SET
            quantity = EXCLUDED.quantity,
            reserved = EXCLUDED.reserved,
            last_updated_at = EXCLUDED.last_updated_at,
            snapshot_version = EXCLUDED.snapshot_version,
            computed_at = NOW()
    """, (
        product_id,
        product_name,
        after.get("quantity"),
        after.get("reserved"),
        after.get("updated_at"),
        event_log_id,
    ))


def update_product_name_on_inventory(cursor, event: dict):
    """When a product event comes in, update the name on the inventory snapshot."""
    after = event.get("after")
    if after and after.get("id") and after.get("name"):
        cursor.execute("""
            UPDATE inventory_snapshots
            SET product_name = %s, computed_at = NOW()
            WHERE product_id = %s
        """, (after["name"], after["id"]))
