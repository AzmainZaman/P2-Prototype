"""Question and rubric editor (Report Figure 4.7, §4.5.1)."""
import streamlit as st

import draft_state as ds
import ui
from grader.preview import CANDIDATE, CONFIRMED, NOT_DETECTED, UNCERTAIN, preview, review_needed
from grader.store import NoChanges, ValidationFailed, compute_hash
from grader.validation import concept_shares, fmt, has_errors, validate

store = ui.get_store()
ds.ensure_draft(store)
ds.hydrate()

base_id = ds.base_config_id()
base = store.load(base_id) if base_id else None
latest = store.latest(base.question_id) if base else None

ui.page_header("Proposed interface / 02", "Question and rubric editor")

# Outcome of the previous save, shown once.
flash = st.session_state.pop("flash", None)
if flash:
    kind, message = flash
    (st.success if kind == "success" else st.info)(message, icon=":material/check_circle:")

cfg = ds.build_config()
issues = validate(cfg, store.question_ids(), is_new_question=base is None)
n_errors = sum(i.level == "error" for i in issues)
n_warnings = len(issues) - n_errors
unchanged = base is not None and compute_hash(cfg) == base.content_hash


def issues_for(section, index=None, field=None):
    return [i for i in issues if i.section == section and i.index == index
            and (field is None or i.field == field)]


def _save():
    draft = ds.build_config()
    try:
        saved = store.save_new_version(draft, parent_config_id=ds.base_config_id())
    except ValidationFailed:
        st.session_state.flash = ("info", "Not saved: fix the errors listed in the validation summary.")
        return
    except NoChanges as exc:
        st.session_state.flash = ("info", str(exc))
        return
    st.session_state.active_config_id = saved.config_id
    ds.edit_version(saved)
    st.session_state.flash = ("success", f"Saved {saved.question_id} version {saved.version} "
                                         f"({saved.config_id}). Earlier versions are unchanged.")


def _discard():
    if base is not None:
        ds.edit_version(base)
    else:
        ds.new_blank(store)


# --- Status bar ------------------------------------------------------------
with st.container(border=True):
    left, right = st.columns([3, 2], vertical_alignment="center")
    with left:
        if base is None:
            st.markdown(f"**New question** · not saved yet")
        else:
            st.markdown(f"**{base.question_id}** · editing from version {base.version}"
                        + (" · no unsaved changes" if unchanged else " · :orange[unsaved changes]"))
            if latest and latest.version != base.version:
                st.caption(f"A newer version (v{latest.version}) exists. Saving will create "
                           f"v{latest.version + 1} based on v{base.version}.")
    with right:
        b1, b2 = st.columns(2)
        b1.button("New question", on_click=ds.new_blank, args=(store,), width="stretch",
                  icon=":material/add:")
        b2.button("Discard", on_click=_discard, width="stretch",
                  icon=":material/undo:", disabled=unchanged)

# --- Question --------------------------------------------------------------
st.subheader("Question")
c1, c2 = st.columns([1, 2])
c1.text_input("Question ID", key="w_q_id", disabled=base is not None,
              help="Fixed once saved. Editing a saved question creates a new version with the same ID.")
c2.text_input("Domain", key="w_q_domain")
ui.show_issues(issues_for("question", field="question_id"))

st.text_area("Question prompt", key="w_q_prompt", height=80, placeholder="Enter a typed Bangla question…")
ui.show_issues(issues_for("question", field="prompt"))
st.text_area("Model answer", key="w_q_answer", height=100, placeholder="Enter the reference answer in Bangla…",
             help="Private to the teacher. Never shown in student feedback.")
ui.show_issues(issues_for("question", field="model_answer"))

m1, m2, _ = st.columns([1, 1, 2])
m1.number_input("Maximum mark", key="w_q_max", step=float(ds.get("w_q_inc") or 0.5), format="%g")
m2.selectbox("Mark increment", options=[0.5, 1.0], key="w_q_inc", format_func=fmt,
             help="Maximum mark, caps and penalties must be multiples of this value.")
ui.show_issues(issues_for("question", field="max_mark") + issues_for("question", field="increment"))

step = float(ds.get("w_q_inc") or 0.5)

# --- Weighted concepts -----------------------------------------------------
st.subheader("Weighted concepts")
st.caption("Each concept is credited once. A match is confirmed only when a whole clause matches an "
           "approved clause pattern. Enter one expression or clause per line.")

shares = concept_shares(cfg)
if cfg.concepts:
    st.dataframe(
        [{"Concept": c.id or "—", "Description": c.label, "Weight": c.weight,
          "Share": (s or 0.0) * 100, "Expressions": len(c.expressions), "Clauses": len(c.clauses)}
         for c, s in zip(cfg.concepts, shares)],
        hide_index=True, width="stretch",
        column_config={"Share": st.column_config.ProgressColumn("Share of rubric", format="%.0f%%",
                                                                min_value=0, max_value=100)},
    )
ui.show_issues(issues_for("concepts"))

for idx, uid in enumerate(ds.uids("concepts")):
    k = f"w_{uid}_"
    with st.container(border=True):
        a, b, c, d = st.columns([1, 3, 1, 1], vertical_alignment="bottom")
        a.text_input("ID", key=k + "id")
        b.text_input("Description", key=k + "label", placeholder="What this concept credits")
        c.number_input("Weight", key=k + "weight", step=1.0, format="%g")
        d.button("Remove", key=k + "remove", on_click=ds.remove_item, args=("concepts", uid),
                 icon=":material/delete:", width="stretch")
        share = shares[idx] if idx < len(shares) else None
        st.caption(f"Normalized share: {share * 100:.1f}%" if share is not None else "Normalized share: —")
        e, f = st.columns(2)
        e.text_area("Accepted expressions", key=k + "expr", height=100,
                    help="Short phrases that express this concept, e.g. দুটি হাইড্রোজেন পরমাণু")
        f.text_area("Approved clause patterns", key=k + "clauses", height=100,
                    help="Complete clauses showing a valid use of the expression.")
        st.checkbox("Allow overlap (this concept may share expressions with another concept)", key=k + "overlap")
        ui.show_issues(issues_for("concepts", idx))

st.button("Add concept", on_click=ds.add_item, args=("concepts",), icon=":material/add:")

# --- Required items and wrong ideas ----------------------------------------
concept_ids = [c.id for c in cfg.concepts if c.id]

st.subheader("Required items")
st.caption("If a required item is not confirmed, the mark is capped at its absence cap and the answer is "
           "flagged for review.")
for idx, uid in enumerate(ds.uids("required_items")):
    k = f"w_{uid}_"
    if st.session_state.get(k + "concept") not in concept_ids:
        st.session_state[k + "concept"] = None
    with st.container(border=True):
        a, b, c, d = st.columns([1, 2, 1, 1], vertical_alignment="bottom")
        a.text_input("ID", key=k + "id")
        b.radio("Type", options=["concept", "phrase"], key=k + "kind", horizontal=True,
                format_func={"concept": "Linked concept", "phrase": "Standalone phrase"}.get)
        c.number_input("Absence cap", key=k + "cap", step=step, format="%g")
        d.button("Remove", key=k + "remove", on_click=ds.remove_item, args=("required_items", uid),
                 icon=":material/delete:", width="stretch")
        if ds.get(k + "kind") == "concept":
            st.selectbox("Required concept", options=concept_ids, key=k + "concept",
                         placeholder="Select a concept")
        else:
            e, f = st.columns(2)
            e.text_area("Required phrases", key=k + "phrases", height=90)
            f.text_area("Approved clause patterns", key=k + "clauses", height=90)
        ui.show_issues(issues_for("required_items", idx))
st.button("Add required item", on_click=ds.add_item, args=("required_items",), icon=":material/add:")

st.subheader("Known wrong ideas")
st.caption("A misconception applies its action only when a confirming clause pattern matches. Uncertain, "
           "negated or conflicting evidence is sent to review instead of deducting marks.")
for idx, uid in enumerate(ds.uids("wrong_ideas")):
    k = f"w_{uid}_"
    with st.container(border=True):
        a, b, c, d, e = st.columns([1, 3, 1.3, 1, 1], vertical_alignment="bottom")
        a.text_input("ID", key=k + "id")
        b.text_input("Description", key=k + "label", placeholder="The misconception in plain words")
        c.selectbox("Action", options=["cap", "penalty", "review"], key=k + "action",
                    format_func={"cap": "Cap", "penalty": "Penalty", "review": "Review only"}.get)
        d.number_input("Amount", key=k + "amount", step=step, format="%g",
                       disabled=ds.get(k + "action") == "review")
        e.button("Remove", key=k + "remove", on_click=ds.remove_item, args=("wrong_ideas", uid),
                 icon=":material/delete:", width="stretch")
        f, g = st.columns(2)
        f.text_area("Trigger expressions", key=k + "expr", height=90)
        g.text_area("Confirming clause patterns", key=k + "clauses", height=90)
        ui.show_issues(issues_for("wrong_ideas", idx))
st.button("Add wrong idea", on_click=ds.add_item, args=("wrong_ideas",), icon=":material/add:")

# --- Test this rubric --------------------------------------------------------
# Sample answers from Report Table 4.7 (worked example for question Q01).
SAMPLE_ANSWERS = {
    "A: complete": "পানির একটি অণুতে দুটি হাইড্রোজেন পরমাণু থাকে। পানির একটি অণুতে একটি অক্সিজেন পরমাণু থাকে।",
    "B: partial": "পানির একটি অণুতে দুটি হাইড্রোজেন পরমাণু থাকে।",
    "C: unseen paraphrase": "প্রতিটি জল অণু গঠিত হয় হাইড্রোজেনের দুই পরমাণু ও অক্সিজেনের এক পরমাণু দিয়ে।",
    "D: configured misconception": "পানির একটি অণুতে তিনটি হাইড্রোজেন পরমাণু থাকে।",
    "E: negated misconception": "পানির একটি অণুতে তিনটি হাইড্রোজেন পরমাণু থাকে না।",
}
STATE_LABELS = {CONFIRMED: "✓ Confirmed", CANDIDATE: "? Candidate (review)",
                UNCERTAIN: "? Uncertain (review)", NOT_DETECTED: "– Not detected"}
STATE_TAGS = {CONFIRMED: "✓", CANDIDATE: "?", UNCERTAIN: "?"}


def _load_sample():
    choice = st.session_state.get("preview_sample")
    if choice in SAMPLE_ANSWERS:
        st.session_state.preview_answer = SAMPLE_ANSWERS[choice]


st.subheader("Test this rubric")
st.caption("Paste a sample answer to see which rules its wording would trigger. Exact matching only: no "
           "spelling tolerance, no semantic score and no mark. This checks the rubric; it is not a grading result.")
with st.container(border=True):
    p1, p2 = st.columns([3, 1], vertical_alignment="bottom")
    p1.selectbox("Load a sample answer (Report Table 4.7, question Q01)", list(SAMPLE_ANSWERS),
                 key="preview_sample", index=None, placeholder="Choose a sample…")
    p2.button("Load sample", on_click=_load_sample, icon=":material/input:", width="stretch",
              disabled=not st.session_state.get("preview_sample"))
    st.text_area("Sample answer", key="preview_answer", height=90,
                 placeholder="Type or paste a Bangla answer…")
    answer = st.session_state.get("preview_answer") or ""
    if answer.strip():
        if n_errors:
            st.caption("The rubric still has validation errors, so this preview may be incomplete.")
        results = preview(cfg, answer)
        marks = []
        for r in results:
            if not r.spans or r.state not in STATE_TAGS:
                continue
            if r.rule_type == "Wrong idea":
                css = "wrong" if r.state == CONFIRMED else "check"
            else:
                css = "ok" if r.state == CONFIRMED else "check"
            marks += [(start, end, css, f"{r.rule_id} {STATE_TAGS[r.state]}") for start, end in r.spans]
        ui.highlighted(answer, marks, "Evidence in the answer")
        st.caption("Green: confirmed credit · Amber, dashed: needs review · Red: confirmed misconception. "
                   "Each highlight is also labelled with its rule ID and ✓ or ?.")
        st.dataframe(
            [{"Rule": r.rule_id, "Type": r.rule_type, "Description": r.label,
              "Evidence": STATE_LABELS[r.state], "Effect": r.effect or "—", "Why": r.reason}
             for r in results],
            hide_index=True, width="stretch",
        )
        reasons = review_needed(results)
        if reasons:
            st.markdown("**Would be flagged for teacher review:** " + ui.md_escape("; ".join(reasons)) + ".")
        else:
            st.markdown("**No review triggers from exact evidence.** Semantic-disagreement checks are not "
                        "part of this preview.")

# --- Validation summary and save -------------------------------------------
st.subheader("Validation summary")
with st.container(border=True):
    if n_errors:
        st.markdown(f":red[**{n_errors} error{'s' * (n_errors != 1)}**] must be fixed before saving"
                    + (f" · {n_warnings} warning{'s' * (n_warnings != 1)}" if n_warnings else ""))
    elif n_warnings:
        st.markdown(f":green[**No errors.**] {n_warnings} warning{'s' * (n_warnings != 1)} to review "
                    "(these do not block saving).")
    else:
        st.markdown(":green[**No errors or warnings.**] The rubric is ready to save.")
    st.caption("Checked: IDs, references, weights, mark increments, caps and penalties, "
               "overlaps, and clause collisions between credited and wrong ideas.")
    for issue in issues:
        icon = "🔴" if issue.level == "error" else "🟠"
        st.markdown(f"{icon} **{ui.md_escape(issue.where)}** — {ui.md_escape(issue.message)}")

next_version = (latest.version + 1) if latest else 1
save_label = f"Save as version {next_version}" if base else "Save question (version 1)"
reason = ("Fix the errors above to enable saving." if n_errors
          else "No changes since the loaded version." if unchanged
          else "Saved versions are read-only; later edits create a new version.")
s1, s2 = st.columns([1, 2], vertical_alignment="center")
s1.button(save_label, type="primary", on_click=_save, disabled=bool(n_errors) or unchanged,
          icon=":material/save:", width="stretch")
s2.caption(reason)

ui.footer(ui.active_label(store))
ds.sync()
