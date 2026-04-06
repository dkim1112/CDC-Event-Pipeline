#!/bin/bash
# Register the Debezium PostgreSQL connector
# Run after: docker compose up -d && wait for all services healthy

set -euo pipefail

CONNECT_URL="http://localhost:8083"

echo "Waiting for Debezium Connect to be ready..."
until curl -s "$CONNECT_URL/connectors" > /dev/null 2>&1; do
    echo "  Connect not ready yet, retrying in 3s..."
    sleep 3
done
echo "Connect is ready."

echo "Registering source-db connector..."
curl -s -X POST "$CONNECT_URL/connectors" \
    -H "Content-Type: application/json" \
    -d '{
    "name": "source-db-connector",
    "config": {
        "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
        "database.hostname": "source-db",
        "database.port": "5432",
        "database.user": "cdc_user",
        "database.password": "cdc_pass",
        "database.dbname": "source_db",
        "topic.prefix": "cdc",
        "table.include.list": "public.orders,public.order_items,public.inventory,public.customers,public.products",
        "plugin.name": "pgoutput",
        "publication.autocreate.mode": "filtered",
        "snapshot.mode": "initial",
        "heartbeat.interval.ms": "10000",
        "tombstones.on.delete": "true",
        "decimal.handling.mode": "string",
        "key.converter": "org.apache.kafka.connect.json.JsonConverter",
        "key.converter.schemas.enable": "false",
        "value.converter": "org.apache.kafka.connect.json.JsonConverter",
        "value.converter.schemas.enable": "false"
    }
}' | python3 -m json.tool

echo ""
echo "Connector registered. Check status:"
curl -s "$CONNECT_URL/connectors/source-db-connector/status" | python3 -m json.tool
