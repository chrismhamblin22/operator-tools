from __future__ import annotations
import os
import json
import uuid
import sqlite3
import streamlit as st
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

DATA_DIR = Path(os.environ.get("DATA_DIR", "."))
DB_PATH  = DATA_DIR / "tasks.db"

SECTIONS = {
    "inbox":    "📥 Landing Zone",
    "priority": "⚡ Priority Actions",
    "chase":    "🔍 Chase This Week",
    "waiting":  "⏳ Waiting",
}

TOPICS = ["", "CRO", "People", "Strategy", "Hiring", "Finance", "Marketing", "Ops", "Other"]

TOPIC_COLORS = {
    "CRO":       "#6366F1",
    "People":    "#10B981",
    "Strategy":  "#EF4444",
    "Hiring":    "#F59E0B",
    "Finance":   "#8B5CF6",
    "Marketing": "#EC4899",
    "Ops":       "#06B6D4",
    "Other":     "#9CA3AF",
}

# ── Database ──────────────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id         TEXT PRIMARY KEY,
                title      TEXT NOT NULL,
                notes      TEXT DEFAULT '',
                topic      TEXT DEFAULT '',
                section    TEXT NOT NULL,
                priority   INTEGER DEFAULT 0,
                done       INTEGER DEFAULT 0,
                created_at TEXT,
                done_at    TEXT
            )
        """)
        conn.commit()
    _migrate_from_json()


def _migrate_from_json() -> None:
    """One-time import of tasks.json into SQLite if it exists."""
    json_file = Path("tasks.json")
    if not json_file.exists():
        return
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        if count > 0:
            return  # already migrated
        tasks = json.loads(json_file.read_text())
        for t in tasks:
            conn.execute("""
                INSERT OR IGNORE INTO tasks
                    (id, title, notes, topic, section, priority, done, created_at, done_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                t.get("id"), t.get("title"), t.get("notes", ""),
                t.get("topic", ""), t.get("section"), t.get("priority", 0),
                1 if t.get("done") else 0,
                t.get("created_at"), t.get("done_at"),
            ))
        conn.commit()
    json_file.rename("tasks.json.bak")


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["done"] = bool(d["done"])
    return d

# ── Data layer ────────────────────────────────────────────────────────────────

def load() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM tasks ORDER BY created_at").fetchall()
    return [_row_to_dict(r) for r in rows]


def section_tasks(section: str) -> list[dict]:
    order = "priority ASC" if section == "priority" else "created_at ASC"
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT * FROM tasks WHERE section=? AND done=0 ORDER BY {order}",
            (section,),
        ).fetchall()
    return [_row_to_dict(r) for r in rows]

# ── Mutations ─────────────────────────────────────────────────────────────────

def add_task(title: str, notes: str, topic: str, section: str, priority_pos: int | None = None) -> None:
    with get_db() as conn:
        active = conn.execute(
            "SELECT id FROM tasks WHERE section='priority' AND done=0 ORDER BY priority"
        ).fetchall()
        ids = [r["id"] for r in active]
        n   = len(ids)

        if section == "priority" and priority_pos is not None:
            new_idx = max(0, min(priority_pos - 1, n))
            ids.insert(new_idx, "__new__")
            for pos, tid in enumerate(ids):
                if tid != "__new__":
                    conn.execute("UPDATE tasks SET priority=? WHERE id=?", (pos, tid))
            new_priority = ids.index("__new__")
        else:
            new_priority = n

        conn.execute("""
            INSERT INTO tasks (id, title, notes, topic, section, priority, done, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?)
        """, (
            str(uuid.uuid4()), title.strip(), notes.strip(), topic,
            section, new_priority, datetime.now().isoformat(),
        ))
        conn.commit()


def move_task(task_id: str, new_section: str) -> None:
    with get_db() as conn:
        if new_section == "priority":
            n = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE section='priority' AND done=0"
            ).fetchone()[0]
            conn.execute(
                "UPDATE tasks SET section=?, priority=? WHERE id=?",
                (new_section, n, task_id),
            )
        else:
            conn.execute("UPDATE tasks SET section=? WHERE id=?", (new_section, task_id))
        conn.commit()


def mark_done(task_id: str) -> None:
    with get_db() as conn:
        conn.execute(
            "UPDATE tasks SET done=1, done_at=? WHERE id=?",
            (datetime.now().isoformat(), task_id),
        )
        conn.commit()


def delete_task(task_id: str) -> None:
    with get_db() as conn:
        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        conn.commit()


def set_priority(task_id: str, new_pos: int) -> None:
    with get_db() as conn:
        active = conn.execute(
            "SELECT id FROM tasks WHERE section='priority' AND done=0 ORDER BY priority"
        ).fetchall()
        ids = [r["id"] for r in active]
        try:
            i = ids.index(task_id)
        except ValueError:
            return
        new_idx = max(0, min(new_pos - 1, len(ids) - 1))
        ids.pop(i)
        ids.insert(new_idx, task_id)
        for pos, tid in enumerate(ids):
            conn.execute("UPDATE tasks SET priority=? WHERE id=?", (pos, tid))
        conn.commit()

# ── Render helpers ────────────────────────────────────────────────────────────

def badge_html(topic: str) -> str:
    color = TOPIC_COLORS.get(topic, "#9CA3AF")
    return (
        f'<span style="background:{color};color:#fff;padding:2px 9px;'
        f'border-radius:12px;font-size:0.7rem;font-weight:700;'
        f'letter-spacing:0.04em;vertical-align:middle">{topic}</span>'
    )


def render_task(task: dict, section: str, idx: int, total: int) -> None:
    tid   = task["id"]
    topic = task.get("topic", "")

    title_md = f"**{task['title']}**"
    if topic:
        title_md += f"&nbsp;&nbsp;{badge_html(topic)}"
    st.markdown(title_md, unsafe_allow_html=True)

    if task.get("notes"):
        st.caption(task["notes"])

    if section == "priority":
        num_col, move_col, done_col, del_col = st.columns([1, 4, 1, 1])
        with num_col:
            st.number_input(
                "#",
                min_value=1,
                max_value=total,
                value=idx + 1,
                step=1,
                key=f"pri_{tid}",
                on_change=lambda: set_priority(tid, st.session_state[f"pri_{tid}"]),
                label_visibility="collapsed",
            )
    else:
        move_col, done_col, del_col = st.columns([6, 1, 1])

    with move_col:
        options = [k for k in SECTIONS if k != section]
        dest = st.selectbox(
            "move",
            [""] + options,
            format_func=lambda x: "Move to…" if x == "" else SECTIONS[x],
            key=f"mv_{tid}",
            label_visibility="collapsed",
        )
        if dest:
            move_task(tid, dest)
            st.rerun()

    with done_col:
        if st.button("✓", key=f"done_{tid}", help="Mark complete", type="primary"):
            mark_done(tid)
            st.rerun()

    with del_col:
        if st.button("✕", key=f"del_{tid}", help="Delete task"):
            delete_task(tid)
            st.rerun()

    st.divider()

# ── Dashboard ─────────────────────────────────────────────────────────────────

def render_dashboard() -> None:
    import pandas as pd
    import altair as alt

    tasks = load()
    if not tasks:
        st.markdown(
            '<p style="color:#94A3B8;padding:3rem 0;text-align:center">No data yet.</p>',
            unsafe_allow_html=True,
        )
        return

    now = datetime.now()
    df  = pd.DataFrame(tasks)
    df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
    df["done_at"]    = pd.to_datetime(df["done_at"],    errors="coerce")
    df["topic"]      = df["topic"].fillna("").replace("", "Untagged")
    df["age_days"]   = (now - df["created_at"].dt.tz_localize(None)).dt.total_seconds() / 86400

    done_df   = df[df["done"] == True].copy()
    active_df = df[df["done"] == False].copy()

    if not done_df.empty:
        done_df["days_to_complete"] = (
            done_df["done_at"].dt.tz_localize(None) - done_df["created_at"].dt.tz_localize(None)
        ).dt.total_seconds() / 86400

    # ── Top metrics ───────────────────────────────────────────────────────────
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("Total tasks", len(df))
    with m2:
        st.metric("Completed", len(done_df))
    with m3:
        rate = f"{100 * len(done_df) / len(df):.0f}%" if len(df) else "—"
        st.metric("Completion rate", rate)
    with m4:
        if not done_df.empty and "days_to_complete" in done_df and done_df["days_to_complete"].notna().any():
            st.metric("Avg days to complete", f"{done_df['days_to_complete'].mean():.1f}d")
        else:
            st.metric("Avg days to complete", "—")
    with m5:
        if not active_df.empty:
            st.metric("Avg active task age", f"{active_df['age_days'].mean():.1f}d")
        else:
            st.metric("Avg active task age", "—")

    st.markdown("---")
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("**Completed per day** (last 30 days)")
        if not done_df.empty and done_df["done_at"].notna().any():
            daily = (
                done_df.dropna(subset=["done_at"])
                .assign(day=lambda d: d["done_at"].dt.tz_localize(None).dt.date)
                .groupby("day").size().reset_index(name="count")
            )
            daily["day"] = pd.to_datetime(daily["day"])
            cutoff = pd.Timestamp(now.date()) - pd.Timedelta(days=30)
            daily  = daily[daily["day"] >= cutoff]
            if not daily.empty:
                st.altair_chart(
                    alt.Chart(daily)
                    .mark_bar(color="#6366F1", cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                    .encode(
                        x=alt.X("day:T", title=None, axis=alt.Axis(format="%b %d", labelAngle=-45)),
                        y=alt.Y("count:Q", title="Tasks", axis=alt.Axis(tickMinStep=1)),
                        tooltip=[alt.Tooltip("day:T", format="%b %d"), "count:Q"],
                    ).properties(height=220),
                    use_container_width=True,
                )
            else:
                st.caption("No completions in last 30 days.")
        else:
            st.caption("No completed tasks yet.")

    with col_right:
        st.markdown("**Tasks by topic**")
        by_topic = (
            df.groupby("topic")
            .agg(total=("id", "count"), done=("done", "sum"))
            .reset_index()
        )
        by_topic["active"] = by_topic["total"] - by_topic["done"]
        melted = by_topic.melt(id_vars="topic", value_vars=["active", "done"], var_name="status", value_name="count")
        st.altair_chart(
            alt.Chart(melted)
            .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("count:Q", title="Tasks", axis=alt.Axis(tickMinStep=1)),
                y=alt.Y("topic:N", sort="-x", title=None),
                color=alt.Color("status:N",
                    scale=alt.Scale(domain=["active", "done"], range=["#6366F1", "#10B981"]),
                    legend=alt.Legend(title=None)),
                tooltip=["topic:N", "status:N", "count:Q"],
            ).properties(height=220),
            use_container_width=True,
        )

    col_left2, col_right2 = st.columns(2)

    with col_left2:
        st.markdown("**Avg days to complete by topic**")
        if not done_df.empty and "days_to_complete" in done_df and done_df["days_to_complete"].notna().any():
            avg_by_topic = (
                done_df.dropna(subset=["days_to_complete"])
                .groupby("topic")["days_to_complete"].mean()
                .reset_index().rename(columns={"days_to_complete": "avg_days"})
                .sort_values("avg_days", ascending=False)
            )
            st.altair_chart(
                alt.Chart(avg_by_topic)
                .mark_bar(color="#F59E0B", cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                .encode(
                    x=alt.X("avg_days:Q", title="Days"),
                    y=alt.Y("topic:N", sort="-x", title=None),
                    tooltip=["topic:N", alt.Tooltip("avg_days:Q", format=".1f")],
                ).properties(height=220),
                use_container_width=True,
            )
        else:
            st.caption("No completion data yet.")

    with col_right2:
        st.markdown("**Active tasks by section**")
        if not active_df.empty:
            by_section = active_df.groupby("section").size().reset_index(name="count")
            by_section["label"] = by_section["section"].map(
                lambda s: SECTIONS.get(s, s).split(" ", 1)[1]
            )
            st.altair_chart(
                alt.Chart(by_section)
                .mark_bar(color="#06B6D4", cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                .encode(
                    x=alt.X("count:Q", title="Tasks", axis=alt.Axis(tickMinStep=1)),
                    y=alt.Y("label:N", sort="-x", title=None),
                    tooltip=["label:N", "count:Q"],
                ).properties(height=220),
                use_container_width=True,
            )
        else:
            st.caption("No active tasks.")

    st.markdown("---")
    st.markdown("**Oldest active tasks**")
    if not active_df.empty:
        oldest = (
            active_df[["title", "topic", "section", "age_days"]]
            .sort_values("age_days", ascending=False).head(10).copy()
        )
        oldest["section"] = oldest["section"].map(lambda s: SECTIONS.get(s, s).split(" ", 1)[1])
        oldest["age_days"] = oldest["age_days"].map(lambda x: f"{x:.1f}d")
        oldest.columns = ["Title", "Topic", "Section", "Age"]
        st.dataframe(oldest, use_container_width=True, hide_index=True)

# ── App ───────────────────────────────────────────────────────────────────────

def main():
    init_db()

    st.set_page_config(
        page_title="Daily Work",
        page_icon="✅",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown("""
    <style>
    .stApp { background: #F8FAFC; }
    section[data-testid="stSidebar"] { background: #1E293B !important; }
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stMarkdown { color: #CBD5E1 !important; }
    section[data-testid="stSidebar"] h2 { color: #F1F5F9 !important; }
    .block-container { padding-top: 1.5rem !important; max-width: 1100px; }
    .stTabs [data-baseweb="tab"] { font-weight: 600; font-size: 0.85rem; }
    .stTabs [data-baseweb="tab-highlight"] { background: #6366F1; }
    div[data-testid="stVerticalBlock"] > div.element-container { margin-bottom: 0.1rem; }
    hr { margin: 0.5rem 0 !important; }
    [data-testid="stMetricValue"] { font-size: 1.6rem !important; }
    </style>
    """, unsafe_allow_html=True)

    # ── Sidebar ────────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("## Add Task")
        st.divider()

        with st.form("add_task_form", clear_on_submit=True):
            title = st.text_input("Title", placeholder="What needs to happen?")
            notes = st.text_area("Notes", placeholder="Context, links, details…", height=80)
            topic = st.selectbox("Topic", TOPICS)
            dest  = st.selectbox("Add to", list(SECTIONS.keys()), format_func=lambda x: SECTIONS[x])
            n_priority = len(section_tasks("priority"))
            pri_pos = st.number_input(
                "Priority position",
                min_value=1,
                max_value=max(n_priority + 1, 1),
                value=n_priority + 1,
                step=1,
                help="Where to insert in Priority Actions (ignored for other sections)",
            )
            submitted = st.form_submit_button("＋ Add Task", use_container_width=True, type="primary")
            if submitted:
                if title.strip():
                    add_task(title, notes, topic, dest, priority_pos=int(pri_pos))
                    st.success("Task added!")
                    st.rerun()
                else:
                    st.error("Title is required.")

        st.divider()
        all_tasks = load()
        n_active = sum(1 for t in all_tasks if not t["done"])
        n_done   = sum(1 for t in all_tasks if t["done"])
        st.caption(f"**{n_active}** active · **{n_done}** completed")

    # ── Tabs ───────────────────────────────────────────────────────────────────
    st.markdown("# Daily Work")

    counts     = {k: len(section_tasks(k)) for k in SECTIONS}
    tab_labels = [f"{label}  ({counts[key]})" for key, label in SECTIONS.items()] + ["📊 Dashboard"]
    tabs       = st.tabs(tab_labels)

    for tab, (section_key, _) in zip(tabs, SECTIONS.items()):
        with tab:
            tasks = section_tasks(section_key)
            if not tasks:
                st.markdown(
                    '<p style="color:#94A3B8;padding:3rem 0;text-align:center;font-size:0.95rem">'
                    "Nothing here yet.</p>",
                    unsafe_allow_html=True,
                )
            else:
                for i, task in enumerate(tasks):
                    render_task(task, section_key, i, len(tasks))

    with tabs[-1]:
        render_dashboard()


if __name__ == "__main__":
    main()
