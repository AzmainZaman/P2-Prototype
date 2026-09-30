"""Editor draft held in Streamlit session state.

Widget values live under keys prefixed "w_". Streamlit discards widget keys
when the user visits another page, so a canonical copy is kept in
`draft_values` and restored (`hydrate`) whenever the editor is shown again.
Each rubric item gets an internal uid so its widgets keep stable keys while
items are added and removed.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import streamlit as st

from grader.models import Concept, Configuration, RequiredItem, WrongIdea
from grader.normalize import split_lines
from grader.store import Store

SECTIONS = ("concepts", "required_items", "wrong_ideas")
ID_PREFIX = {"concepts": "C", "required_items": "R", "wrong_ideas": "W"}
QUESTION_KEYS = {
    "w_q_id": "question_id",
    "w_q_domain": "domain",
    "w_q_prompt": "prompt",
    "w_q_answer": "model_answer",
    "w_q_max": "max_mark",
    "w_q_inc": "increment",
}


def _lines(items: List[str]) -> str:
    return "\n".join(items)


def _item_values(section: str, uid: str, item) -> Dict[str, object]:
    k = f"w_{uid}_"
    if section == "concepts":
        return {k + "id": item.id, k + "label": item.label, k + "weight": float(item.weight),
                k + "expr": _lines(item.expressions), k + "clauses": _lines(item.clauses),
                k + "overlap": bool(item.allow_overlap)}
    if section == "required_items":
        return {k + "id": item.id, k + "kind": item.kind, k + "concept": item.concept_id,
                k + "phrases": _lines(item.phrases), k + "clauses": _lines(item.clauses),
                k + "cap": float(item.absence_cap)}
    return {k + "id": item.id, k + "label": item.label, k + "expr": _lines(item.expressions),
            k + "clauses": _lines(item.clauses), k + "action": item.action,
            k + "amount": float(item.amount or 0.0)}


def _set(key: str, value) -> None:
    st.session_state[key] = value
    st.session_state.draft_values[key] = value


def _new_uid() -> str:
    st.session_state.uid_counter = st.session_state.get("uid_counter", 0) + 1
    return f"u{st.session_state.uid_counter}"


def get(key: str):
    if key in st.session_state:
        return st.session_state[key]
    return st.session_state.draft_values.get(key)


def uids(section: str) -> List[str]:
    return st.session_state.draft_uids[section]


def base_config_id() -> Optional[str]:
    return st.session_state.get("draft_base")


# --- Loading --------------------------------------------------------------

def load_draft(cfg: Configuration, base_id: Optional[str]) -> None:
    for key in [k for k in st.session_state.keys() if str(k).startswith("w_")]:
        del st.session_state[key]
    values: Dict[str, object] = {}
    for key, attr in QUESTION_KEYS.items():
        value = getattr(cfg, attr)
        values[key] = float(value) if attr in ("max_mark", "increment") else value
    draft_uids = {s: [] for s in SECTIONS}
    for section in SECTIONS:
        for item in getattr(cfg, section):
            uid = _new_uid()
            draft_uids[section].append(uid)
            values.update(_item_values(section, uid, item))
    st.session_state.draft_values = values
    st.session_state.draft_uids = draft_uids
    st.session_state.draft_base = base_id
    hydrate()


def new_blank(store: Store) -> None:
    cfg = Configuration(
        question_id=store.next_question_id(),
        concepts=[Concept(id="C1", weight=1.0)],
    )
    load_draft(cfg, None)


def edit_version(cfg: Configuration) -> None:
    load_draft(cfg.as_draft(), cfg.config_id)


def ensure_draft(store: Store) -> None:
    if "draft_uids" not in st.session_state:
        new_blank(store)


def hydrate() -> None:
    """Restore widget keys that Streamlit dropped while another page was shown."""
    for key, value in st.session_state.draft_values.items():
        if key not in st.session_state:
            st.session_state[key] = value


def sync() -> None:
    """Copy current widget values into the canonical draft (call at the end of the page)."""
    for key in list(st.session_state.draft_values.keys()):
        if key in st.session_state:
            st.session_state.draft_values[key] = st.session_state[key]


# --- Building the configuration -------------------------------------------

def build_config() -> Configuration:
    cfg = Configuration(**{attr: get(key) for key, attr in QUESTION_KEYS.items()})
    cfg.question_id = (cfg.question_id or "").strip()
    for uid in uids("concepts"):
        k = f"w_{uid}_"
        cfg.concepts.append(Concept(
            id=(get(k + "id") or "").strip(), label=get(k + "label") or "",
            weight=get(k + "weight"), expressions=split_lines(get(k + "expr")),
            clauses=split_lines(get(k + "clauses")), allow_overlap=bool(get(k + "overlap")),
        ))
    for uid in uids("required_items"):
        k = f"w_{uid}_"
        linked = get(k + "kind") == "concept"
        cfg.required_items.append(RequiredItem(
            id=(get(k + "id") or "").strip(), kind=get(k + "kind"),
            concept_id=get(k + "concept") if linked else None,
            phrases=[] if linked else split_lines(get(k + "phrases")),
            clauses=[] if linked else split_lines(get(k + "clauses")),
            absence_cap=get(k + "cap"),
        ))
    for uid in uids("wrong_ideas"):
        k = f"w_{uid}_"
        action = get(k + "action")
        cfg.wrong_ideas.append(WrongIdea(
            id=(get(k + "id") or "").strip(), label=get(k + "label") or "",
            expressions=split_lines(get(k + "expr")), clauses=split_lines(get(k + "clauses")),
            action=action, amount=None if action == "review" else get(k + "amount"),
        ))
    return cfg


# --- Editing callbacks ----------------------------------------------------

def _next_id(section: str) -> str:
    used = {(get(f"w_{u}_id") or "").strip() for u in uids(section)}
    n = 1
    while f"{ID_PREFIX[section]}{n}" in used:
        n += 1
    return f"{ID_PREFIX[section]}{n}"


def add_item(section: str) -> None:
    uid = _new_uid()
    new_id = _next_id(section)
    if section == "concepts":
        item = Concept(id=new_id, weight=1.0)
    elif section == "required_items":
        concept_ids = [(get(f"w_{u}_id") or "").strip() for u in uids("concepts")]
        item = RequiredItem(id=new_id, concept_id=concept_ids[0] if concept_ids else None,
                            absence_cap=float(get("w_q_max") or 0.0))
    else:
        item = WrongIdea(id=new_id)
    for key, value in _item_values(section, uid, item).items():
        _set(key, value)
    uids(section).append(uid)


def remove_item(section: str, uid: str) -> None:
    uids(section).remove(uid)
    prefix = f"w_{uid}_"
    for key in [k for k in st.session_state.draft_values if k.startswith(prefix)]:
        del st.session_state.draft_values[key]
        st.session_state.pop(key, None)
