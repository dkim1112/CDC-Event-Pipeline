#!/bin/bash
# Quick peek at Kafka topics and recent messages
# Usage: bash scripts/peek_topics.sh [topic_name]

set -euo pipefail

KAFKA_CONTAINER="cdc-kafka"

echo "=== Kafka Topics ==="
docker exec $KAFKA_CONTAINER /kafka/bin/kafka-topics.sh \
    --bootstrap-server localhost:9092 --list

if [ -n "${1:-}" ]; then
    echo ""
    echo "=== Last 5 messages from $1 ==="
    docker exec $KAFKA_CONTAINER /kafka/bin/kafka-console-consumer.sh \
        --bootstrap-server localhost:9092 \
        --topic "$1" \
        --from-beginning \
        --max-messages 5 \
        --timeout-ms 5000 2>/dev/null || true
fi
