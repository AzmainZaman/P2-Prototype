"""Shared presentation helpers for the teacher console."""
from __future__ import annotations

import html
import os
import re
from pathlib import Path
from typing import Iterable, Optional

import streamlit as st

from grader.store import Store
from grader.validation import Issue

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Bengali:wght@400;600;700&display=swap');
html, body, p, label, input, textarea, td, th, li, h1, h2, h3, h4, .lit {
  font-family: "Source Sans", "Source Sans Pro", "Source Sans 3", "Noto Sans Bengali", sans-serif;
}
.block-container { max-width: 1100px; padding-top: 2.5rem; }
.console-header { background: #16283F; color: #FFFFFF; padding: 14px 22px; border-radius: 6px; margin-bottom: 1.2rem; }
.console-header .kicker { font-size: 0.7rem; letter-spacing: 0.08em; text-transform: uppercase; color: #B8C4D6; font-weight: 600; }
.console-header .title { font-size: 1.4rem; font-weight: 700; line-height: 1.3; }
.lit { white-space: pre-wrap; background: #F0F4F8; border: 1px solid #D5DEE8; border-radius: 6px;
       padding: 10px 14px; line-height: 1.7; margin-bottom: 0.6rem; }
.lit-label { font-size: 0.8rem; font-weight: 600; color: #405066; margin-bottom: 2px; }
.lit mark { padding: 1px 2px; border-radius: 3px; }
.lit mark.ok { background: #D3EFDC; border-bottom: 2px solid #2E7D4F; }
.lit mark.check { background: #FCEBC4; border-bottom: 2px dashed #A86B00; }
.lit mark.wrong { background: #F9D6D5; border-bottom: 2px solid #B3261E; }
.lit .tag { font-size: 0.68rem; font-weight: 700; vertical-align: super; margin: 0 3px 0 1px; color: #405066; }
.console-footer { font-size: 0.75rem; color: #5C6B7E; letter-spacing: 0.03em; margin-top: 2rem;
                  border-top: 1px solid #E1E7EE; padding-top: 0.6rem; }
</style>
"""


@st.cache_resource
def get_store() -> Store:
    config_dir = os.environ.get("GRADER_CONFIG_DIR")
    store = Store(Path(config_dir)) if config_dir else Store()
    store.ensure_seed()
    return store


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(kicker: str, title: str) -> None:
    st.markdown(
        f'<div class="console-header"><div class="kicker">{html.escape(kicker)}</div>'
        f'<div class="title">{html.escape(title)}</div></div>',
        unsafe_allow_html=True,
    )


def literal(text: str, label: Optional[str] = None) -> None:
    """Show teacher/student text exactly as typed; never interpreted as markup (NFR-07)."""
    label_html = f'<div class="lit-label">{html.escape(label)}</div>' if label else ""
    st.html(f'{label_html}<div class="lit">{html.escape(text or "")}</div>')


def highlighted(text: str, marks, label: Optional[str] = None) -> None:
    """Show text literally with highlighted spans.

    `marks` is a list of (start, end, css_class, tag). Each run is followed by a
    text tag such as "C1 ✓" so status is never conveyed by colour alone.
    """
    owners = [[] for _ in range(len(text))]
    for start, end, css, tag in marks:
        for i in range(start, end):
            owners[i].append((css, tag))
    priority = {"wrong": 0, "check": 1, "ok": 2}
    parts, i = [], 0
    while i < len(text):
        j = i
        while j < len(text) and owners[j] == owners[i]:
            j += 1
        chunk = html.escape(text[i:j])
        if owners[i]:
            css = min((c for c, _ in owners[i]), key=priority.get)
            tags = " ".join(dict.fromkeys(t for _, t in owners[i]))
            parts.append(f'<mark class="{css}">{chunk}</mark><span class="tag">{html.escape(tags)}</span>')
        else:
            parts.append(chunk)
        i = j
    label_html = f'<div class="lit-label">{html.escape(label)}</div>' if label else ""
    st.html(f'{label_html}<div class="lit">{"".join(parts)}</div>')


_MD_SPECIAL =re.compile(r"([\\`*_{}\[\]()#+\-.!|<>~$:])")


def md_escape(text: str) -> str:
    """Escape Markdown so teacher-entered text inside messages is shown literally."""
    return _MD_SPECIAL.sub(r"\\\1", text or "")


def show_issues(issues: Iterable[Issue]) -> None:
    for issue in issues:
        if issue.level == "error":
            st.error(md_escape(issue.message), icon=":material/error:")
        else:
            st.warning(md_escape(issue.message), icon=":material/warning:")


def footer(active_label: str) -> None:
    st.markdown(
        '<div class="console-footer">LOCAL DEMONSTRATION &nbsp;|&nbsp; '
        f"{html.escape(active_label)} &nbsp;|&nbsp; Retention notice: configurations are stored as "
        "local files in data/configs. No student answers are collected in this build.</div>",
        unsafe_allow_html=True,
    )


def active_label(store: Store) -> str:
    config_id = st.session_state.get("active_config_id")
    cfg = store.load(config_id) if config_id else None
    return f"Active question: {cfg.question_id} v{cfg.version}" if cfg else "No question selected"
