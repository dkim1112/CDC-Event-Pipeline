"""
Configuration for the CDC consumer.
"""

import os

# Kafka
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_CONSUMER_GROUP = os.getenv("KAFKA_CONSUMER_GROUP", "cdc-consumer")
KAFKA_TOPIC_PREFIX = "cdc.public"

# Topics to subscribe to
TOPICS = [
    f"{KAFKA_TOPIC_PREFIX}.orders",
    f"{KAFKA_TOPIC_PREFIX}.order_items",
    f"{KAFKA_TOPIC_PREFIX}.inventory",
    f"{KAFKA_TOPIC_PREFIX}.customers",
    f"{KAFKA_TOPIC_PREFIX}.products",
]

# Analytics DB
ANALYTICS_DB = {
    "host": os.getenv("ANALYTICS_DB_HOST", "localhost"),
    "port": int(os.getenv("ANALYTICS_DB_PORT", "5434")),
    "dbname": os.getenv("ANALYTICS_DB_NAME", "analytics_db"),
    "user": os.getenv("ANALYTICS_DB_USER", "analytics_user"),
    "password": os.getenv("ANALYTICS_DB_PASSWORD", "analytics_pass"),
}

# Processing
COMMIT_BATCH_SIZE = 10       # Commit Kafka offset every N events
METRICS_WINDOW_SECONDS = 60  # Aggregate metrics per 1-minute window
