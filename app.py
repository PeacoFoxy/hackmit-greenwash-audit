"""TextQuant — Streamlit 界面。FRONTEND.md 步骤 1：骨架（页头、输入行、七个空区块）。

运行: streamlit run app.py
离线自检: env -u ANTHROPIC_API_KEY streamlit run app.py
"""
import json
from pathlib import Path

import streamlit as st

from src.ui_text import PRESETS

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "corpus"

st.set_page_config(page_title="TextQuant", layout="wide")


@st.cache_data
def load_sources():
    return json.loads((CORPUS / "sources.json").read_text(encoding="utf-8"))


def resolve(query, sources):
    """公司名或 ticker 精确匹配，忽略大小写。匹配不到返回 None，绝不报错。"""
    q = (query or "").strip().lower()
    if not q:
        return None
    for s in sources:
        if q in (s["company"].lower(), s["ticker"].lower()):
            return s
    return None


def placeholder(note):
    st.info(f"_{note}_ — not built yet (FRONTEND.md build order).")


# ------------------------------------------------------------------ HEADER
st.title("TextQuant")
st.markdown(
    "Finds claims that are true and incomplete. Nothing is false, so "
    "fact-checking doesn't fire. Nothing is obviously vague, so a reader "
    "doesn't either."
)

# --------------------------------------------------------------- INPUT ROW
sources = load_sources()
col_q, col_go, col_up = st.columns([3, 1, 2])
with col_q:
    query = st.text_input("Company or ticker", placeholder="Alphabet, MSFT, AMZN …",
                          label_visibility="collapsed")
with col_go:
    analyze = st.button("Analyze", use_container_width=True)
with col_up:
    upload = st.file_uploader("Or upload a PDF report", type="pdf",
                              label_visibility="collapsed")

st.caption("Preloaded: " + " · ".join(s["company"] for s in sources))

selected = resolve(query, sources)
if upload is not None:
    st.warning("Upload analysis is not wired up yet — it is the last build step. "
               "The three preloaded reports work today.")
elif query and selected is None:
    st.info("No report loaded for that name. Preloaded reports: "
            + ", ".join(f"{s['company']} ({s['ticker']})" for s in sources)
            + ". Anything else, upload the PDF above.")
elif selected:
    st.success(f"Loaded {selected['company']} — {selected['doc_type'].replace('_', ' ')}, "
               f"published {selected['published_date']}")
elif analyze:
    st.info("Type a company or ticker first, or upload a PDF.")

st.divider()

# ------------------------------------------------------------- SECTION 1-7
st.header("Which passages need review")
placeholder("Report map: one strip per company, marks coloured by mechanism")

st.divider()
st.header("What this passage says, and what it leaves out")
placeholder("Passage detail: quote with the trigger highlighted, then why it was flagged")

st.divider()
st.header("Try a claim")
st.caption("Presets: " + " · ".join(p["button"] for p in PRESETS))
placeholder("Claim classifier: four presets from cache plus a free-text box")

st.divider()
st.header("How the three reports compare")
placeholder("Cross-company signals: promises per verification, three-panel figure")

st.divider()
st.header("Can these commitments be progress-checked?")
placeholder("Commitment verifiability: the 57-of-59 headline and the bar chart")

st.divider()
st.header("How it was evaluated")
placeholder("Ablation table, confusion matrix, three short paragraphs")

st.divider()
st.header("What this does not claim")
placeholder("Limitations, stated on screen rather than buried in the README")
