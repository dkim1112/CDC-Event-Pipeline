"""
CDC Pipeline Dashboard — real-time visualization of the event pipeline.

Run:  streamlit run src/dashboard.py
"""

import os
import time
import psycopg2
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ── DB connection ──

# Try Streamlit secrets first, then environment variables
try:
    import streamlit as st
    # More robust secrets check to avoid StreamlitSecretNotFoundError
    try:
        if hasattr(st, 'secrets') and hasattr(st.secrets, 'database'):
            DB_CONFIG = {
                "host": st.secrets.database.DB_HOST,
                "port": int(st.secrets.database.DB_PORT),
                "dbname": st.secrets.database.DB_NAME,
                "user": st.secrets.database.DB_USER,
                "password": st.secrets.database.DB_PASSWORD,
            }
        else:
            raise AttributeError("No secrets.database found")
    except (AttributeError, Exception):
        # Fallback to environment variables
        DB_CONFIG = {
            "host": os.getenv("ANALYTICS_DB_HOST", "localhost"),
            "port": int(os.getenv("ANALYTICS_DB_PORT", "5434")),
            "dbname": os.getenv("ANALYTICS_DB_NAME", "analytics_db"),
            "user": os.getenv("ANALYTICS_DB_USER", "analytics_user"),
            "password": os.getenv("ANALYTICS_DB_PASSWORD", "analytics_pass"),
        }
except ImportError:
    # Streamlit not available, use environment variables
    DB_CONFIG = {
        "host": os.getenv("ANALYTICS_DB_HOST", "localhost"),
        "port": int(os.getenv("ANALYTICS_DB_PORT", "5434")),
        "dbname": os.getenv("ANALYTICS_DB_NAME", "analytics_db"),
        "user": os.getenv("ANALYTICS_DB_USER", "analytics_user"),
        "password": os.getenv("ANALYTICS_DB_PASSWORD", "analytics_pass"),
    }


@st.cache_resource
def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def query(sql):
    """Run a query and return a DataFrame. Reconnects if needed."""
    try:
        conn = get_connection()
        return pd.read_sql(sql, conn)
    except Exception:
        st.cache_resource.clear()
        conn = get_connection()
        return pd.read_sql(sql, conn)


def col_to_list(df, col):
    """Convert a DataFrame column to a plain Python list (avoids plotly/narwhals bugs)."""
    return df[col].tolist()


# ── Page config ──

st.set_page_config(page_title="CDC Pipeline", page_icon="🔄", layout="wide")

st.sidebar.title("CDC Pipeline")
page = st.sidebar.radio("Navigate", [
    "Pipeline Overview",
    "Event Stream",
    "Order Snapshots",
    "Inventory",
    "Performance Metrics",
])

auto_refresh = st.sidebar.checkbox("Auto-refresh (10s)", value=False)


# ── Pipeline Overview ──

if page == "Pipeline Overview":
    st.title("Pipeline Overview")

    # Summary metrics
    summary = query("""
        SELECT
            (SELECT COUNT(*) FROM event_log) AS total_events,
            (SELECT COUNT(*) FROM order_snapshots) AS total_orders,
            (SELECT COUNT(*) FROM inventory_snapshots) AS inventory_items,
            (SELECT COUNT(*) FROM dead_letter_events) AS dead_letters,
            (SELECT COALESCE(SUM(errors), 0) FROM processing_metrics) AS total_errors
    """).iloc[0]

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total Events", f"{int(summary['total_events']):,}")
    c2.metric("Orders Tracked", int(summary['total_orders']))
    c3.metric("Inventory Items", int(summary['inventory_items']))
    c4.metric("Dead Letters", int(summary['dead_letters']))
    c5.metric("Total Errors", int(summary['total_errors']))

    st.markdown("---")

    # Events by table
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Events by Source Table")
        by_table = query("""
            SELECT source_table, COUNT(*) AS count
            FROM event_log
            GROUP BY source_table
            ORDER BY count DESC
        """)
        if not by_table.empty:
            fig = go.Figure(go.Bar(
                x=col_to_list(by_table, "source_table"),
                y=col_to_list(by_table, "count"),
                text=col_to_list(by_table, "count"),
                textposition="auto",
            ))
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Events by Operation")
        by_op = query("""
            SELECT
                CASE operation
                    WHEN 'c' THEN 'CREATE'
                    WHEN 'u' THEN 'UPDATE'
                    WHEN 'd' THEN 'DELETE'
                    WHEN 'r' THEN 'READ (snapshot)'
                END AS operation,
                COUNT(*) AS count
            FROM event_log
            GROUP BY operation
            ORDER BY count DESC
        """)
        if not by_op.empty:
            fig = go.Figure(go.Pie(
                labels=col_to_list(by_op, "operation"),
                values=col_to_list(by_op, "count"),
                hole=0.4,
            ))
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)

    # Pipeline flow diagram
    st.subheader("Data Flow")

    flow_col, desc_col = st.columns([1, 1])

    with flow_col:
        st.code(
            "Source DB (PostgreSQL)\n"
            "    | WAL (logical replication)\n"
            "    v\n"
            "Debezium (Kafka Connect)\n"
            "    | JSON events\n"
            "    v\n"
            "Kafka (5 topics)\n"
            "    | confluent-kafka consumer\n"
            "    v\n"
            "Python Consumer\n"
            "    +-- event_log (append-only, JSONB)\n"
            "    +-- order_snapshots (materialized)\n"
            "    +-- inventory_snapshots (materialized)\n"
            "    +-- processing_metrics (per-window)\n"
            "    +-- dead_letter_events (failures)",
            language=None
        )

    with desc_col:
        st.markdown(
            "데이터의 시작점: Source DB (PostgreSQL)\n"
            "* WAL (logical replication): 데이터베이스에서 일어나는 모든 삽입/수정/삭제 기록을 "
            "'로그(Log)' 형태로 실시간으로 내보냅니다. 원본 데이터를 직접 건드리지 않고 "
            "기록(WAL)만 읽어오기 때문에 DB에 부담이 적습니다.\n\n"
            "2\\. 변화를 감지하는 레이더: Debezium (Kafka Connect)\n"
            "* PostgreSQL의 WAL 로그를 실시간으로 읽어서 "
            "\"어느 테이블의 데이터가 어떻게 바뀌었는지\" 해석해 줍니다.\n"
            "* JSON events: 해석한 내용을 컴퓨터가 이해하기 쉬운 JSON 형식의 메시지로 변환합니다.\n\n"
            "3\\. 데이터 고속도로: Kafka (5 topics)\n"
            "* Debezium이 만든 메시지들을 주제별(Topic, 예: 주문, 재고 등)로 분류해서 안전하게 "
            "보관합니다. 데이터가 일시에 몰려도 병목 현상 없이 버텨주는 완충 지대 역할을 합니다.\n\n"
            "4\\. 핵심 처리 엔진: Python Consumer (confluent-kafka)\n"
            "Kafka 고속도로에서 데이터를 꺼내와서 실제로 우리가 쓸 수 있게 가공하는 단계입니다. "
            "그림 하단의 5가지 결과물이 여기서 만들어집니다.\n"
            "* event_log: 모든 변경 사항을 그대로 쌓아두는 '원본 로그' (나중에 문제 생기면 복구용)\n"
            "* order/inventory_snapshots: 실시간 변경 사항을 반영해 "
            "\"지금 현재 주문/재고 상태\"를 최신화해서 저장 (이게 대시보드의 숫자가 됩니다)\n"
            "* processing_metrics: 시스템이 잘 돌아가는지 성능 수치를 계산\n"
            "* dead_letter_events: 만약 처리 중 에러가 나면 따로 빼두어 나중에 확인 "
            "(아까 대시보드에서 0이었던 항목)"
        )


# ── Event Stream ──

elif page == "Event Stream":
    st.title("Event Stream")

    # Filters
    col1, col2, col3 = st.columns(3)
    tables = query("SELECT DISTINCT source_table FROM event_log ORDER BY source_table")
    table_options = ["All"] + tables["source_table"].tolist() if not tables.empty else ["All"]
    selected_table = col1.selectbox("Source Table", table_options)

    ops = {"All": None, "CREATE": "c", "UPDATE": "u", "DELETE": "d"}
    selected_op = col2.selectbox("Operation", list(ops.keys()))

    limit = col3.number_input("Show last N events", value=50, min_value=10, max_value=500)

    # Build query
    where = []
    if selected_table != "All":
        where.append(f"source_table = '{selected_table}'")
    if ops[selected_op]:
        where.append(f"operation = '{ops[selected_op]}'")

    where_clause = "WHERE " + " AND ".join(where) if where else ""

    events = query(f"""
        SELECT id, source_table, operation,
               record_key::text AS key,
               source_ts::timestamp AS source_ts,
               processed_at::timestamp AS processed_at,
               EXTRACT(EPOCH FROM (processed_at - source_ts)) * 1000 AS lag_ms
        FROM event_log
        {where_clause}
        ORDER BY id DESC
        LIMIT {int(limit)}
    """)

    if not events.empty:
        st.dataframe(events, use_container_width=True, height=500)

        # Lag distribution
        st.subheader("Processing Lag Distribution")
        lag_data = events[events["lag_ms"].notna() & (events["lag_ms"] > 0) & (events["lag_ms"] < 10000)]
        if not lag_data.empty:
            fig = go.Figure(go.Histogram(
                x=col_to_list(lag_data, "lag_ms"),
                nbinsx=30,
            ))
            fig.update_layout(height=300, xaxis_title="Lag (ms)", yaxis_title="Count")
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No events yet. Run the simulator to generate data.")

    # Event timeline
    st.subheader("Events Over Time")
    timeline = query(f"""
        SELECT date_trunc('second', source_ts)::timestamp AS ts,
               source_table, COUNT(*) AS count
        FROM event_log
        {where_clause}
        GROUP BY ts, source_table
        ORDER BY ts
    """)
    if not timeline.empty:
        fig = go.Figure()
        for table in timeline["source_table"].unique():
            t = timeline[timeline["source_table"] == table]
            fig.add_trace(go.Scatter(
                x=col_to_list(t, "ts"),
                y=col_to_list(t, "count"),
                name=table, mode="lines+markers",
            ))
        fig.update_layout(height=350, xaxis_title="Time", yaxis_title="Events")
        st.plotly_chart(fig, use_container_width=True)


# ── Order Snapshots ──

elif page == "Order Snapshots":
    st.title("Order Snapshots")

    orders = query("""
        SELECT order_id, customer_id, status, total_amount, item_count,
               created_at::timestamp AS created_at,
               last_updated_at::timestamp AS last_updated_at,
               snapshot_version
        FROM order_snapshots
        ORDER BY order_id DESC
    """)

    if not orders.empty:
        col1, col2 = st.columns(2)

        colors_map = {
            "CREATED": "#3498db", "PAID": "#f39c12", "SHIPPED": "#9b59b6",
            "DELIVERED": "#2ecc71", "CANCELLED": "#e74c3c", "REFUNDED": "#95a5a6",
        }

        with col1:
            st.subheader("Orders by Status")
            status_counts = orders["status"].value_counts().reset_index()
            status_counts.columns = ["status", "count"]
            bar_colors = [colors_map.get(s, "#bdc3c7") for s in status_counts["status"]]

            fig = go.Figure(go.Bar(
                x=col_to_list(status_counts, "status"),
                y=col_to_list(status_counts, "count"),
                marker_color=bar_colors,
                text=col_to_list(status_counts, "count"),
                textposition="auto",
            ))
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("Revenue by Status")
            revenue = orders.groupby("status")["total_amount"].sum().reset_index()
            revenue.columns = ["status", "revenue"]
            revenue = revenue[revenue["revenue"] > 0]
            if not revenue.empty:
                pie_colors = [colors_map.get(s, "#bdc3c7") for s in revenue["status"]]
                fig = go.Figure(go.Pie(
                    labels=col_to_list(revenue, "status"),
                    values=col_to_list(revenue, "revenue"),
                    hole=0.4,
                    marker=dict(colors=pie_colors),
                ))
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)

        # Order lifecycle transitions
        st.subheader("Order Lifecycle Flow")
        lifecycle = query("""
            SELECT
                e.before_state::json->>'status' AS from_status,
                e.after_state::json->>'status' AS to_status,
                COUNT(*) AS transitions
            FROM event_log e
            WHERE e.source_table = 'public.orders'
              AND e.operation = 'u'
              AND e.before_state IS NOT NULL
              AND e.after_state IS NOT NULL
            GROUP BY from_status, to_status
            ORDER BY transitions DESC
        """)
        if not lifecycle.empty:
            st.dataframe(lifecycle, use_container_width=True)

        # Full table
        st.subheader("All Orders")
        st.dataframe(orders, use_container_width=True, height=400)
    else:
        st.info("No order snapshots yet.")


# ── Inventory ──

elif page == "Inventory":
    st.title("Inventory Snapshots")

    inv = query("""
        SELECT product_id, product_name, quantity, reserved, available,
               last_updated_at::timestamp AS last_updated_at
        FROM inventory_snapshots
        ORDER BY product_id
    """)

    if not inv.empty:
        st.subheader("Stock Levels by Product")
        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="Available",
            x=col_to_list(inv, "product_name"),
            y=col_to_list(inv, "available"),
            marker_color="#2ecc71",
        ))
        fig.add_trace(go.Bar(
            name="Reserved",
            x=col_to_list(inv, "product_name"),
            y=col_to_list(inv, "reserved"),
            marker_color="#e74c3c",
        ))
        fig.update_layout(barmode="stack", height=400, xaxis_tickangle=-45)
        st.plotly_chart(fig, use_container_width=True)

        # Low stock alert
        low_stock = inv[inv["available"] < 50]
        if not low_stock.empty:
            st.warning(f"Low stock alert: {len(low_stock)} products below 50 units")
            st.dataframe(low_stock[["product_name", "quantity", "reserved", "available"]],
                         use_container_width=True)

        st.subheader("Full Inventory")
        st.dataframe(inv, use_container_width=True)
    else:
        st.info("No inventory snapshots yet.")


# ── Performance Metrics ──

elif page == "Performance Metrics":
    st.title("Processing Performance")

    metrics = query("""
        SELECT window_start::timestamp AS window_start,
               window_end::timestamp AS window_end,
               events_processed,
               events_per_second, max_lag_ms, avg_lag_ms,
               errors, out_of_order_count
        FROM processing_metrics
        ORDER BY window_start DESC
        LIMIT 60
    """)

    if not metrics.empty:
        latest = metrics.iloc[0]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Events/sec", f"{float(latest['events_per_second']):.1f}")
        c2.metric("Max Lag", f"{int(latest['max_lag_ms'])} ms")
        c3.metric("Errors", int(latest['errors']))
        c4.metric("Out-of-Order", int(latest['out_of_order_count']))

        st.markdown("---")

        active = metrics[metrics["events_processed"] > 0].sort_values("window_start")

        if not active.empty:
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Throughput (events/sec)")
                fig = go.Figure(go.Scatter(
                    x=col_to_list(active, "window_start"),
                    y=col_to_list(active, "events_per_second"),
                    mode="lines+markers",
                ))
                fig.update_layout(height=300)
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.subheader("Processing Lag (ms)")
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=col_to_list(active, "window_start"),
                    y=col_to_list(active, "max_lag_ms"),
                    name="Max Lag", mode="lines+markers", line=dict(color="#e74c3c"),
                ))
                fig.add_trace(go.Scatter(
                    x=col_to_list(active, "window_start"),
                    y=col_to_list(active, "avg_lag_ms"),
                    name="Avg Lag", mode="lines+markers", line=dict(color="#3498db"),
                ))
                fig.update_layout(height=300)
                st.plotly_chart(fig, use_container_width=True)

        # Error history
        error_windows = metrics[metrics["errors"] > 0]
        if not error_windows.empty:
            st.subheader("Windows with Errors")
            st.dataframe(error_windows, use_container_width=True)
        else:
            st.success("No errors recorded in any processing window.")

        # Dead letter queue
        st.subheader("Dead Letter Queue")
        dead = query("SELECT * FROM dead_letter_events ORDER BY id DESC LIMIT 10")
        if not dead.empty:
            st.dataframe(dead, use_container_width=True)
        else:
            st.success("Dead letter queue is empty — all events processed successfully.")

        # Full metrics table
        st.subheader("All Metrics Windows")
        st.dataframe(metrics, use_container_width=True, height=300)
    else:
        st.info("No metrics yet. Start the consumer and simulator.")


# ── Auto-refresh ──

if auto_refresh:
    time.sleep(10)
    st.rerun()
