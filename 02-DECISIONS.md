# Architecture Decision Records (ADR)

> Every technical choice should have a "why."

---

### ADR-001: WAL-Based CDC over Polling or Triggers
- **Status**: Accepted
- **Context**: Need to capture row-level changes from a PostgreSQL source database.
- **Alternatives**:
  - Polling (periodic SELECT): simple but misses deletes, misses intermediate states between polls, adds load to the DB
  - DB triggers: captures changes in real-time but adds overhead to every write, couples pipeline to the source schema
  - WAL-based CDC (Debezium): reads the database log asynchronously, zero impact on write performance, captures everything including deletes
- **Decision**: WAL-based CDC with Debezium
- **Rationale**: Polling can't do event sourcing — if an order goes CREATED → PAID → SHIPPED between polls, we'd only see SHIPPED. Triggers are fragile and slow down the source DB. WAL-based CDC is the standard approach at production companies and captures every change without impacting the source.

### ADR-002: Kafka over RabbitMQ
- **Status**: Accepted
- **Context**: Debezium needs somewhere to publish change events.
- **Alternatives**:
  - Kafka: Debezium's native integration, durable log with replay capability, topic-per-table
  - RabbitMQ: lighter but no replay (messages disappear after consumption), not a natural fit for event sourcing
  - No broker (direct HTTP sink): simplest but loses events if consumer is down
- **Decision**: Apache Kafka
- **Rationale**: Kafka's log-based design matches event sourcing — we can replay the entire history from any point. RabbitMQ deletes messages after delivery, so we'd lose the ability to rebuild state. Kafka + Debezium is also the standard combo that interviewers expect.

### ADR-003: confluent-kafka over kafka-python
- **Status**: Accepted
- **Context**: Need a Python library to consume Kafka events.
- **Alternatives**:
  - confluent-kafka: C-based (fast), backed by Confluent, production-grade
  - kafka-python: pure Python, simpler but slower and less maintained
- **Decision**: confluent-kafka
- **Rationale**: Performance doesn't matter at our demo scale, but using the production-grade library shows awareness of real tooling. It's also what most companies actually use.

### ADR-004: JSONB Event Log over Normalized Tables
- **Status**: Accepted
- **Context**: How should we store change events in the analytics DB?
- **Alternatives**:
  - Single event_log table with JSONB columns: schema-agnostic, one INSERT per event, easy to add new tables
  - Separate typed tables per entity (order_events, inventory_events): type-safe, faster queries, but needs migration when source schema changes
- **Decision**: Single append-only event_log with JSONB, plus separate snapshot tables for current state
- **Rationale**: The event log should just store what happened — no interpretation. JSONB handles any source table without migrations. The snapshot tables (order_snapshots, inventory_snapshots) provide the structured views for querying. This is the standard event sourcing pattern: immutable log + derived views.

### ADR-005: E-Commerce Domain
- **Status**: Accepted
- **Context**: Need a domain that naturally produces interesting state changes for CDC.
- **Alternatives**:
  - E-commerce orders: rich state machine (create → pay → ship → deliver), touches multiple tables per action
  - Banking transactions: interesting but mostly INSERTs (less UPDATE/DELETE to showcase CDC)
  - IoT sensors: high volume but append-only, doesn't demonstrate CDC's strengths
- **Decision**: E-commerce order management
- **Rationale**: Orders have the most interesting change patterns — one order goes through 4+ status transitions, each captured as a separate event. It also touches multiple tables (orders + items + inventory), creating cross-table consistency challenges that are relevant for CDC.

### ADR-006: Schema Evolution Strategy — Log-Then-Adapt
- **Status**: Accepted
- **Context**: Source DB schemas change over time (new columns, renames, type changes). The consumer needs to handle events from before and after schema changes.
- **Decision**: The event_log stores raw JSONB from Debezium, so it never breaks on schema changes — new fields just appear in the JSON. Snapshot tables handle missing fields with `COALESCE` and default values. If a snapshot table needs a new column, we add it with `ALTER TABLE ... ADD COLUMN ... DEFAULT`.
- **Rationale**: Because event_log uses JSONB, it's naturally schema-agnostic. The snapshot layer is the only part that cares about specific fields, and it uses `dict.get()` with defaults in Python, so a missing field won't crash it. This is simpler than running a schema registry (like Confluent Schema Registry) which would be overkill for this project.
- **Trade-off**: No compile-time safety — a renamed column silently becomes NULL in the snapshot until we update the consumer code. Acceptable for this scale.

### ADR-007: CLI Monitor over Grafana Dashboard
- **Status**: Accepted
- **Context**: Need a way to view pipeline health (events/sec, lag, errors, snapshots).
- **Alternatives**:
  - Grafana + Prometheus: industry standard, pretty dashboards, but requires 2+ extra containers and lots of config
  - Streamlit: used in Project 01, but not a natural fit for ops monitoring
  - Python CLI: zero extra dependencies, reads directly from analytics DB, can run in watch mode
- **Decision**: Python CLI (`monitor.py`) with subcommands and `--watch` mode
- **Rationale**: The analytics DB already has a `processing_metrics` table. A CLI that queries it directly is the simplest path. No extra infrastructure, and it demonstrates that we built observability into the data model from the start (the metrics table was designed in Phase 0).

### ADR-008: Streamlit Dashboard (in addition to CLI)
- **Status**: Accepted
- **Context**: The CLI monitor works, but a visual dashboard is more impressive for a portfolio and easier for reviewers to understand at a glance.
- **Decision**: Added a Streamlit dashboard (`src/dashboard.py`) alongside the CLI. Uses `plotly.graph_objects` for charts.
- **Rationale**: Streamlit reads from the same analytics DB tables the CLI uses — no extra backend work. Dashboard shows event breakdowns, order lifecycle, inventory levels, and processing lag in a way that's immediately understandable. We kept the CLI too since it's useful for quick checks without opening a browser.
- **Trade-off**: Used `go.*` instead of `px.*` (plotly express) because of a narwhals compatibility bug on Python 3.9. Slightly more verbose code but works reliably.
