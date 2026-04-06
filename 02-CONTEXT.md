# Project 02: CDC-Based Event Sourcing Pipeline

## Why This Project

Project 01 was a batch pipeline — collect data on a schedule, process it later. But most real companies need to react to changes immediately. When someone places an order, downstream systems (inventory, shipping, analytics) need to know right away, not on the next hourly poll.

CDC (Change Data Capture) solves this. Instead of asking "what changed?", it watches the database and streams every change as it happens. This is how companies like Coupang and Toss handle real-time data.

## What It Does

Simulates an e-commerce order system:

1. A **source database** holds orders, products, inventory, and customers
2. **Debezium** watches the database and publishes every row change to Kafka
3. A **Python consumer** reads those changes and builds an event log, current-state snapshots, and metrics
4. A **simulator** generates realistic order flows (create → pay → ship → deliver, with cancellations)
5. A **Streamlit dashboard** visualizes the pipeline in real time (events, orders, inventory, lag)

## Why This Stands Out

- Wanted to show awareness of event-driven systems via CDC.
- Event sourcing (keeping a full history of changes) is a real production pattern.
- The full stack (PostgreSQL → Debezium → Kafka → Python) runs in Docker.

## Tech Stack

- PostgreSQL 16 (source DB, with WAL-based replication)
- Debezium (CDC connector that reads the database log)
- Apache Kafka (message broker for streaming events)
- Python with confluent-kafka (event consumer)
- Streamlit + Plotly (real-time dashboard)
- Docker Compose (everything runs locally)
