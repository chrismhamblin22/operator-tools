import streamlit as st
import json
import uuid
from datetime import datetime
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

def add_task(title: str, notes: str, topic: str, section: str) -> None:
    tasks = load()
    n = len([t for t in tasks if t["section"] == "priority" and not t["done"]])
    tasks.append({
        "id":         str(uuid.uuid4()),
        "title":      title.strip(),
        "notes":      notes.strip(),
        "topic":      topic,
        "section":    section,
        "priority":   n,
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
            t["done"] = True
            break
    save(tasks)


def delete_task(task_id: str) -> None:
    tasks = load()
    save([t for t in tasks if t["id"] != task_id])


def reorder(task_id: str, direction: str) -> None:
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
    if direction == "up" and i > 0:
        ids[i - 1], ids[i] = ids[i], ids[i - 1]
    elif direction == "down" and i < len(ids) - 1:
        ids[i], ids[i + 1] = ids[i + 1], ids[i]
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
    tid = task["id"]
    topic = task.get("topic", "")

    # Title + badge
    title_md = f"**{task['title']}**"
    if topic:
        title_md += f"&nbsp;&nbsp;{badge_html(topic)}"
    st.markdown(title_md, unsafe_allow_html=True)

    if task.get("notes"):
        st.caption(task["notes"])

    # Action row — priority section gets reorder arrows
    if section == "priority":
        up_col, dn_col, move_col, done_col, del_col = st.columns([1, 1, 4, 1, 1])
        with up_col:
            if idx > 0:
                if st.button("↑", key=f"up_{tid}", help="Move up"):
                    reorder(tid, "up")
                    st.rerun()
        with dn_col:
            if idx < total - 1:
                if st.button("↓", key=f"dn_{tid}", help="Move down"):
                    reorder(tid, "down")
                    st.rerun()
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
    /* Page background */
    .stApp { background: #F8FAFC; }

    /* Sidebar */
    section[data-testid="stSidebar"] { background: #1E293B !important; }
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stMarkdown { color: #CBD5E1 !important; }
    section[data-testid="stSidebar"] h2 { color: #F1F5F9 !important; }

    /* Main container */
    .block-container { padding-top: 1.5rem !important; max-width: 1100px; }

    /* Tabs */
    .stTabs [data-baseweb="tab"] { font-weight: 600; font-size: 0.85rem; }
    .stTabs [data-baseweb="tab-highlight"] { background: #6366F1; }

    /* Reduce vertical gap between elements */
    div[data-testid="stVerticalBlock"] > div.element-container { margin-bottom: 0.1rem; }

    /* Divider spacing */
    hr { margin: 0.5rem 0 !important; }
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
            submitted = st.form_submit_button("＋ Add Task", use_container_width=True, type="primary")
            if submitted:
                if title.strip():
                    add_task(title, notes, topic, dest)
                    st.success("Task added!")
                    st.rerun()
                else:
                    st.error("Title is required.")

        st.divider()
        all_tasks = load()
        n_active = len([t for t in all_tasks if not t["done"]])
        n_done   = len([t for t in all_tasks if t["done"]])
        st.caption(f"**{n_active}** active · **{n_done}** completed")

    # ── Main: section tabs ─────────────────────────────────────────────────────
    st.markdown("# Daily Work")

    counts     = {k: len(section_tasks(k)) for k in SECTIONS}
    tab_labels = [f"{label}  ({counts[key]})" for key, label in SECTIONS.items()]
    tabs       = st.tabs(tab_labels)

    for tab, (section_key, _) in zip(tabs, SECTIONS.items()):
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


if __name__ == "__main__":
    main()
