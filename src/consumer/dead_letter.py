"""
Dead Letter Queue — stores events that failed processing.

When an event can't be processed (bad data, schema mismatch, etc.),
it goes here instead of being silently dropped. This lets us:
1. Not block the pipeline on one bad event
2. Investigate and replay failed events later
"""

import json
import logging

from consumer.event_log import build_event_id

logger = logging.getLogger(__name__)


def send_to_dead_letter(cursor, event: dict, kafka_meta: dict, error: Exception):
    """Store a failed event in the dead_letter_events table."""
    source = event.get("source", {})
    source_table = f"{source.get('schema', 'public')}.{source.get('table', '')}"
    record_key = kafka_meta.get("key", {})
    event_id = build_event_id(source, record_key)

    try:
        cursor.execute("""
            INSERT INTO dead_letter_events
                (event_id, source_table, raw_event, error_message)
            VALUES (%s, %s, %s, %s)
        """, (
            event_id,
            source_table,
            json.dumps(event),
            f"[{type(error).__name__}] {str(error)}",
        ))
        logger.warning("Event sent to dead letter: %s — %s", source_table, error)

    except Exception as e:
        # If even dead-lettering fails, just log it — don't crash the consumer
        logger.error("Failed to dead-letter event: %s", e)
