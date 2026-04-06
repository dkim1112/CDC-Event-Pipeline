"""
Order Simulator
===============
Generates realistic e-commerce order lifecycles against the source DB.
Each order goes through: CREATED → PAID → SHIPPED → DELIVERED
With some orders getting CANCELLED or REFUNDED.

Usage:
  python simulator.py                  # run continuously (~10 orders/min)
  python simulator.py --burst 50       # create 50 orders quickly, then process them
  python simulator.py --rate 5         # 5 orders per minute
"""

import argparse
import logging
import random
import time
from datetime import datetime
from decimal import Decimal

import psycopg2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Source DB connection
DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "dbname": "source_db",
    "user": "cdc_user",
    "password": "cdc_pass",
}

# Probabilities for order outcomes
CANCEL_RATE = 0.10      # 10% of orders get cancelled before payment
REFUND_RATE = 0.05      # 5% of paid orders get refunded

# Delays between state transitions (seconds)
MIN_DELAY = 1
MAX_DELAY = 5


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def get_random_customer(cur):
    cur.execute("SELECT id FROM customers ORDER BY random() LIMIT 1")
    row = cur.fetchone()
    return row[0] if row else None


def get_random_products(cur, count=None):
    """Pick 1-4 random products that are in stock."""
    if count is None:
        count = random.randint(1, 4)
    cur.execute("""
        SELECT p.id, p.base_price, i.quantity - i.reserved AS available
        FROM products p
        JOIN inventory i ON i.product_id = p.id
        WHERE i.quantity - i.reserved > 0
        ORDER BY random()
        LIMIT %s
    """, (count,))
    return cur.fetchall()


def create_order(conn):
    """Create a new order with items. Returns order_id."""
    cur = conn.cursor()

    customer_id = get_random_customer(cur)
    if not customer_id:
        logger.warning("No customers found")
        return None

    products = get_random_products(cur)
    if not products:
        logger.warning("No products in stock")
        return None

    # Create order
    cur.execute(
        "INSERT INTO orders (customer_id, status, total_amount) VALUES (%s, 'CREATED', 0) RETURNING id",
        (customer_id,),
    )
    order_id = cur.fetchone()[0]

    # Add items and calculate total
    total = Decimal("0")
    for product_id, base_price, available in products:
        qty = random.randint(1, min(3, available))
        # Small random price variation (sales/markups)
        unit_price = base_price * Decimal(str(round(random.uniform(0.9, 1.1), 2)))
        cur.execute(
            "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (%s, %s, %s, %s)",
            (order_id, product_id, qty, unit_price),
        )
        # Reserve inventory
        cur.execute(
            "UPDATE inventory SET reserved = reserved + %s, updated_at = NOW() WHERE product_id = %s",
            (qty, product_id),
        )
        total += unit_price * qty

    # Update order total
    cur.execute(
        "UPDATE orders SET total_amount = %s, updated_at = NOW() WHERE id = %s",
        (total, order_id),
    )

    conn.commit()
    logger.info("ORDER #%d CREATED — %d items, total ₩%s", order_id, len(products), f"{total:,.0f}")
    return order_id


def advance_order(conn, order_id):
    """Move an order to its next state. Returns the new status."""
    cur = conn.cursor()

    cur.execute("SELECT status FROM orders WHERE id = %s", (order_id,))
    row = cur.fetchone()
    if not row:
        return None
    current_status = row[0]

    # Decide next state
    if current_status == "CREATED":
        if random.random() < CANCEL_RATE:
            new_status = "CANCELLED"
        else:
            new_status = "PAID"
    elif current_status == "PAID":
        if random.random() < REFUND_RATE:
            new_status = "REFUNDED"
        else:
            new_status = "SHIPPED"
    elif current_status == "SHIPPED":
        new_status = "DELIVERED"
    else:
        # Terminal state
        return current_status

    cur.execute(
        "UPDATE orders SET status = %s, updated_at = NOW() WHERE id = %s",
        (new_status, order_id),
    )

    # Release inventory on cancellation/refund
    if new_status in ("CANCELLED", "REFUNDED"):
        cur.execute("""
            UPDATE inventory i
            SET reserved = i.reserved - oi.quantity, updated_at = NOW()
            FROM order_items oi
            WHERE oi.order_id = %s AND i.product_id = oi.product_id
        """, (order_id,))

    # Deduct inventory on shipment (reserved → actually shipped)
    if new_status == "SHIPPED":
        cur.execute("""
            UPDATE inventory i
            SET quantity = i.quantity - oi.quantity,
                reserved = i.reserved - oi.quantity,
                updated_at = NOW()
            FROM order_items oi
            WHERE oi.order_id = %s AND i.product_id = oi.product_id
        """, (order_id,))

    conn.commit()
    logger.info("ORDER #%d: %s → %s", order_id, current_status, new_status)
    return new_status


def restock_products(conn):
    """Occasionally restock low-inventory products."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE inventory
        SET quantity = quantity + 50 + (random() * 50)::int,
            updated_at = NOW()
        WHERE quantity - reserved < 10
        RETURNING product_id, quantity
    """)
    restocked = cur.fetchall()
    if restocked:
        conn.commit()
        logger.info("RESTOCK: %d products restocked", len(restocked))


def run_continuous(rate_per_min=10):
    """Run the simulator continuously."""
    conn = get_connection()
    delay = 60.0 / rate_per_min
    pending_orders = []  # Orders waiting to advance

    logger.info("Simulator started — %d orders/min", rate_per_min)

    try:
        while True:
            # Create a new order
            order_id = create_order(conn)
            if order_id:
                pending_orders.append(order_id)

            # Advance some pending orders
            still_pending = []
            for oid in pending_orders:
                if random.random() < 0.6:  # 60% chance to advance each cycle
                    status = advance_order(conn, oid)
                    if status not in ("DELIVERED", "CANCELLED", "REFUNDED"):
                        still_pending.append(oid)
                else:
                    still_pending.append(oid)
            pending_orders = still_pending

            # Occasional restock
            if random.random() < 0.1:
                restock_products(conn)

            time.sleep(delay)

    except KeyboardInterrupt:
        logger.info("Simulator stopped. %d orders still pending.", len(pending_orders))
    finally:
        conn.close()


def run_burst(count=50):
    """Create N orders quickly, then process them all through their lifecycle."""
    conn = get_connection()
    order_ids = []

    logger.info("Burst mode: creating %d orders...", count)
    for _ in range(count):
        oid = create_order(conn)
        if oid:
            order_ids.append(oid)
        time.sleep(0.1)  # Small delay so events are distinct

    logger.info("Created %d orders. Now advancing through lifecycle...", len(order_ids))

    # Process all orders through their lifecycle
    active = list(order_ids)
    while active:
        still_active = []
        for oid in active:
            status = advance_order(conn, oid)
            if status not in ("DELIVERED", "CANCELLED", "REFUNDED", None):
                still_active.append(oid)
            time.sleep(0.1)
        active = still_active
        if active:
            time.sleep(1)

    logger.info("Burst complete. All %d orders reached terminal state.", len(order_ids))
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="E-commerce order simulator")
    parser.add_argument("--burst", type=int, help="Create N orders in burst mode")
    parser.add_argument("--rate", type=int, default=10, help="Orders per minute (continuous mode)")
    args = parser.parse_args()

    if args.burst:
        run_burst(args.burst)
    else:
        run_continuous(args.rate)


if __name__ == "__main__":
    main()
