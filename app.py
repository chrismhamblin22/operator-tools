from __future__ import annotations
import streamlit as st
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

DATA_FILE = Path("tasks.json")

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

# ── Data layer ────────────────────────────────────────────────────────────────

def load() -> list[dict]:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return []


def save(tasks: list[dict]) -> None:
    DATA_FILE.write_text(json.dumps(tasks, indent=2))


def section_tasks(section: str) -> list[dict]:
    tasks = load()
    result = [t for t in tasks if t["section"] == section and not t["done"]]
    if section == "priority":
        result.sort(key=lambda x: x.get("priority", 0))
    else:
        result.sort(key=lambda x: x["created_at"])
    return result

# ── Mutations ─────────────────────────────────────────────────────────────────

def add_task(title: str, notes: str, topic: str, section: str, priority_pos: int | None = None) -> None:
    tasks = load()
    active_priority = sorted(
        [t for t in tasks if t["section"] == "priority" and not t["done"]],
        key=lambda x: x.get("priority", 0),
    )
    n = len(active_priority)

    if section == "priority" and priority_pos is not None:
        # Insert at the requested position and shift others down
        ids = [t["id"] for t in active_priority]
        new_idx = max(0, min(priority_pos - 1, n))
        ids.insert(new_idx, "__new__")
        pri_map = {tid: pos for pos, tid in enumerate(ids)}
        for t in tasks:
            if t["id"] in pri_map:
                t["priority"] = pri_map[t["id"]]
        new_priority = pri_map["__new__"]
    else:
        new_priority = n

    tasks.append({
        "id":         str(uuid.uuid4()),
        "title":      title.strip(),
        "notes":      notes.strip(),
        "topic":      topic,
        "section":    section,
        "priority":   new_priority,
        "done":       False,
        "created_at": datetime.now().isoformat(),
    })
    save(tasks)


def move_task(task_id: str, new_section: str) -> None:
    tasks = load()
    for t in tasks:
        if t["id"] == task_id:
            t["section"] = new_section
            if new_section == "priority":
                n = len([x for x in tasks if x["section"] == "priority" and not x["done"]])
                t["priority"] = n
            break
    save(tasks)


def mark_done(task_id: str) -> None:
    tasks = load()
    for t in tasks:
        if t["id"] == task_id:
            t["done"]    = True
            t["done_at"] = datetime.now().isoformat()
            break
    save(tasks)


def delete_task(task_id: str) -> None:
    tasks = load()
    save([t for t in tasks if t["id"] != task_id])


def set_priority(task_id: str, new_pos: int) -> None:
    tasks = load()
    active = sorted(
        [t for t in tasks if t["section"] == "priority" and not t["done"]],
        key=lambda x: x.get("priority", 0),
    )
    ids = [t["id"] for t in active]
    try:
        i = ids.index(task_id)
    except ValueError:
        return
    new_idx = max(0, min(new_pos - 1, len(ids) - 1))
    ids.pop(i)
    ids.insert(new_idx, task_id)
    pri = {tid: pos for pos, tid in enumerate(ids)}
    for t in tasks:
        if t["id"] in pri:
            t["priority"] = pri[t["id"]]
    save(tasks)

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
    df["created_at"] = pd.to_datetime(df["created_at"], utc=False, errors="coerce")
    df["done_at"]    = pd.to_datetime(df.get("done_at"), utc=False, errors="coerce") if "done_at" in df else pd.NaT
    df["topic"]      = df["topic"].fillna("").replace("", "Untagged")
    df["age_days"]   = (now - df["created_at"].dt.tz_localize(None)).dt.total_seconds() / 86400

    done_df   = df[df["done"] == True].copy()
    active_df = df[df["done"] == False].copy()

    if not done_df.empty and "done_at" in done_df.columns:
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
        if not done_df.empty and "days_to_complete" in done_df.columns and done_df["days_to_complete"].notna().any():
            avg = done_df["days_to_complete"].mean()
            st.metric("Avg days to complete", f"{avg:.1f}d")
        else:
            st.metric("Avg days to complete", "—")
    with m5:
        if not active_df.empty:
            avg_age = active_df["age_days"].mean()
            st.metric("Avg active task age", f"{avg_age:.1f}d")
        else:
            st.metric("Avg active task age", "—")

    st.markdown("---")

    col_left, col_right = st.columns(2)

    # ── Completed tasks per day (last 30 days) ────────────────────────────────
    with col_left:
        st.markdown("**Completed per day** (last 30 days)")
        if not done_df.empty and done_df["done_at"].notna().any():
            daily = (
                done_df.dropna(subset=["done_at"])
                .assign(day=lambda d: d["done_at"].dt.tz_localize(None).dt.date)
                .groupby("day")
                .size()
                .reset_index(name="count")
            )
            daily["day"] = pd.to_datetime(daily["day"])
            cutoff = pd.Timestamp(now.date()) - pd.Timedelta(days=30)
            daily  = daily[daily["day"] >= cutoff]
            if not daily.empty:
                chart = (
                    alt.Chart(daily)
                    .mark_bar(color="#6366F1", cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                    .encode(
                        x=alt.X("day:T", title=None, axis=alt.Axis(format="%b %d", labelAngle=-45)),
                        y=alt.Y("count:Q", title="Tasks", axis=alt.Axis(tickMinStep=1)),
                        tooltip=[alt.Tooltip("day:T", format="%b %d"), "count:Q"],
                    )
                    .properties(height=220)
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                st.caption("No completions in last 30 days.")
        else:
            st.caption("No completed tasks yet.")

    # ── Tasks by topic ────────────────────────────────────────────────────────
    with col_right:
        st.markdown("**Tasks by topic**")
        by_topic = (
            df.groupby("topic")
            .agg(total=("id", "count"), done=("done", "sum"))
            .reset_index()
            .sort_values("total", ascending=False)
        )
        by_topic["active"] = by_topic["total"] - by_topic["done"]

        melted = by_topic.melt(id_vars="topic", value_vars=["active", "done"], var_name="status", value_name="count")
        color_scale = alt.Scale(domain=["active", "done"], range=["#6366F1", "#10B981"])
        chart = (
            alt.Chart(melted)
            .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("count:Q", title="Tasks", axis=alt.Axis(tickMinStep=1)),
                y=alt.Y("topic:N", sort="-x", title=None),
                color=alt.Color("status:N", scale=color_scale, legend=alt.Legend(title=None)),
                tooltip=["topic:N", "status:N", "count:Q"],
            )
            .properties(height=220)
        )
        st.altair_chart(chart, use_container_width=True)

    col_left2, col_right2 = st.columns(2)

    # ── Avg days to complete by topic ─────────────────────────────────────────
    with col_left2:
        st.markdown("**Avg days to complete by topic**")
        if not done_df.empty and "days_to_complete" in done_df.columns and done_df["days_to_complete"].notna().any():
            avg_by_topic = (
                done_df.dropna(subset=["days_to_complete"])
                .groupby("topic")["days_to_complete"]
                .mean()
                .reset_index()
                .rename(columns={"days_to_complete": "avg_days"})
                .sort_values("avg_days", ascending=False)
            )
            chart = (
                alt.Chart(avg_by_topic)
                .mark_bar(color="#F59E0B", cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                .encode(
                    x=alt.X("avg_days:Q", title="Days"),
                    y=alt.Y("topic:N", sort="-x", title=None),
                    tooltip=["topic:N", alt.Tooltip("avg_days:Q", format=".1f")],
                )
                .properties(height=220)
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            st.caption("No completion data yet.")

    # ── Active tasks by section ───────────────────────────────────────────────
    with col_right2:
        st.markdown("**Active tasks by section**")
        by_section = (
            active_df.groupby("section")
            .size()
            .reset_index(name="count")
        )
        by_section["label"] = by_section["section"].map(
            lambda s: SECTIONS.get(s, s).split(" ", 1)[1] if s in SECTIONS else s
        )
        if not by_section.empty:
            chart = (
                alt.Chart(by_section)
                .mark_bar(color="#06B6D4", cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
                .encode(
                    x=alt.X("count:Q", title="Tasks", axis=alt.Axis(tickMinStep=1)),
                    y=alt.Y("label:N", sort="-x", title=None),
                    tooltip=["label:N", "count:Q"],
                )
                .properties(height=220)
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            st.caption("No active tasks.")

    # ── Oldest active tasks ───────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("**Oldest active tasks**")
    oldest = (
        active_df[["title", "topic", "section", "age_days"]]
        .sort_values("age_days", ascending=False)
        .head(10)
        .copy()
    )
    oldest["section"] = oldest["section"].map(lambda s: SECTIONS.get(s, s).split(" ", 1)[1])
    oldest["age_days"] = oldest["age_days"].map(lambda x: f"{x:.1f}d")
    oldest.columns = ["Title", "Topic", "Section", "Age"]
    st.dataframe(oldest, use_container_width=True, hide_index=True)

# ── App ───────────────────────────────────────────────────────────────────────

def main():
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

    # ── Sidebar: add task ──────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("## Add Task")
        st.divider()

        with st.form("add_task_form", clear_on_submit=True):
            title = st.text_input("Title", placeholder="What needs to happen?")
            notes = st.text_area("Notes", placeholder="Context, links, details…", height=80)
            topic = st.selectbox("Topic", TOPICS)
            dest  = st.selectbox(
                "Add to",
                list(SECTIONS.keys()),
                format_func=lambda x: SECTIONS[x],
            )
            n_priority = len(section_tasks("priority"))
            pri_pos = st.number_input(
                "Priority position",
                min_value=1,
                max_value=max(n_priority + 1, 1),
                value=n_priority + 1,
                step=1,
                help="Where in the priority list to insert (only applies when adding to Priority Actions)",
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
        n_active = len([t for t in all_tasks if not t["done"]])
        n_done   = len([t for t in all_tasks if t["done"]])
        st.caption(f"**{n_active}** active · **{n_done}** completed")

    # ── Main: section tabs + dashboard ─────────────────────────────────────────
    st.markdown("# Daily Work")

    counts     = {k: len(section_tasks(k)) for k in SECTIONS}
    tab_labels = [f"{label}  ({counts[key]})" for key, label in SECTIONS.items()]
    tab_labels.append("📊 Dashboard")
    tabs = st.tabs(tab_labels)

    section_items = list(SECTIONS.items())
    for tab, (section_key, _) in zip(tabs, section_items):
        with tab:
            tasks = section_tasks(section_key)
            if not tasks:
                st.markdown(
                    '<p style="color:#94A3B8;padding:3rem 0;text-align:center;font-size:0.95rem">'
                    "Nothing here yet."
                    "</p>",
                    unsafe_allow_html=True,
                )
            else:
                for i, task in enumerate(tasks):
                    render_task(task, section_key, i, len(tasks))

    with tabs[-1]:
        render_dashboard()


if __name__ == "__main__":
    main()
