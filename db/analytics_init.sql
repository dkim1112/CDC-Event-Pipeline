-- Analytics DB schema: event-sourced tables
-- Consumer writes here; everything is append-only except snapshots

CREATE TABLE event_log (
    id              BIGSERIAL PRIMARY KEY,
    event_id        UUID UNIQUE NOT NULL,
    source_table    VARCHAR(50) NOT NULL,
    operation       CHAR(1) NOT NULL,       -- c, u, d, r
    record_key      JSONB NOT NULL,
    before_state    JSONB,
    after_state     JSONB,
    source_ts       TIMESTAMPTZ NOT NULL,
    kafka_ts        TIMESTAMPTZ,
    processed_at    TIMESTAMPTZ DEFAULT NOW(),
    kafka_topic     VARCHAR(100),
    kafka_partition INTEGER,
    kafka_offset    BIGINT,
    source_lsn      BIGINT,
    source_txid     BIGINT
);

CREATE INDEX idx_event_log_table_ts ON event_log(source_table, source_ts);
CREATE INDEX idx_event_log_kafka ON event_log(kafka_topic, kafka_partition, kafka_offset);

CREATE TABLE order_snapshots (
    order_id        INTEGER PRIMARY KEY,
    customer_id     INTEGER,
    status          VARCHAR(20),
    total_amount    DECIMAL(12,2),
    item_count      INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ,
    last_updated_at TIMESTAMPTZ,
    snapshot_version BIGINT,
    computed_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE inventory_snapshots (
    product_id      INTEGER PRIMARY KEY,
    product_name    VARCHAR(200),
    quantity        INTEGER,
    reserved        INTEGER,
    available       INTEGER GENERATED ALWAYS AS (quantity - reserved) STORED,
    last_updated_at TIMESTAMPTZ,
    snapshot_version BIGINT,
    computed_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE processing_metrics (
    id                  BIGSERIAL PRIMARY KEY,
    window_start        TIMESTAMPTZ NOT NULL,
    window_end          TIMESTAMPTZ NOT NULL,
    events_processed    INTEGER DEFAULT 0,
    events_per_second   DECIMAL(10,2),
    max_lag_ms          INTEGER,
    avg_lag_ms          INTEGER,
    errors              INTEGER DEFAULT 0,
    out_of_order_count  INTEGER DEFAULT 0
);

CREATE TABLE dead_letter_events (
    id              BIGSERIAL PRIMARY KEY,
    event_id        UUID,
    source_table    VARCHAR(50),
    raw_event       JSONB NOT NULL,
    error_message   TEXT NOT NULL,
    retry_count     INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);
