"""Saved question configurations and their version history."""
import json

import streamlit as st

import draft_state as ds
import ui
from grader.compare import summarize_changes
from grader.validation import concept_shares, fmt

store = ui.get_store()

ui.page_header("Question library", "Saved question configurations")

question_ids = store.question_ids()
if not question_ids:
    st.info("No questions have been saved yet.")
    if st.button("Create question", type="primary"):
        ds.new_blank(store)
        st.switch_page("views/editor.py")
    st.stop()

latest_by_q = {q: store.latest(q) for q in question_ids}
active_id = st.session_state.get("active_config_id")
default_q = active_id.rsplit("-v", 1)[0] if active_id else question_ids[0]


def _excerpt(text, n=60):
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n] + "…"


qid = st.selectbox(
    "Question", question_ids,
    index=question_ids.index(default_q) if default_q in question_ids else 0,
    format_func=lambda q: f"{q} — {_excerpt(latest_by_q[q].prompt)}",
)
versions = store.versions(qid)

st.markdown("**Version history**")
st.dataframe(
    [{"Version": v.version, "Config ID": v.config_id, "Created (UTC)": v.created_at.replace("T", " "),
      "Based on": v.parent_config_id or "—", "Content hash": v.content_hash[:12],
      "Concepts": len(v.concepts), "Max mark": v.max_mark}
     for v in reversed(versions)],
    hide_index=True, width="stretch",
)

version_numbers = [v.version for v in reversed(versions)]
chosen = st.selectbox(
    "Version", version_numbers,
    format_func=lambda n: f"v{n}" + (" (latest)" if n == versions[-1].version else ""),
)
cfg = next(v for v in versions if v.version == chosen)

b1, b2, _ = st.columns([1.3, 1.3, 2])
if b1.button("Edit as new version", type="primary", icon=":material/edit:", width="stretch"):
    ds.edit_version(cfg)
    st.switch_page("views/editor.py")
is_active = active_id == cfg.config_id
if b2.button("Active question" if is_active else "Set as active question", disabled=is_active,
             icon=":material/check:" if is_active else ":material/radio_button_unchecked:", width="stretch"):
    st.session_state.active_config_id = cfg.config_id
    st.rerun()

# --- Read-only view ----------------------------------------------------------
with st.container(border=True):
    st.markdown(f"**{cfg.config_id}** · read-only")
    st.caption("Saved versions cannot be changed. Editing creates a new version and leaves this one intact.")
    if store.verify(cfg):
        st.markdown(f":green[**Integrity check passed**] · SHA-256 `{cfg.content_hash}`")
    else:
        st.error("Integrity check failed: this file was modified outside the application.",
                 icon=":material/gpp_bad:")

    if cfg.parent_config_id:
        parent = store.load(cfg.parent_config_id)
        if parent:
            changes = summarize_changes(parent, cfg)
            st.markdown(f"**Changes from {parent.config_id}:** "
                        + ("; ".join(changes) if changes else "none"))

m1, m2, m3, m4 = st.columns(4)
m1.metric("Maximum mark", fmt(cfg.max_mark))
m2.metric("Mark increment", fmt(cfg.increment))
m3.metric("Concepts", len(cfg.concepts))
m4.metric("Required / wrong ideas", f"{len(cfg.required_items)} / {len(cfg.wrong_ideas)}")

st.caption("Domain: " + ui.md_escape(cfg.domain))
ui.literal(cfg.prompt, "Question prompt")
ui.literal(cfg.model_answer, "Model answer (private to the teacher)")

st.markdown("**Weighted concepts**")
st.dataframe(
    [{"ID": c.id, "Description": c.label, "Weight": c.weight, "Share": (s or 0) * 100,
      "Accepted expressions": " · ".join(c.expressions), "Clauses": len(c.clauses),
      "Overlap allowed": c.allow_overlap}
     for c, s in zip(cfg.concepts, concept_shares(cfg))],
    hide_index=True, width="stretch",
    column_config={"Share": st.column_config.ProgressColumn("Share", format="%.0f%%",
                                                            min_value=0, max_value=100)},
)
for c in cfg.concepts:
    if c.clauses:
        with st.expander(f"Approved clause patterns for {c.id}"):
            for clause in c.clauses:
                ui.literal(clause)

if cfg.required_items:
    st.markdown("**Required items**")
    st.dataframe(
        [{"ID": r.id,
          "Requires": f"Concept {r.concept_id}" if r.kind == "concept" else " · ".join(r.phrases),
          "Type": "Linked concept" if r.kind == "concept" else "Standalone phrase",
          "Absence cap": r.absence_cap}
         for r in cfg.required_items],
        hide_index=True, width="stretch",
    )

if cfg.wrong_ideas:
    st.markdown("**Known wrong ideas**")
    st.dataframe(
        [{"ID": w.id, "Description": w.label, "Triggers": " · ".join(w.expressions),
          "Action": {"cap": "Cap", "penalty": "Penalty", "review": "Review only"}[w.action],
          "Amount": "—" if w.amount is None else fmt(w.amount), "Clauses": len(w.clauses)}
         for w in cfg.wrong_ideas],
        hide_index=True, width="stretch",
    )
    for w in cfg.wrong_ideas:
        if w.clauses:
            with st.expander(f"Confirming clause patterns for {w.id}"):
                for clause in w.clauses:
                    ui.literal(clause)

st.download_button(
    "Download configuration (JSON)",
    data=json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2).encode("utf-8"),
    file_name=f"{cfg.config_id}.json", mime="application/json", icon=":material/download:",
)

ui.footer(ui.active_label(store))
