"""Home and task selection (Report Figure 4.6)."""
import streamlit as st

import draft_state as ds
import ui

store = ui.get_store()

ui.page_header("Proposed interface / 01", "Bangla short-answer grading assistant")
st.subheader("Teacher workspace")
st.caption("Every suggested mark requires teacher approval.")

left, right = st.columns(2)
with left.container(border=True, height=170):
    st.markdown("**Create a question**")
    st.caption("Define the model answer and rubric.")
    if st.button("Create question", type="primary", icon=":material/add:"):
        ds.new_blank(store)
        st.switch_page("views/editor.py")
with right.container(border=True, height=170):
    st.markdown("**Open a prepared question**")
    st.caption("Load a saved configuration version.")
    if st.button("Open question", type="primary", icon=":material/folder_open:"):
        st.switch_page("views/library.py")

active_id = st.session_state.get("active_config_id")
active = store.load(active_id) if active_id else None
with st.container(border=True):
    st.markdown("**Grade a typed answer**")
    if active:
        st.caption(f"Active question: {active.question_id} v{active.version}. Grading, evidence review and "
                   "approval are the next implementation milestone and are not part of this build.")
    else:
        st.caption("Available after a question and rubric pass validation.")
    st.button("Grade answer", disabled=True, icon=":material/lock:")

configs = store.all_configs()
if configs:
    st.subheader("Saved questions")
    latest = {}
    for c in configs:
        latest[c.question_id] = c
    st.dataframe(
        [{"Question": q, "Domain": c.domain, "Prompt": c.prompt,
          "Latest version": c.version, "Concepts": len(c.concepts), "Max mark": c.max_mark}
         for q, c in latest.items()],
        hide_index=True, width="stretch",
    )

with st.expander("Prototype progress (against Report Table 5.2)", icon=":material/checklist:"):
    st.dataframe(
        [
            {"Module": "Configuration and intake", "Status": "Implemented",
             "Evidence": "Question and rubric editor, validation rules, automated tests"},
            {"Module": "Versioned records", "Status": "Implemented (configurations)",
             "Evidence": "Read-only JSON versions with content hash and parent link"},
            {"Module": "Bangla preprocessing", "Status": "Partial",
             "Evidence": "NFC normalization, tokens with original offsets, clause segmentation, "
                         "negation/quotation/correction markers"},
            {"Module": "Rubric and misconception matching", "Status": "Partial",
             "Evidence": "Exact-match rubric preview with confirmed / candidate / uncertain / not-detected "
                         "states (no spelling tolerance, no marks)"},
            {"Module": "Semantic scoring and calibration", "Status": "Planned", "Evidence": "—"},
            {"Module": "Aggregation and review", "Status": "Planned", "Evidence": "—"},
            {"Module": "Feedback and approval", "Status": "Planned", "Evidence": "—"},
            {"Module": "Evaluation and records", "Status": "Planned", "Evidence": "—"},
        ],
        hide_index=True, width="stretch",
    )

ui.footer(ui.active_label(store))
