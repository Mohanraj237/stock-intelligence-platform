from __future__ import annotations

import sys
from pathlib import Path
import streamlit as st

# ROOT PROJECT PATH FIX
ROOT_DIR = Path(__file__).resolve().parents[1]

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def apply_page_config(title: str):
    st.set_page_config(
        page_title=title,
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(
        """
        <style>
        .block-container {padding-top:1rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def sidebar_footer():
    st.sidebar.markdown("---")
    st.sidebar.caption("Educational analytics only. Not investment advice.")