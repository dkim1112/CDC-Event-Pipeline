# CDC vs Polling: When to Use Which

This is the core "why" behind this project — and a common interview question for data engineering roles.

## The Comparison

| Factor | Polling (periodic SELECT) | CDC (WAL-based) |
|--------|--------------------------|-----------------|
| Intermediate states | Missed between polls | Every change captured |
| Deletes | Invisible (row is gone) | Captured as delete event |
| Source DB load | Query runs every cycle | Zero — reads the log |
| Latency | Depends on poll interval | Sub-second |
| Complexity | Simple (just SQL) | More infrastructure (Kafka, Debezium) |
| Infra cost | Low (just a cron job) | Higher (Kafka cluster needed) |
| Schema changes | Just update the query | Need to handle in consumer |
| Ordering | No guarantees | Per-partition ordering from Kafka |
| Replay | Can't replay past changes | Can replay from Kafka offset |

## Example: Order Tracking

Say an order goes through these states in 5 minutes:
```
12:00:00  CREATED
12:01:30  PAID
12:03:00  SHIPPED
12:04:45  DELIVERED
```

**With polling (every 5 min)**: you see one row — status = DELIVERED. You know the final state but not the journey.

**With CDC**: you get 4 events, one for each transition. You know exactly when each step happened. You can calculate time-to-ship, time-to-deliver, detect stuck orders.

## When Polling Is Fine

- Data changes infrequently (daily/weekly updates)
- You only need the latest state, not the history
- The source DB can handle the extra query load
- You don't have budget for Kafka infrastructure
- The team doesn't have Kafka experience

## When You Need CDC

- Order tracking, inventory management, fraud detection (need every state change)
- Analytics that depend on "how did we get here?" not just "where are we?"
- Multiple downstream consumers need the same changes (Kafka fan-out)
- Source DB is already under heavy load (CDC reads the log, not the tables)
- Regulatory requirements to audit every change

## What This Project Demonstrates

This project shows what polling CAN'T do:

1. **Event sourcing**: the event_log stores every change. We can rebuild any snapshot from scratch by replaying events.
2. **State machine tracking**: the order lifecycle (CREATED → PAID → SHIPPED → DELIVERED) is visible as individual events, not just the final state.
3. **Cross-table consistency**: when an order is created, we see both the order INSERT and the inventory UPDATE as separate events with the same transaction ID.
4. **Lag measurement**: we know exactly how long it took from source change to consumer processing (822ms in our tests).

None of this is possible with polling.

## Interview Talking Points

- "CDC reads the WAL, so there's zero impact on source DB performance"
- "Polling misses intermediate states — CDC captures every transition"
- "Kafka gives us replay capability, so we can rebuild derived tables without touching the source"
- "The trade-off is infrastructure complexity — CDC needs Kafka + Debezium, while polling is just a cron job"
- "For this project I chose CDC because the order state machine has 4+ transitions that would be invisible to polling"
