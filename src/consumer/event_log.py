"""
Event Log — append-only storage of all CDC events.

Every Debezium change event gets stored here as-is.
This is the single source of truth; all other tables
can be rebuilt from this log.
"""

import uuid
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def build_event_id(source: dict, record_key: dict) -> str:
    """
    Create a deterministic event_id for dedup.
    Based on: table + LSN + txId — unique per change in the WAL.
    """
    table = source.get("table", "")
    lsn = source.get("lsn", 0)
    tx_id = source.get("txId", 0)
    raw = f"{table}:{lsn}:{tx_id}:{json.dumps(record_key, sort_keys=True)}"
    return str(uuid.uuid5(uuid.NAMESPACE_OID, raw))


def store_event(cursor, event: dict, kafka_meta: dict) -> int | None:
    """
    Store a single Debezium event in the event_log.
    Returns the event_log.id on success, None if duplicate.
    """
    source = event.get("source", {})
    record_key = kafka_meta.get("key", {})
    event_id = build_event_id(source, record_key)

    source_ts_ms = source.get("ts_ms", 0)
    source_ts = datetime.fromtimestamp(source_ts_ms / 1000, tz=timezone.utc) if source_ts_ms else None

    kafka_ts_ms = event.get("ts_ms", 0)
    kafka_ts = datetime.fromtimestamp(kafka_ts_ms / 1000, tz=timezone.utc) if kafka_ts_ms else None

    try:
        cursor.execute("""
            INSERT INTO event_log
                (event_id, source_table, operation, record_key,
                 before_state, after_state, source_ts, kafka_ts,
                 kafka_topic, kafka_partition, kafka_offset,
                 source_lsn, source_txid)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (event_id) DO NOTHING
            RETURNING id
        """, (
            event_id,
            f"{source.get('schema', 'public')}.{source.get('table', '')}",
            event.get("op", "?"),
            json.dumps(record_key),
            json.dumps(event.get("before")) if event.get("before") else None,
            json.dumps(event.get("after")) if event.get("after") else None,
            source_ts,
            kafka_ts,
            kafka_meta.get("topic"),
            kafka_meta.get("partition"),
            kafka_meta.get("offset"),
            source.get("lsn"),
            source.get("txId"),
        ))

        row = cursor.fetchone()
        if row:
            return row[0]
        else:
            logger.debug("Duplicate event skipped: %s", event_id)
            return None

    except Exception as e:
        logger.error("Failed to store event: %s", e)
        raise
