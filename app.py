"""
Workspace Tracker & To-Do List — Streamlit port of the single-file HTML app.

Run with:  streamlit run app.py
Requires:  streamlit >= 1.33  (st.popover, st.date_input(value=None))
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="Workspace Tracker & To-Do List",
    page_icon="📋",
    layout="wide",
)

# --------------------------------------------------------------------------- #
# Constants & small helpers
# --------------------------------------------------------------------------- #

DATA_FILE = Path(__file__).with_name("workspace_tracker_data.json")

PRIORITY_META = {
    "low":    {"label": "Low",    "icon": "🟢", "next": "medium"},
    "medium": {"label": "Medium", "icon": "🟡", "next": "high"},
    "high":   {"label": "High",   "icon": "🔴", "next": "low"},
}
PRIORITY_ORDER = ["low", "medium", "high"]
FILTER_ORDER = ["all", "active", "completed"]
FILTER_LABELS = {"all": "All", "active": "Active", "completed": "Done"}

_MD_SPECIAL = re.compile(r"([\\`*_{}\[\]()#+\-.!|>~])")


def uid() -> str:
    return "id_" + uuid.uuid4().hex[:8]


def md_escape(text: str) -> str:
    """Prevent task text from being interpreted as markdown."""
    return _MD_SPECIAL.sub(r"\\\1", str(text))


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def format_deadline(date_str: str | None) -> dict | None:
    due = parse_date(date_str)
    if due is None:
        return None
    diff = (due - date.today()).days
    short = due.strftime("%b %d")
    if diff < 0:
        return {"label": f"Overdue ({short})", "kind": "overdue"}
    if diff == 0:
        return {"label": "Due Today", "kind": "today"}
    if diff == 1:
        return {"label": "Due Tomorrow", "kind": "soon"}
    return {"label": f"Due {short}", "kind": "normal"}


# --------------------------------------------------------------------------- #
# State handling (replaces localStorage with session_state + a JSON file)
# --------------------------------------------------------------------------- #

def default_state() -> dict:
    return {"activeNode": None, "filter": "all", "categories": []}


def _norm_todo(todo: dict) -> None:
    todo.setdefault("id", uid())
    todo.setdefault("text", "")
    todo.setdefault("done", False)
    if todo.get("priority") not in PRIORITY_META:
        todo["priority"] = "medium"
    if not isinstance(todo.get("deadline"), str):
        todo["deadline"] = ""


def _norm_node(node: dict) -> None:
    node.setdefault("id", uid())
    node.setdefault("name", "Untitled")
    node.setdefault("refresher", "")
    node.setdefault("todos", [])
    for todo in node["todos"]:
        _norm_todo(todo)


def normalize_state(parsed) -> dict:
    if not isinstance(parsed, dict) or not isinstance(parsed.get("categories"), list):
        return default_state()
    parsed.setdefault("activeNode", None)
    if parsed.get("filter") not in FILTER_ORDER:
        parsed["filter"] = "all"
    for cat in parsed["categories"]:
        cat.setdefault("id", uid())
        cat.setdefault("name", "Untitled")
        cat.setdefault("collapsed", False)
        cat.setdefault("tabs", [])
        for tab in cat["tabs"]:
            _norm_node(tab)
            tab.setdefault("expanded", True)
            tab.setdefault("subTabs", [])
            for sub in tab["subTabs"]:
                _norm_node(sub)
    return parsed


def sample_state() -> dict:
    subtab = {
        "id": uid(), "name": "Bug Bash", "refresher": "",
        "todos": [
            {"id": uid(), "text": "Fix the login redirect", "done": False,
             "priority": "high", "deadline": ""},
        ],
    }
    tab1 = {
        "id": uid(), "name": "Project Alpha", "expanded": True,
        "refresher": "Waiting on design sign-off. Next up: the settings page.",
        "todos": [
            {"id": uid(), "text": "Review the wireframes", "done": False,
             "priority": "high", "deadline": date.today().isoformat()},
            {"id": uid(), "text": "Send status update to the team", "done": False,
             "priority": "medium", "deadline": ""},
            {"id": uid(), "text": "Set up the repository", "done": True,
             "priority": "low", "deadline": ""},
        ],
        "subTabs": [subtab],
    }
    tab2 = {
        "id": uid(), "name": "Reading List", "expanded": True, "refresher": "",
        "todos": [
            {"id": uid(), "text": "Finish chapter 4", "done": False,
             "priority": "low", "deadline": ""},
        ],
        "subTabs": [],
    }
    return {
        "activeNode": {"categoryId": None, "tabId": tab1["id"], "parentTabId": None},
        "filter": "all",
        "categories": [
            {"id": uid(), "name": "Work", "collapsed": False, "tabs": [tab1]},
            {"id": uid(), "name": "Personal", "collapsed": False, "tabs": [tab2]},
        ],
    }


def get_state() -> dict:
    return st.session_state.state


def persist() -> None:
    try:
        DATA_FILE.write_text(
            json.dumps(st.session_state.state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass


def find_node(active: dict | None):
    """Return (category, parent_tab_or_None, node) for the active node."""
    if not active:
        return None
    cat = next((c for c in get_state()["categories"] if c["id"] == active.get("categoryId")), None)
    if cat is None:
        return None
    parent_id = active.get("parentTabId")
    for tab in cat["tabs"]:
        if parent_id:
            if tab["id"] == parent_id:
                for sub in tab.get("subTabs", []):
                    if sub["id"] == active.get("tabId"):
                        return cat, tab, sub
        elif tab["id"] == active.get("tabId"):
            return cat, None, tab
    return None


if "state" not in st.session_state:
    if DATA_FILE.exists():
        try:
            st.session_state.state = normalize_state(
                json.loads(DATA_FILE.read_text(encoding="utf-8"))
            )
        except Exception:
            st.session_state.state = sample_state()
    else:
        st.session_state.state = sample_state()
        persist()


# --------------------------------------------------------------------------- #
# Callbacks (run BEFORE the script body, so the UI is already up to date)
# --------------------------------------------------------------------------- #

def _toggle_done(todo: dict, key: str) -> None:
    todo["done"] = bool(st.session_state.get(key))
    persist()


def _save_refresher(node: dict, key: str) -> None:
    node["refresher"] = st.session_state.get(key, "")
    persist()


def _save_deadline(todo: dict, key: str) -> None:
    picked = st.session_state.get(key)
    todo["deadline"] = picked.isoformat() if isinstance(picked, date) else ""
    persist()


def _clear_deadline(todo: dict, key: str) -> None:
    todo["deadline"] = ""
    if key in st.session_state:
        st.session_state[key] = None
    persist()


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #

def render_tab_row(cat: dict, tab: dict) -> None:
    state = get_state()
    active = state.get("activeNode") or {}
    is_active = (
        active.get("categoryId") == cat["id"]
        and active.get("tabId") == tab["id"]
        and not active.get("parentTabId")
    )
    open_count = sum(1 for t in tab.get("todos", []) if not t.get("done"))

    c1, c2 = st.columns([6, 1])
    with c1:
        label = f"📄 {tab['name']}"
        if open_count:
            label += f"  ·  {open_count}"
        if st.button(
            label,
            key=f"tab_btn_{tab['id']}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            state["activeNode"] = {
                "categoryId": cat["id"],
                "tabId": tab["id"],
                "parentTabId": None,
            }
            persist()
            st.rerun()

    with c2:
        with st.popover("⋯"):
            renamed = st.text_input("Rename tab", value=tab["name"], key=f"tab_ren_{tab['id']}")
            if st.button("💾 Save name", key=f"tab_ren_save_{tab['id']}", use_container_width=True):
                if renamed.strip():
                    tab["name"] = renamed.strip()
                    persist()
                    st.rerun()

            sub_name = st.text_input("New sub-tab", key=f"sub_new_{tab['id']}", placeholder="Sub-tab name")
            if st.button("➕ Add sub-tab", key=f"sub_add_{tab['id']}", use_container_width=True):
                if sub_name.strip():
                    sub = {"id": uid(), "name": sub_name.strip(), "refresher": "", "todos": []}
                    tab.setdefault("subTabs", []).append(sub)
                    state["activeNode"] = {
                        "categoryId": cat["id"],
                        "tabId": sub["id"],
                        "parentTabId": tab["id"],
                    }
                    persist()
                    st.rerun()

            if st.button("🗑 Delete tab", key=f"tab_del_{tab['id']}", use_container_width=True):
                cat["tabs"] = [t for t in cat["tabs"] if t["id"] != tab["id"]]
                persist()
                st.rerun()

    for sub in tab.get("subTabs", []):
        render_sub_row(cat, tab, sub)


def render_sub_row(cat: dict, tab: dict, sub: dict) -> None:
    state = get_state()
    active = state.get("activeNode") or {}
    is_active = (
        active.get("categoryId") == cat["id"]
        and active.get("tabId") == sub["id"]
        and active.get("parentTabId") == tab["id"]
    )
    open_count = sum(1 for t in sub.get("todos", []) if not t.get("done"))

    c0, c1, c2 = st.columns([0.4, 5.6, 1])
    with c1:
        label = f"↳ {sub['name']}"
        if open_count:
            label += f"  ·  {open_count}"
        if st.button(
            label,
            key=f"sub_btn_{sub['id']}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            state["activeNode"] = {
                "categoryId": cat["id"],
                "tabId": sub["id"],
                "parentTabId": tab["id"],
            }
            persist()
            st.rerun()

    with c2:
        with st.popover("⋯"):
            renamed = st.text_input("Rename sub-tab", value=sub["name"], key=f"sub_ren_{sub['id']}")
            if st.button("💾 Save name", key=f"sub_ren_save_{sub['id']}", use_container_width=True):
                if renamed.strip():
                    sub["name"] = renamed.strip()
                    persist()
                    st.rerun()
            if st.button("🗑 Delete sub-tab", key=f"sub_del_{sub['id']}", use_container_width=True):
                tab["subTabs"] = [s for s in tab["subTabs"] if s["id"] != sub["id"]]
                persist()
                st.rerun()


def render_category(cat: dict) -> None:
    state = get_state()
    cid = cat["id"]

    with st.expander(cat["name"], expanded=not cat.get("collapsed", False)):
        with st.popover("⋯ Category options", use_container_width=True):
            renamed = st.text_input("Rename category", value=cat["name"], key=f"cat_ren_{cid}")
            if st.button("💾 Save name", key=f"cat_ren_save_{cid}", use_container_width=True):
                if renamed.strip():
                    cat["name"] = renamed.strip()
                    persist()
                    st.rerun()

            new_tab = st.text_input("New tab name", key=f"cat_newtab_{cid}", placeholder="Tab name")
            if st.button("➕ Add tab", key=f"cat_addtab_{cid}", use_container_width=True):
                if new_tab.strip():
                    tab = {"id": uid(), "name": new_tab.strip(), "expanded": True,
                           "refresher": "", "todos": [], "subTabs": []}
                    cat["tabs"].append(tab)
                    state["activeNode"] = {"categoryId": cid, "tabId": tab["id"], "parentTabId": None}
                    persist()
                    st.rerun()

            st.divider()
            confirm = st.checkbox("Confirm delete", key=f"cat_sure_{cid}")
            if st.button(
                "🗑 Delete category",
                key=f"cat_del_{cid}",
                use_container_width=True,
                disabled=not confirm,
            ):
                state["categories"] = [c for c in state["categories"] if c["id"] != cid]
                persist()
                st.rerun()

        if not cat["tabs"]:
            st.caption("No tabs yet — use the ⋯ menu to add one.")

        for tab in cat["tabs"]:
            render_tab_row(cat, tab)


def render_backup_panel() -> None:
    state = get_state()
    with st.expander("💾 Backup / Restore"):
        st.download_button(
            "⬇️ Download backup (.json)",
            data=json.dumps(state, indent=2, ensure_ascii=False),
            file_name="workspace-tracker-backup.json",
            mime="application/json",
            use_container_width=True,
        )

        pasted = st.text_area(
            "Paste JSON to restore",
            key="restore_json_area",
            height=120,
            placeholder='{"categories": [ ... ]}',
        )
        if st.button("♻️ Restore from pasted JSON", use_container_width=True):
            try:
                st.session_state.state = normalize_state(json.loads(pasted))
                persist()
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Could not restore: {exc}")

        uploaded = st.file_uploader("…or upload a backup file", type=["json"])
        if uploaded is not None and st.button("♻️ Restore from file", use_container_width=True):
            try:
                st.session_state.state = normalize_state(
                    json.loads(uploaded.getvalue().decode("utf-8"))
                )
                persist()
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Could not restore: {exc}")

        st.divider()
        sure = st.checkbox("I'm sure", key="reset_sure")
        if st.button("🧹 Reset workspace (delete everything)", use_container_width=True, disabled=not sure):
            st.session_state.state = default_state()
            persist()
            st.rerun()


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## 📋 Workspace Tracker")

        with st.form("add_category_form", clear_on_submit=True):
            name = st.text_input(
                "New category", placeholder="New category name", label_visibility="collapsed"
            )
            if st.form_submit_button("➕ Add Category", use_container_width=True):
                if name.strip():
                    get_state()["categories"].append(
                        {"id": uid(), "name": name.strip(), "collapsed": False, "tabs": []}
                    )
                    persist()
                    st.rerun()

        st.divider()
        cats = get_state()["categories"]
        if not cats:
            st.caption("No categories yet — add one above.")
        for cat in cats:
            render_category(cat)

        st.divider()
        render_backup_panel()


# --------------------------------------------------------------------------- #
# Main workspace
# --------------------------------------------------------------------------- #

def render_task_row(todos: list[dict], idx: int, todo: dict) -> None:
    tid = todo["id"]
    c0, c1, c2, c3, c4 = st.columns([0.4, 6, 1.3, 1.7, 0.9])

    with c0:
        st.checkbox(
            "Done",
            value=todo["done"],
            key=f"done_{tid}",
            label_visibility="collapsed",
            on_change=_toggle_done,
            args=(todo, f"done_{tid}"),
        )

    with c1:
        text = md_escape(todo["text"])
        st.markdown(f"~~{text}~~" if todo["done"] else text)

    with c2:
        meta = PRIORITY_META[todo["priority"]]
        if st.button(
            f"{meta['icon']} {meta['label']}",
            key=f"prio_{tid}",
            use_container_width=True,
            help="Click to cycle priority",
        ):
            todo["priority"] = meta["next"]
            persist()
            st.rerun()

    with c3:
        info = format_deadline(todo.get("deadline"))
        with st.popover(f"📅 {info['label']}" if info else "📅 Set date"):
            dl_key = f"dl_{tid}"
            st.date_input(
                "Deadline",
                value=parse_date(todo.get("deadline")),
                key=dl_key,
                label_visibility="collapsed",
            )
            b1, b2 = st.columns(2)
            with b1:
                st.button("Save", key=f"dl_save_{tid}", use_container_width=True,
                          on_click=_save_deadline, args=(todo, dl_key))
            with b2:
                st.button("Clear", key=f"dl_clear_{tid}", use_container_width=True,
                          on_click=_clear_deadline, args=(todo, dl_key))

    with c4:
        with st.popover("⋯"):
            new_text = st.text_input("Edit task", value=todo["text"], key=f"edit_{tid}")
            if st.button("💾 Save text", key=f"save_text_{tid}", use_container_width=True):
                if new_text.strip():
                    todo["text"] = new_text.strip()
                    persist()
                    st.rerun()

            u1, u2 = st.columns(2)
            with u1:
                if st.button("↑ Up", key=f"up_{tid}", use_container_width=True, disabled=idx == 0):
                    todos[idx - 1], todos[idx] = todos[idx], todos[idx - 1]
                    persist()
                    st.rerun()
            with u2:
                if st.button("↓ Down", key=f"down_{tid}", use_container_width=True,
                             disabled=idx == len(todos) - 1):
                    todos[idx + 1], todos[idx] = todos[idx], todos[idx + 1]
                    persist()
                    st.rerun()

            if st.button("🗑 Delete task", key=f"del_{tid}", use_container_width=True):
                todos.pop(idx)
                persist()
                st.rerun()


def render_workspace() -> None:
    state = get_state()
    ctx = find_node(state.get("activeNode"))

    if ctx is None:
        st.subheader("Select or create a tab to get started")
        st.caption("Pick any tab or sub-tab in the sidebar, or create one from a category's ⋯ menu.")
        return

    cat, parent, node = ctx
    nid = node["id"]

    # Breadcrumb
    trail = f"{cat['name']} › "
    if parent:
        trail += f"{parent['name']} › "
    trail += node["name"]
    st.caption(trail)

    # Title + rename
    t1, t2 = st.columns([9, 1])
    with t1:
        st.markdown(f"## {md_escape(node['name'])}")
    with t2:
        with st.popover("✏️"):
            renamed = st.text_input("Rename tab", value=node["name"], key=f"ws_ren_{nid}")
            if st.button("💾 Save", key=f"ws_ren_save_{nid}", use_container_width=True):
                if renamed.strip():
                    node["name"] = renamed.strip()
                    persist()
                    st.rerun()

    # Refresher
    st.markdown("##### 📌 What's Going On / Refresher")
    st.text_area(
        "Refresher",
        value=node.get("refresher", ""),
        key=f"refresher_{nid}",
        label_visibility="collapsed",
        height=100,
        placeholder="Type a quick refresher on where you left off, current status, or key context…",
        on_change=_save_refresher,
        args=(node, f"refresher_{nid}"),
    )

    st.divider()

    # To-do header + filters
    todos = node.setdefault("todos", [])
    active_count = sum(1 for t in todos if not t.get("done"))
    done_count = len(todos) - active_count

    h1, h2 = st.columns([5, 4])
    with h1:
        st.markdown("### ✅ To-Do List")
        st.caption(f"{active_count} remaining · {done_count} done")
    with h2:
        current = state.get("filter", "all")
        if current not in FILTER_ORDER:
            current = "all"
        choice = st.radio(
            "Filter",
            FILTER_ORDER,
            index=FILTER_ORDER.index(current),
            format_func=lambda f: (
                f"{FILTER_LABELS[f]} ("
                f"{len(todos) if f == 'all' else active_count if f == 'active' else done_count})"
            ),
            horizontal=True,
            label_visibility="collapsed",
            key=f"filter_{nid}",
        )
        if choice != state.get("filter"):
            state["filter"] = choice
            persist()

    # Add task form
    with st.form(f"add_task_{nid}", clear_on_submit=True):
        f1, f2, f3, f4 = st.columns([5, 2, 2, 1])
        with f1:
            text = st.text_input("New task", placeholder="Add a new task…", label_visibility="collapsed")
        with f2:
            prio = st.selectbox(
                "Priority",
                PRIORITY_ORDER,
                index=1,
                format_func=lambda p: f"{PRIORITY_META[p]['icon']} {PRIORITY_META[p]['label']}",
                label_visibility="collapsed",
            )
        with f3:
            due = st.date_input("Deadline", value=None, label_visibility="collapsed")
        with f4:
            submitted = st.form_submit_button("Add", type="primary", use_container_width=True)

        if submitted and text.strip():
            todos.append({
                "id": uid(),
                "text": text.strip(),
                "done": False,
                "priority": prio,
                "deadline": due.isoformat() if due else "",
            })
            persist()
            st.rerun()

    # Task list
    filter_mode = state.get("filter", "all")
    shown = 0
    for idx, todo in enumerate(todos):
        if filter_mode == "active" and todo.get("done"):
            continue
        if filter_mode == "completed" and not todo.get("done"):
            continue
        shown += 1
        render_task_row(todos, idx, todo)

    if shown == 0:
        st.caption("No tasks in this view. Add one above to start tracking!")


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #

render_sidebar()
render_workspace()
