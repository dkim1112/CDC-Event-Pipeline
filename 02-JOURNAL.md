# Project Progress Journal

> Honest process, not perfect process. Failures and pivots are the most valuable entries.

---

## Project Kickoff

### What I did

- Chose e-commerce orders as the domain — natural fit for CDC since orders go through multiple state changes
- Set up project structure (CONTEXT, ROADMAP, DECISIONS, JOURNAL, SCHEMA-DESIGN)
- Learning CDC from scratch

### How I used AI

- Delegated: explaining CDC concepts, proposing architecture, drafting docs
- Decided myself: domain choice, project structure matching Project 01's approach

---

## Phase 0 — Research & Schema Design

### What I did

- Studied the CDC stack: PostgreSQL WAL → Debezium → Kafka → Python consumer
- Learned Debezium event format: each change has `op` (c/u/d/r), `before`, `after`, and `source` metadata (LSN, txId, table name)
- Designed two databases:
  - Source: 5 tables (customers, products, inventory, orders, order_items)
  - Analytics: event_log (append-only JSONB), snapshots, metrics, dead letter queue
- Wrote 5 ADRs

### What surprised me

- **Debezium runs inside Kafka Connect** — it's not a standalone process. You register a connector via REST API. Means we need a Kafka Connect container in Docker.
- **WAL bloat is a real risk** — if the consumer stops, PostgreSQL keeps WAL data for the replication slot. Can fill the disk. Solution: heartbeat events to keep the slot advancing.
- **Tombstone events** — when you DELETE a row, Debezium sends two messages: the delete event, then a null message (tombstone) for Kafka log compaction. Consumer needs to handle both.
- **Docker needs ~2-3 GB RAM** for the full stack (Kafka + Zookeeper + Debezium). Much heavier than Project 01.

### How I used AI

- Delegated: researching Debezium docs, Docker image names, event format details
- Decided myself: two-database architecture, JSONB event log design, order lifecycle states, which ADRs to write

### What to do next

- [x] Build Docker Compose with all services
- [x] Create source DB schema and seed data
- [x] Register Debezium connector and verify events in Kafka
- [x] Build the order simulator

---

## Phase 1 — Infrastructure & CDC Setup

### What I did

- **Docker Compose** with 5 services: source-db (Debezium's PostgreSQL image), analytics-db, Zookeeper, Kafka, Debezium Connect
- **Source DB schema**: customers, products, inventory, orders, order_items — all with `REPLICA IDENTITY FULL` so Debezium captures before/after state on updates
- **Seed data**: 10 customers, 15 products (Korean e-commerce items), random inventory levels
- **Connector registration script**: `scripts/register_connector.sh` — registers the Debezium connector via REST API, watches all 5 source tables
- **Order simulator** (`src/simulator.py`): generates realistic order lifecycles with burst and continuous modes

### Verification

Simulator burst of 5 orders:

```
ORDER #21 CREATED — 1 items, total ₩2,261,000
ORDER #22 CREATED — 1 items, total ₩45,900
ORDER #23 CREATED — 3 items, total ₩2,670,950
ORDER #24 CREATED — 4 items, total ₩1,341,510
ORDER #25 CREATED — 2 items, total ₩8,199,720
ORDER #21: CREATED → PAID
ORDER #24: CREATED → CANCELLED
ORDER #21: PAID → SHIPPED → DELIVERED
ORDER #25: PAID → SHIPPED → DELIVERED
```

Kafka topics auto-created by Debezium:

```
cdc.public.customers
cdc.public.inventory
cdc.public.order_items
cdc.public.orders
cdc.public.products
```

Sample event from `cdc.public.orders` (truncated):

```json
{
  "op": "u",
  "before": {"id": 1, "status": "CREATED", ...},
  "after": {"id": 1, "status": "PAID", ...},
  "source": {"table": "orders", "lsn": 27578208, "txId": 761}
}
```

Full chain confirmed: source DB write → WAL → Debezium → Kafka topic.

### What surprised me

- **Zookeeper health check failed**: the `nc` (netcat) command wasn't available in Debezium's Zookeeper image. Had to use bash's built-in `/dev/tcp/` instead. Took a couple tries to get right.
- **Decimal columns come as base64 in JSON**: Debezium encodes `DECIMAL` columns as base64 bytes by default. Added `"decimal.handling.mode": "string"` to the connector config to get readable numbers. This is a common gotcha.
- **Ambiguous column names in SQL UPDATE with JOIN**: `quantity` existed in both `inventory` and `order_items` tables. PostgreSQL requires explicit table aliases (`i.quantity`) in UPDATE...FROM joins.
- **Docker stack needs ~2-3 GB RAM**: Kafka + Zookeeper + Debezium Connect are heavy. Noticeably slower than Project 01's single PostgreSQL container.

### How I used AI

- Delegated: Docker Compose configuration, seed data generation, simulator boilerplate, connector registration script
- Decided myself: using Debezium's pre-configured PostgreSQL image (has `wal_level=logical` built in), setting `REPLICA IDENTITY FULL` on all tables, the order lifecycle probabilities (10% cancel, 5% refund), fixing the Zookeeper health check

### What to do next

- [x] Build the Python Kafka consumer
- [x] Implement event log (append-only storage)
- [x] Implement materialized snapshots
- [x] Handle idempotency and out-of-order events

---

## Phase 2 — Event Consumer & Processing

### What I did

- Built a Python Kafka consumer (`src/consumer/`) with 7 modules:
  - `config.py` — environment-based settings (Kafka, DB, batch size)
  - `db.py` — analytics DB connection helper
  - `event_log.py` — append-only event storage with UUID5-based dedup (built from table + LSN + txId + key)
  - `snapshots.py` — materialized snapshots for orders and inventory, using UPSERT
  - `metrics.py` — per-window metrics (events/sec, lag, out-of-order detection via per-table timestamp tracking)
  - `dead_letter.py` — failed events get stored instead of dropped
  - `runner.py` — main loop: poll Kafka → store event → update snapshot → record metrics → commit offset

- Consumer processes events in batches (commit every 10 events) and flushes metrics every 60 seconds
- Idempotency: `event_id` is a deterministic UUID5 hash. If the same event arrives twice, `ON CONFLICT DO NOTHING` skips it
- Out-of-order detection: `MetricsCollector` tracks the latest `source_ts` per table. If a new event has an older timestamp, it increments `out_of_order_count`

### Verification

Ran simulator burst of 20 orders, consumer processed everything:

```
events in event_log: 533
dead_letter_events: 0
```

Order snapshots (sample):

```
 order_id |  status   | total_amount | item_count
----------+-----------+--------------+------------
       26 | DELIVERED |   2713350.00 |          2
       24 | CANCELLED |   1341510.00 |          0
       27 | DELIVERED |   7555850.00 |          2
```

Inventory snapshots (sample):

```
 product_id |     product_name     | quantity | reserved | available
------------+----------------------+----------+----------+-----------
          8 | Organic Milk 1L      |      155 |        2 |       153
         11 | IKEA Desk Lamp       |      264 |        0 |       264
         14 | Sony WH-1000XM5      |      263 |        1 |       262
```

Processing metrics:

```
 events_processed | events_per_second | max_lag_ms | errors | out_of_order_count
              243 |              4.00 |        822 |      0 |                  0
```

All snapshots populated correctly. `available` column auto-computed as `quantity - reserved`. Zero errors, zero dead letters.

### What surprised me

- **First metrics window showed ~1.4 million ms lag** — that's because the consumer started by reading old messages from earlier testing (before the consumer existed). The second burst showed a normal 822ms max lag.
- **Orders 1-2 have NULL total_amount** — these were from the first test run before we added `decimal.handling.mode: "string"` to the connector. Old messages in Kafka still had base64-encoded decimals. Not a bug, just a consequence of the fix arriving after some data was already written.
- **The `available` GENERATED column is really convenient** — PostgreSQL computes `quantity - reserved` automatically. No consumer logic needed.

### How I used AI

- Delegated: consumer module boilerplate, dispatch table pattern, dead letter handler
- Decided myself: UUID5 dedup strategy, batch commit size (10), metrics window length (60s), which snapshot fields to track, error handling flow (rollback → dead letter → continue)

### What to do next

- [x] Verify snapshot consistency against source DB
- [x] Add unit tests for event processing
- [x] Build monitoring dashboard or CLI
- [x] Handle schema evolution

---

## Phase 3 — Monitoring & Observability

### What I did

- **Monitor CLI** (`src/monitor.py`): queries the analytics DB directly for pipeline status. Has subcommands (`events`, `metrics`, `orders`, `inventory`, `dead-letters`, `breakdown`) and a `--watch` mode that refreshes every 5 seconds. No extra infrastructure needed — reads from the tables we already built.

- **Consistency checker** (`scripts/verify_consistency.sh`): compares row counts and sample data between source DB and analytics snapshots. This is the Phase 2 exit proof.

- **Dead letter handler** (`src/consumer/dead_letter.py`): failed events go to `dead_letter_events` table with the error message. Consumer rolls back the main transaction, inserts the dead letter, then continues processing.

- **Schema evolution strategy** (ADR-006): since event_log uses JSONB, new columns in the source DB just show up as new JSON fields automatically. Snapshot tables use `dict.get()` with defaults so missing fields don't crash. Only need a migration if we want a new snapshot column.

- **Unit tests** (21 tests, all passing):
  - `test_event_log.py`: dedup determinism, different inputs → different IDs, missing fields, key ordering
  - `test_metrics.py`: lag calculation, out-of-order detection (per-table), windowing, reset
  - `test_snapshots.py`: decimal conversion edge cases (string, int, None, base64 garbage)

```
tests/test_event_log.py    6 passed
tests/test_metrics.py      8 passed
tests/test_snapshots.py    7 passed
Total: 21 passed in 0.07s
```

- **Streamlit dashboard** (`src/dashboard.py`): 5-page web UI showing pipeline health in real time. Uses `plotly.graph_objects` (not `plotly.express` — had compatibility issues with narwhals on Python 3.9). Pages: Pipeline Overview, Event Stream (with filters + lag histogram), Order Snapshots (status bar chart + revenue pie + lifecycle transitions), Inventory (stacked bar chart + low stock alerts), Performance Metrics (throughput + lag charts). Has auto-refresh toggle.

### What surprised me

- **plotly.express broke on Python 3.9** — newer plotly versions use a library called `narwhals` internally that passes arguments the older version doesn't support. Fix: switched to `plotly.graph_objects` and converted all pandas Series to plain Python lists with `.tolist()` before passing to plotly.

### How I used AI

- Delegated: monitor CLI layout, test boilerplate, dead letter module, dashboard layout
- Decided myself: CLI over Grafana (ADR-007 — no extra containers), test cases to write, schema evolution approach, go._ over px._ for Python 3.9 compatibility

### What to do next

- [x] README.md with full project explanation
- [x] Cost analysis
- [x] CDC vs polling comparison doc
- [x] Final journal retrospective

---

## Phase 4 — Polish & Packaging

### What I did

- **README.md**: Problem → Approach → Key Decisions → Learnings → Limitations → Quick Start → Project Structure
- **Cost analysis** (`docs/cost-analysis.md`): AWS estimate ~$94/month, GCP alternative ~$55/month, optimization ideas
- **CDC vs polling comparison** (`docs/cdc-vs-polling.md`): side-by-side table, example with order tracking, when to use which, interview talking points

---

## Retrospective

### What went well

- **CDC stack worked first try** (after fixing the Zookeeper health check). Docker Compose with 5 services is complex, but the Debezium images came pre-configured.
- **Event sourcing pattern clicked** once I saw it in action — the event_log is genuinely useful, not just a design pattern exercise. Being able to rebuild snapshots from raw events makes debugging easy.

### What was harder than expected

- **Debezium decimal encoding** (base64 surprise) — this took a while to debug. The events looked correct until I noticed `total_amount` was base64 gibberish. Production systems probably hit this all the time.
- **Docker RAM usage** — 2-3 GB for the stack means my laptop was noticeably slower. Had to close other apps.
- **plotly compatibility** — spent time debugging narwhals errors on Python 3.9. Not a CDC problem, but a reminder that library version conflicts are a real part of the job.

### What I'd do differently

- **Start with Confluent Cloud** instead of self-managed Kafka/Debezium. Would eliminate most Docker issues and let me focus on the consumer logic.
- **Add integration tests earlier** — unit tests cover the logic, but I should have written a test that runs the full pipeline (insert → CDC → consumer → verify snapshot) from the start.
- **Use KRaft mode** instead of Zookeeper — Kafka 3.x supports it and it's one fewer container.

### Key skills demonstrated

- CDC concepts: WAL, logical replication, Debezium event format
- Event sourcing: append-only log + materialized snapshots
- Stream processing: Kafka consumer with batched commits, lag tracking, dead letter queue
- Data quality: idempotent processing, out-of-order detection, consistency verification
- Infrastructure: Docker Compose orchestration, health checks, service dependencies
- Observability: processing metrics, CLI monitor, Streamlit dashboard
