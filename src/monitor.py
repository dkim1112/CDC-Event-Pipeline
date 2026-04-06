#!/usr/bin/env python3
"""
Pipeline Monitor CLI — shows pipeline status at a glance.

Usage:
  python3 monitor.py              # full dashboard
  python3 monitor.py --watch      # auto-refresh every 5 seconds
  python3 monitor.py events       # recent events only
  python3 monitor.py metrics      # processing metrics only
  python3 monitor.py dead-letters # dead letter queue only
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone

import psycopg2

DB_CONFIG = {
    "host": os.getenv("ANALYTICS_DB_HOST", "localhost"),
    "port": int(os.getenv("ANALYTICS_DB_PORT", "5434")),
    "dbname": os.getenv("ANALYTICS_DB_NAME", "analytics_db"),
    "user": os.getenv("ANALYTICS_DB_USER", "analytics_user"),
    "password": os.getenv("ANALYTICS_DB_PASSWORD", "analytics_pass"),
}


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def query(conn, sql):
    cur = conn.cursor()
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    cur.close()
    return cols, rows


def print_table(title, cols, rows, max_rows=20):
    """Simple ASCII table printer."""
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")

    if not rows:
        print("  (no data)")
        return

    # Calculate column widths
    widths = [len(str(c)) for c in cols]
    for row in rows[:max_rows]:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val) if val is not None else "—"))

    # Header
    header = " | ".join(str(c).ljust(widths[i]) for i, c in enumerate(cols))
    print(f"  {header}")
    print(f"  {'-+-'.join('-' * w for w in widths)}")

    # Rows
    for row in rows[:max_rows]:
        line = " | ".join(
            str(val if val is not None else "—").ljust(widths[i])
            for i, val in enumerate(row)
        )
        print(f"  {line}")

    if len(rows) > max_rows:
        print(f"  ... and {len(rows) - max_rows} more rows")


def show_summary(conn):
    """Top-level pipeline health numbers."""
    cols, rows = query(conn, """
        SELECT
            (SELECT COUNT(*) FROM event_log) AS total_events,
            (SELECT COUNT(*) FROM order_snapshots) AS orders,
            (SELECT COUNT(*) FROM inventory_snapshots) AS inventory_items,
            (SELECT COUNT(*) FROM dead_letter_events) AS dead_letters,
            (SELECT COALESCE(SUM(errors), 0) FROM processing_metrics) AS total_errors
    """)
    print_table("Pipeline Summary", cols, rows)


def show_events(conn):
    """Most recent events."""
    cols, rows = query(conn, """
        SELECT id, source_table, operation,
               record_key::text AS key,
               source_ts,
               processed_at
        FROM event_log
        ORDER BY id DESC
        LIMIT 15
    """)
    print_table("Recent Events (last 15)", cols, rows)


def show_order_snapshots(conn):
    """Current order states."""
    cols, rows = query(conn, """
        SELECT order_id, customer_id, status, total_amount, item_count,
               last_updated_at
        FROM order_snapshots
        ORDER BY last_updated_at DESC NULLS LAST
        LIMIT 15
    """)
    print_table("Order Snapshots (latest 15)", cols, rows)


def show_inventory(conn):
    """Current inventory levels."""
    cols, rows = query(conn, """
        SELECT product_id, product_name, quantity, reserved, available,
               last_updated_at
        FROM inventory_snapshots
        ORDER BY product_id
    """)
    print_table("Inventory Snapshots", cols, rows)


def show_metrics(conn):
    """Processing performance metrics."""
    cols, rows = query(conn, """
        SELECT window_start::timestamp(0) AS window_start,
               events_processed AS events,
               events_per_second AS eps,
               max_lag_ms,
               avg_lag_ms,
               errors,
               out_of_order_count AS ooo
        FROM processing_metrics
        WHERE events_processed > 0
        ORDER BY window_start DESC
        LIMIT 10
    """)
    print_table("Processing Metrics (active windows)", cols, rows)


def show_dead_letters(conn):
    """Dead letter queue."""
    cols, rows = query(conn, """
        SELECT id, source_table, error_message,
               created_at::timestamp(0) AS created_at
        FROM dead_letter_events
        ORDER BY id DESC
        LIMIT 10
    """)
    print_table("Dead Letter Queue", cols, rows)


def show_event_breakdown(conn):
    """Events by table and operation."""
    cols, rows = query(conn, """
        SELECT source_table, operation,
               COUNT(*) AS count
        FROM event_log
        GROUP BY source_table, operation
        ORDER BY source_table, operation
    """)
    print_table("Events by Table & Operation", cols, rows)


def full_dashboard(conn):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n  CDC Pipeline Monitor — {now}")
    show_summary(conn)
    show_event_breakdown(conn)
    show_metrics(conn)
    show_order_snapshots(conn)
    show_inventory(conn)
    show_dead_letters(conn)


def main():
    parser = argparse.ArgumentParser(description="CDC Pipeline Monitor")
    parser.add_argument("view", nargs="?", default="all",
                        choices=["all", "events", "metrics", "orders",
                                 "inventory", "dead-letters", "breakdown"],
                        help="Which view to show (default: all)")
    parser.add_argument("--watch", "-w", action="store_true",
                        help="Auto-refresh every 5 seconds")
    args = parser.parse_args()

    view_map = {
        "all": full_dashboard,
        "events": lambda c: (show_summary(c), show_events(c)),
        "metrics": lambda c: (show_summary(c), show_metrics(c)),
        "orders": lambda c: show_order_snapshots(c),
        "inventory": lambda c: show_inventory(c),
        "dead-letters": lambda c: show_dead_letters(c),
        "breakdown": lambda c: show_event_breakdown(c),
    }

    try:
        while True:
            conn = get_conn()
            if args.watch:
                os.system("clear" if os.name != "nt" else "cls")

            view_map[args.view](conn)
            conn.close()

            if not args.watch:
                break
            print(f"\n  Refreshing in 5s... (Ctrl+C to stop)")
            time.sleep(5)

    except KeyboardInterrupt:
        print("\nStopped.")
    except psycopg2.OperationalError as e:
        print(f"Cannot connect to analytics DB: {e}")
        print("Make sure Docker containers are running.")
        sys.exit(1)


if __name__ == "__main__":
    main()
