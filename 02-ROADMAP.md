# Project 02: Roadmap

## Phase 0: Research & Design (Week 1)

> Understand CDC, Debezium, and Kafka before writing code.

### Tasks

- [x] Research CDC concepts: PostgreSQL WAL, Debezium event format, Kafka basics
- [x] Design source DB schema (customers, products, inventory, orders, order_items)
- [x] Design analytics DB schema (event_log, snapshots, metrics, dead letter)
- [x] Write initial ADRs (5 decisions)
- [x] Phase 0 exit: can explain the full data flow on a whiteboard

### Key Differentiator Checks

- [x] ⭐ Can explain "why CDC over polling?" with trade-offs (ADR-001)
- [x] ⭐ Event log design documented (ADR-004, SCHEMA-DESIGN.md)

---

## Phase 1: Infrastructure & CDC Setup (Week 2)

> Get the full stack running: source DB → Debezium → Kafka → visible events.

### Tasks

- [x] Docker Compose with 5 services (source-db, analytics-db, Zookeeper, Kafka, Debezium Connect)
- [x] Source DB schema + seed data (10 customers, 15 products, inventory)
- [x] Register Debezium connector, verify events in Kafka (5 topics auto-created)
- [x] Build order simulator (burst + continuous modes, realistic lifecycles)
- [x] Phase 1 exit: INSERT/UPDATE/DELETE in source DB → events visible in Kafka ✅

### Key Differentiator Checks

- [x] ⭐ Can trace what happens at each step (DB write → WAL → Debezium → Kafka)
- [x] ⭐ Simulator produces realistic patterns (state machine with cancel/refund probabilities)

---

## Phase 2: Event Consumer & Processing (Week 3)

> Build the consumer that turns CDC events into useful data.

### Tasks

- [x] Python Kafka consumer reading Debezium events
- [x] Event log (append-only storage with UUID5 dedup)
- [x] Materialized snapshots (order + inventory)
- [x] Idempotent processing (ON CONFLICT DO NOTHING)
- [x] Out-of-order event detection (per-table timestamp tracking)
- [x] Dead letter queue for failed events
- [x] Processing metrics (events/sec, lag, errors per 60s window)
- [x] Unit tests (21 passing)
- [x] Phase 2 exit: snapshots match source DB state ✅

### Key Differentiator Checks

- [x] ⭐ Out-of-order handling documented with rationale
- [x] ⭐ Snapshot consistency verified against source (verify_consistency.sh)

---

## Phase 3: Monitoring & Observability (Week 4)

> Make the pipeline observable and handle failures.

### Tasks

- [x] Consumer lag monitoring (tracked in processing_metrics table)
- [x] Dead letter queue for failed events (`dead_letter.py`)
- [x] Processing metrics (events/sec, lag, errors per 60s window)
- [x] Schema evolution handling (ADR-006: log-then-adapt strategy)
- [x] CLI for pipeline status (`monitor.py` with --watch mode)
- [x] Snapshot consistency checker (`scripts/verify_consistency.sh`)
- [x] Unit tests (21 tests: dedup, metrics, snapshots)
- [x] Streamlit dashboard (5 pages: overview, events, orders, inventory, performance)
- [x] Phase 3 exit: can detect and recover from common failures ✅

### Key Differentiator Checks

- [x] ⭐ Failure scenarios and recovery documented
- [x] ⭐ Schema evolution strategy in DECISIONS.md (ADR-006)

---

## Phase 4: Polish & Packaging (Week 5)

> Finish as a portfolio piece.

### Tasks

- [x] README.md (Problem → Approach → Learnings → Limitations → Quick Start)
- [x] Cost analysis (docs/cost-analysis.md — AWS ~$94/mo, GCP ~$55/mo)
- [x] CDC vs polling comparison doc (docs/cdc-vs-polling.md)
- [x] Finalize JOURNAL.md with retrospective
- [x] Quick Start guide in README (docker compose up → register → simulate → consume → dashboard)
- [x] Phase 4 exit: portfolio-ready ✅

### Key Differentiator Checks

- [x] ⭐ README conveys project depth
- [x] ⭐ 8 ADRs with rationale
- [x] ⭐ JOURNAL.md records failures and pivots
- [x] ⭐ CDC vs polling comparison included

---
