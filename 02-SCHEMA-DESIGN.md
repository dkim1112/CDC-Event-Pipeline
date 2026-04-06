# Schema Design

## Two Databases

1. **Source DB** — normal e-commerce tables (what Debezium watches)
2. **Analytics DB** — event log + snapshots (where the consumer writes)

---

## Source DB

### customers
- id (PK), email (UNIQUE), name, created_at, updated_at

### products
- id (PK), name, category, base_price, created_at

### inventory
- product_id (PK, FK → products), quantity, reserved, updated_at

### orders
- id (PK), customer_id (FK), status, total_amount, created_at, updated_at

Order lifecycle: `CREATED → PAID → SHIPPED → DELIVERED` (can also go `CREATED → CANCELLED` or `PAID → REFUNDED`)

### order_items
- id (PK), order_id (FK), product_id (FK), quantity, unit_price, created_at

---

## Analytics DB

### event_log (append-only)

The main table. Every change from Debezium gets stored here as-is.

- id (BIGSERIAL PK)
- event_id (UUID, UNIQUE) — for dedup
- source_table, operation (c/u/d/r)
- record_key (JSONB) — PK of changed row
- before_state, after_state (JSONB)
- source_ts — when the change happened
- processed_at — when we processed it
- kafka_topic, kafka_partition, kafka_offset
- source_lsn, source_txid

### order_snapshots

Current state of each order, rebuilt from events.

- order_id (PK), customer_id, status, total_amount, item_count
- created_at, last_updated_at, snapshot_version, computed_at

### inventory_snapshots

Current stock levels per product.

- product_id (PK), product_name, quantity, reserved
- available (= quantity - reserved)
- last_updated_at, snapshot_version, computed_at

### processing_metrics

Consumer health stats per 1-minute window.

- window_start, events_processed, events_per_second
- max_lag_ms, avg_lag_ms, errors, out_of_order_count

### dead_letter_events

Events that failed processing.

- event_id, source_table, raw_event (JSONB)
- error_message, retry_count, created_at, resolved_at

---

## Volume Estimates

With the simulator at ~10 orders/minute: ~50 events/minute → ~72K events/day. Snapshots grow with unique orders. Manageable on a local machine.
