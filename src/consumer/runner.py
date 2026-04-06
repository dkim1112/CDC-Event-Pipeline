"""
Consumer Runner — the main loop that ties everything together.

Flow for each Kafka message:
  1. Deserialize the Debezium event
  2. Store in event_log (append-only, with dedup)
  3. Update the appropriate materialized snapshot
  4. Record metrics
  5. On failure → dead letter queue
  6. Commit Kafka offset every N events
"""

import json
import signal
import logging
import sys
from datetime import datetime, timezone

from confluent_kafka import Consumer, KafkaError, KafkaException

from consumer.config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_CONSUMER_GROUP,
    TOPICS,
    COMMIT_BATCH_SIZE,
)
from consumer.db import get_connection
from consumer.event_log import store_event
from consumer.snapshots import (
    update_order_snapshot,
    update_order_item_count,
    update_inventory_snapshot,
    update_product_name_on_inventory,
)
from consumer.metrics import MetricsCollector
from consumer.dead_letter import send_to_dead_letter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ── Dispatch table: maps source table → snapshot update function(s) ──

SNAPSHOT_HANDLERS = {
    "public.orders": [update_order_snapshot],
    "public.order_items": [update_order_item_count],
    "public.inventory": [update_inventory_snapshot],
    "public.products": [update_product_name_on_inventory],
    "public.customers": [],  # logged but no snapshot needed
}


class CDCConsumer:
    """Kafka consumer that processes Debezium CDC events."""

    def __init__(self):
        self.running = True
        self.conn = None
        self.kafka_consumer = None
        self.metrics = MetricsCollector()
        self.events_since_commit = 0

    def start(self):
        """Connect to Kafka and DB, then enter the main loop."""
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        logger.info("Connecting to analytics DB...")
        self.conn = get_connection()
        self.conn.autocommit = False

        logger.info("Connecting to Kafka at %s...", KAFKA_BOOTSTRAP_SERVERS)
        self.kafka_consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
            "group.id": KAFKA_CONSUMER_GROUP,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        })
        self.kafka_consumer.subscribe(TOPICS)
        logger.info("Subscribed to topics: %s", TOPICS)

        try:
            self._run_loop()
        finally:
            self._cleanup()

    def _run_loop(self):
        """Poll Kafka and process events until shutdown."""
        while self.running:
            msg = self.kafka_consumer.poll(timeout=1.0)

            if msg is None:
                # No message — check if we should flush metrics
                if self.metrics.should_flush():
                    self._flush_metrics()
                continue

            if msg.error():
                self._handle_kafka_error(msg.error())
                continue

            self._process_message(msg)

            # Periodic commits and metric flushes
            if self.events_since_commit >= COMMIT_BATCH_SIZE:
                self._commit()

            if self.metrics.should_flush():
                self._flush_metrics()

    def _process_message(self, msg):
        """Process a single Kafka message through the full pipeline."""
        processed_at = datetime.now(timezone.utc)

        try:
            # 1. Deserialize
            value = json.loads(msg.value().decode("utf-8"))
            key = json.loads(msg.key().decode("utf-8")) if msg.key() else {}

            kafka_meta = {
                "topic": msg.topic(),
                "partition": msg.partition(),
                "offset": msg.offset(),
                "key": key,
            }

            source = value.get("source", {})
            source_table = f"{source.get('schema', 'public')}.{source.get('table', '')}"

            cursor = self.conn.cursor()

            # 2. Store in event log (dedup handled inside)
            event_log_id = store_event(cursor, value, kafka_meta)

            if event_log_id is None:
                # Duplicate — skip snapshot update, still commit
                self.conn.commit()
                cursor.close()
                self.events_since_commit += 1
                return

            # 3. Update snapshot(s)
            handlers = SNAPSHOT_HANDLERS.get(source_table, [])
            for handler in handlers:
                # Some handlers need event_log_id, some don't
                if handler in (update_order_snapshot, update_inventory_snapshot):
                    handler(cursor, value, event_log_id)
                else:
                    handler(cursor, value)

            # 4. Commit DB transaction
            self.conn.commit()
            cursor.close()

            # 5. Record metrics
            source_ts_ms = source.get("ts_ms", 0)
            source_ts = (
                datetime.fromtimestamp(source_ts_ms / 1000, tz=timezone.utc)
                if source_ts_ms else None
            )
            self.metrics.record_event(source_table, source_ts, processed_at)
            self.events_since_commit += 1

            logger.debug("Processed: %s op=%s offset=%d", source_table, value.get("op"), msg.offset())

        except Exception as e:
            logger.error("Error processing message at offset %d: %s", msg.offset(), e)
            self.conn.rollback()
            self.metrics.record_error()

            # Send to dead letter queue
            try:
                cursor = self.conn.cursor()
                send_to_dead_letter(cursor, value, kafka_meta, e)
                self.conn.commit()
                cursor.close()
            except Exception:
                logger.error("Dead letter insert also failed — rolling back")
                self.conn.rollback()

            self.events_since_commit += 1

    def _commit(self):
        """Commit Kafka offsets."""
        try:
            self.kafka_consumer.commit(asynchronous=False)
            self.events_since_commit = 0
        except KafkaException as e:
            logger.error("Kafka commit failed: %s", e)

    def _flush_metrics(self):
        """Write metrics window to DB."""
        try:
            cursor = self.conn.cursor()
            self.metrics.flush(cursor)
            self.conn.commit()
            cursor.close()
        except Exception as e:
            logger.error("Metrics flush failed: %s", e)
            self.conn.rollback()

    def _handle_kafka_error(self, error):
        if error.code() == KafkaError._PARTITION_EOF:
            logger.debug("Reached end of partition")
        else:
            logger.error("Kafka error: %s", error)

    def _shutdown(self, signum, frame):
        logger.info("Shutdown signal received — finishing up...")
        self.running = False

    def _cleanup(self):
        logger.info("Cleaning up...")
        if self.kafka_consumer:
            # Commit any remaining offsets
            try:
                self.kafka_consumer.commit(asynchronous=False)
            except Exception:
                pass
            self.kafka_consumer.close()
        if self.conn:
            # Flush final metrics
            try:
                cursor = self.conn.cursor()
                self.metrics.flush(cursor)
                self.conn.commit()
                cursor.close()
            except Exception:
                pass
            self.conn.close()
        logger.info("Consumer stopped.")


def main():
    consumer = CDCConsumer()
    consumer.start()


if __name__ == "__main__":
    main()
