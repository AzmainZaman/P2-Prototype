"""Teacher console for the Bangla short-answer grading prototype.

Run with:  streamlit run app.py
"""
import streamlit as st

import ui

st.set_page_config(page_title="Teacher Console · Bangla Grading Assistant", page_icon="📝", layout="wide")
ui.inject_css()
ui.get_store()  # creates data/configs and loads the seed example on first run

pages = [
    st.Page("views/home.py", title="Home", icon=":material/home:", default=True),
    st.Page("views/editor.py", title="Question editor", url_path="editor", icon=":material/edit_note:"),
    st.Page("views/library.py", title="Question library", url_path="library", icon=":material/library_books:"),
]
st.navigation(pages).run()
