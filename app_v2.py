"""TextQuant v2 — 分析终端布局。FRONTEND_V2.md 步骤 1：骨架，所有面板为占位。

v1 的 app.py 保持可用，两者并存直到 v2 完成。
运行: streamlit run app_v2.py
离线自检: env -u ANTHROPIC_API_KEY streamlit run app_v2.py
"""
import json
from pathlib import Path

import streamlit as st

from src.indicators import cached_bundle, grade_components, indicators_for
from src.ui_text import (GRADE_BADGE_COLOR, GRADE_DISCLAIMER, GRADE_READINGS,
                         GRADE_TOOLTIP, INDICATORS)

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "corpus"
DATA = ROOT / "data"
FIGS = ROOT / "figures"

# 左栏底部对齐用的留白高度（Streamlit 没有真正的 sticky，靠固定高度近似）
LEFT_SPACER_PX = 220

st.set_page_config(page_title="TextQuant", layout="wide")


@st.cache_data
def load_bundles():
    """三份预加载报告，按公司切好 claims / sentences / audit。"""
    return cached_bundle()


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

bundles = load_bundles()
bundle = bundles.get(selected["company"]) if selected else None
values = indicators_for(bundle) if bundle else None
grade = grade_components(bundle["claims"], bundle["sentences"]) if bundle else None

with bar_grade:
    with st.container(border=True):
        st.caption("Disclosure grade", help=GRADE_TOOLTIP)
        letter_col, read_col = st.columns([1, 3], vertical_alignment="center")
        if grade:
            letter_col.markdown(f"# :{GRADE_BADGE_COLOR[grade['letter']]}[{grade['letter']}]")
            read_col.write(GRADE_READINGS[grade["letter"]])
            read_col.caption(f"Score {grade['score']:.0f} of 100 — "
                             f"{selected['company']} {selected['doc_type'].replace('_', ' ')}")
        else:
            letter_col.markdown("# —")
            read_col.write("No report selected yet.")

        with st.expander("How this grade is computed"):
            if grade:
                i = grade["inputs"]
                st.dataframe([
                    {"sub-score": "Completeness",
                     "formula": "(1 − C_rate) × 100",
                     "inputs": f"{i['C_claims']} of {i['quantified_claims']} quantified claims "
                               f"are technically true but incomplete (C_rate "
                               f"{i['C_rate']:.2f})",
                     "value": round(grade["completeness"], 1)},
                    {"sub-score": "Promise balance",
                     "formula": "clamp((5 − PVR) / 4, 0, 1) × 100",
                     "inputs": f"PVR {i['pvr']:.2f}; 1 or below scores 100, 5 or above "
                               f"scores 0",
                     "value": round(grade["promise_balance"], 1)},
                    {"sub-score": "Verification",
                     "formula": "clamp(mentions per 100 sentences / 5, 0, 1) × 100",
                     "inputs": f"{i['verification_mentions']} mentions across "
                               f"{i['sentences']:,} sentences "
                               f"({i['verif_per_100_sentences']:.2f} per 100)",
                     "value": round(grade["verification"], 1)},
                ], hide_index=True)
                st.write(f"Mean of the three: **{grade['score']:.1f}** → grade "
                         f"**{grade['letter']}**. Bands: 75 and above A, 55 and above B, "
                         "35 and above C, below 35 D.")
                st.caption("B-class and skipped claims are excluded from completeness: it "
                           "measures quantified claims only. Commitment trackability is "
                           "deliberately excluded — it was near zero for every reference "
                           "report, so it carries no information.")
            st.warning(GRADE_DISCLAIMER)

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
    for col, spec in zip(ind, INDICATORS):
        value = spec["fmt"](values[spec["key"]]) if values else "—"
        col.metric(spec["label"], value, help=spec["help"])
    if not values:
        st.caption("Pick a company above, or upload a report, to fill these in.")

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
