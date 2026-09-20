"""TextQuant v2 — 分析终端布局。FRONTEND_V2.md 步骤 1：骨架，所有面板为占位。

v1 的 app.py 保持可用，两者并存直到 v2 完成。
运行: streamlit run app_v2.py
离线自检: env -u ANTHROPIC_API_KEY streamlit run app_v2.py
"""
import json
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "corpus"
DATA = ROOT / "data"
FIGS = ROOT / "figures"

# 左栏底部对齐用的留白高度（Streamlit 没有真正的 sticky，靠固定高度近似）
LEFT_SPACER_PX = 220

st.set_page_config(page_title="TextQuant", layout="wide")


@st.cache_data
def load_sources():
    return json.loads((CORPUS / "sources.json").read_text(encoding="utf-8"))


def resolve(query, sources):
    """公司名或 ticker 精确匹配，忽略大小写。匹配不到返回 None，绝不报错。"""
    q = (query or "").strip().lower()
    if not q:
        return None
    return next((s for s in sources if q in (s["company"].lower(), s["ticker"].lower())), None)


def panel(title, note, height="content"):
    """占位面板：标题 + 待建说明。步骤 2 起逐个替换。"""
    with st.container(border=True, height=height):
        st.markdown(f"**{title}**")
        st.caption(f"{note} — placeholder, FRONTEND_V2.md build order.")


# ============================================================ TOP BAR
sources = load_sources()
bar_input, bar_grade = st.columns([3, 2], vertical_alignment="center")

with bar_input:
    st.markdown("### TextQuant")
    st.caption("Finds claims that are true and incomplete.")
    row_q, row_go = st.columns([4, 1], vertical_alignment="bottom")
    with row_q:
        query = st.text_input("Company or ticker", placeholder="Alphabet, MSFT, AMZN …",
                              label_visibility="collapsed")
    with row_go:
        analyze = st.button("Analyse", width="stretch")
    upload = st.file_uploader("Or upload a PDF report", type="pdf")
    st.caption("Upload is the primary path. Cached examples: "
               + " · ".join(s["company"] for s in sources))

    selected = resolve(query, sources)
    if query and selected is None:
        st.info(f"No report loaded for **{query}**. Upload their sustainability report as a "
                "PDF, or try one of: "
                + ", ".join(s["company"] for s in sources) + ".")
    elif selected:
        st.success(f"Loaded {selected['company']} — "
                   f"{selected['doc_type'].replace('_', ' ')}, "
                   f"published {selected['published_date']}")
    elif analyze:
        st.info("Type a company or ticker first, or upload a PDF.")

with bar_grade:
    with st.container(border=True):
        st.caption("Disclosure grade",
                   help="Measures how completely this report discloses the basis for its own "
                        "figures. It is not a judgment of environmental performance or of "
                        "the company.")
        grade_letter, grade_read = st.columns([1, 3], vertical_alignment="center")
        grade_letter.markdown("# —")
        grade_read.write("No report selected yet.")
        with st.expander("How this grade is computed"):
            st.caption("Placeholder — the full computation lands in step 3 "
                       "(FRONTEND_V2.md §5).")

st.divider()

# ============================================================ TWO COLUMNS
left, right = st.columns([3, 7])

# ----------------------------------------------------------- LEFT 30%
with left:
    panel("Related sources", "Up to 5 headlines with source and date; offline-safe")
    st.container(height=LEFT_SPACER_PX, border=False)   # 把执行状态推到底部
    panel("Running", "One line per pipeline stage, then a collapsed summary with runtime")

# ---------------------------------------------------------- RIGHT 70%
with right:
    panel("Key terms found", "Pills for accounting terms carrying quantified claims, "
                             "tinted by lift")

    ind = st.columns(4)
    for col, (label, helptext) in zip(ind, [
        ("Claims needing review", "Share of quantified claims that are technically true "
                                  "but incomplete"),
        ("Promises per verification", "Forward-looking statements per assurance mention"),
        ("Verification density", "Sentences between assurance mentions"),
        ("Commitments trackable", "Targets with enough history in the same report to "
                                  "check progress"),
    ]):
        col.metric(label, "—", help=helptext)

    panel("Commitment trajectory", "Target vs observed pace, or the honest empty state")
    panel("Where to look", "Report map: flagged regions by mechanism, plus the passage picker")
    panel("Selected passage", "Quote first, then why it was flagged, then the source")

# ============================================================ BELOW THE FOLD
st.divider()
st.header("How it was evaluated")
panel("Ablation table and confusion matrix", "Carried over from v1 unchanged")

st.divider()
st.header("What this does not claim")
panel("Limitations", "Carried over from v1 unchanged")
