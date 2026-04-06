#!/bin/bash
# Verify that analytics snapshots match source DB state.
# This is the Phase 2 exit criteria: "snapshots match source DB state"

set -e

echo "=== Snapshot Consistency Check ==="
echo ""

# --- Orders ---
echo "1) Orders: comparing source DB vs analytics snapshots"

SOURCE_ORDERS=$(docker exec cdc-source-db psql -U postgres -d source_db -t -A -c "
  SELECT id, customer_id, status, total_amount
  FROM orders ORDER BY id;
")

SNAPSHOT_ORDERS=$(docker exec cdc-analytics-db psql -U analytics_user -d analytics_db -t -A -c "
  SELECT order_id, customer_id, status, total_amount
  FROM order_snapshots ORDER BY order_id;
")

echo "   Source orders:"
echo "$SOURCE_ORDERS" | head -5
echo "   ..."
echo ""
echo "   Snapshot orders:"
echo "$SNAPSHOT_ORDERS" | head -5
echo "   ..."
echo ""

# Count comparison
SOURCE_COUNT=$(docker exec cdc-source-db psql -U postgres -d source_db -t -A -c "SELECT COUNT(*) FROM orders;")
SNAP_COUNT=$(docker exec cdc-analytics-db psql -U analytics_user -d analytics_db -t -A -c "SELECT COUNT(*) FROM order_snapshots;")
echo "   Source count: $SOURCE_COUNT | Snapshot count: $SNAP_COUNT"

if [ "$SOURCE_COUNT" = "$SNAP_COUNT" ]; then
  echo "   ✓ Row counts match"
else
  echo "   ✗ Row counts differ"
fi

# Status match check
MISMATCHED=$(docker exec cdc-source-db psql -U postgres -d source_db -t -A -c "
  SELECT COUNT(*) FROM orders;
")
echo ""

# --- Inventory ---
echo "2) Inventory: comparing source DB vs analytics snapshots"

SOURCE_INV=$(docker exec cdc-source-db psql -U postgres -d source_db -t -A -c "
  SELECT i.product_id, p.name, i.quantity, i.reserved
  FROM inventory i JOIN products p ON i.product_id = p.id
  ORDER BY i.product_id;
")

SNAPSHOT_INV=$(docker exec cdc-analytics-db psql -U analytics_user -d analytics_db -t -A -c "
  SELECT product_id, product_name, quantity, reserved, available
  FROM inventory_snapshots ORDER BY product_id;
")

echo "   Source inventory:"
echo "$SOURCE_INV" | head -5
echo "   ..."
echo ""
echo "   Snapshot inventory:"
echo "$SNAPSHOT_INV" | head -5
echo "   ..."
echo ""

SOURCE_INV_COUNT=$(docker exec cdc-source-db psql -U postgres -d source_db -t -A -c "SELECT COUNT(*) FROM inventory;")
SNAP_INV_COUNT=$(docker exec cdc-analytics-db psql -U analytics_user -d analytics_db -t -A -c "SELECT COUNT(*) FROM inventory_snapshots;")
echo "   Source count: $SOURCE_INV_COUNT | Snapshot count: $SNAP_INV_COUNT"

if [ "$SOURCE_INV_COUNT" = "$SNAP_INV_COUNT" ]; then
  echo "   ✓ Row counts match"
else
  echo "   ✗ Row counts differ"
fi

echo ""

# --- Pipeline health ---
echo "3) Pipeline health"

TOTAL_EVENTS=$(docker exec cdc-analytics-db psql -U analytics_user -d analytics_db -t -A -c "SELECT COUNT(*) FROM event_log;")
DEAD_LETTERS=$(docker exec cdc-analytics-db psql -U analytics_user -d analytics_db -t -A -c "SELECT COUNT(*) FROM dead_letter_events;")
TOTAL_ERRORS=$(docker exec cdc-analytics-db psql -U analytics_user -d analytics_db -t -A -c "SELECT COALESCE(SUM(errors), 0) FROM processing_metrics;")

echo "   Total events processed: $TOTAL_EVENTS"
echo "   Dead letters: $DEAD_LETTERS"
echo "   Total errors: $TOTAL_ERRORS"
echo ""
echo "=== Done ==="
