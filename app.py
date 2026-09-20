"""TextQuant — Streamlit 界面。FRONTEND.md 步骤 1：骨架（页头、输入行、七个空区块）。

运行: streamlit run app.py
离线自检: env -u ANTHROPIC_API_KEY streamlit run app.py
"""
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import streamlit as st

from src.ui_text import (MECHANISM_COLORS, PRESETS, mechanism_of_region, say_mechanism,
                         why_flagged)

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "corpus"
DATA = ROOT / "data"
MIN_MARK_PX = 8

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


@st.cache_data
def load_regions():
    regions = json.loads((DATA / "anomaly_regions.json").read_text(encoding="utf-8"))
    for r in regions:
        r["mechanism"] = mechanism_of_region(r.get("flag_types", {}))
    regions.sort(key=lambda r: (r["company"], r["rel_pos"][0]))
    return regions


@st.cache_data
def load_sentence_counts():
    rows = json.loads((DATA / "signals.json").read_text(encoding="utf-8"))
    return Counter(r["company"] for r in rows)


def render_map(regions, counts):
    """每家一条 0→1 的横条，命中区间画成色块。窄区间加宽到 8px 以便点选。"""
    companies = list(counts)
    fig, ax = plt.subplots(figsize=(10, 0.9 * len(companies) + 1.1))
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.6, len(companies) - 0.4)

    # 先布局再量轴宽，才能把 8px 换算成数据单位
    fig.canvas.draw()
    ax_px = ax.get_window_extent(fig.canvas.get_renderer()).width
    min_w = MIN_MARK_PX / ax_px if ax_px else 0.006

    for y, company in enumerate(companies):
        ax.barh(y, 1.0, height=0.34, color="#e9ecef", zorder=1)
        for r in regions:
            if r["company"] != company:
                continue
            start, end = r["rel_pos"]
            width = max(end - start, min_w)
            ax.barh(y, width, left=start, height=0.34, zorder=2,
                    color=MECHANISM_COLORS.get(r["mechanism"], "#9498a0"))

    ax.set_yticks(range(len(companies)), companies)
    ax.invert_yaxis()   # 第一家排在最上，符合阅读顺序
    ax.set_xticks([0, 1], ["start of report", "end"])
    ax.tick_params(axis="x", length=0)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)

    seen = [m for m in MECHANISM_COLORS if any(r["mechanism"] == m for r in regions)]
    ax.legend([Line2D([0], [0], color=MECHANISM_COLORS[m], lw=7) for m in seen],
              [say_mechanism(m) for m in seen],
              loc="upper center", bbox_to_anchor=(0.5, -0.12),
              ncol=len(seen) or 1, frameon=False, fontsize=9)
    fig.tight_layout()
    return fig


def region_option(r):
    pct = round(r["rel_pos"][0] * 100)
    return f"{r['company']} · {pct}% into report · {say_mechanism(r['mechanism'])}"


def badge(text, color):
    return (f"<span style='background:{color};color:white;padding:2px 10px;"
            f"border-radius:10px;font-size:0.85em'>{text}</span>")


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
    analyze = st.button("Analyze", width="stretch")
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
regions = load_regions()
counts = load_sentence_counts()

st.header(f"{len(regions)} passages need review")
st.caption(f"Out of {sum(counts.values()):,} sentences across {len(counts)} reports.")

st.pyplot(render_map(regions, counts), width="stretch")

spans = [(r["rel_pos"][1] - r["rel_pos"][0]) * 100 for r in regions]
st.caption(
    f"Each block marks a run of sentences where accounting-disclosure flags cluster. "
    f"True spans run from {min(spans):.1f}% to {max(spans):.1f}% of a report "
    f"({min(r['n_sentences'] for r in regions)}–{max(r['n_sentences'] for r in regions)} "
    f"sentences); narrow blocks are widened to {MIN_MARK_PX}px so they stay visible."
)

choice = st.selectbox("Jump to a passage", options=range(len(regions)),
                      format_func=lambda i: region_option(regions[i]),
                      key="region_choice")
st.session_state.selected_region = regions[choice]

st.divider()
st.header("What this passage says, and what it leaves out")

region = st.session_state.get("selected_region")
if not region:
    st.info("Pick a passage above.")
else:
    source = next((s for s in sources if s["company"] == region["company"]), None)
    start_pct, end_pct = (p * 100 for p in region["rel_pos"])

    st.markdown(
        badge(say_mechanism(region["mechanism"]),
              MECHANISM_COLORS.get(region["mechanism"], "#9498a0"))
        + f" &nbsp;**{region['company']}** &nbsp;·&nbsp; {start_pct:.0f}–{end_pct:.0f}% "
          f"into the report &nbsp;·&nbsp; {region['n_sentences']} sentences",
        unsafe_allow_html=True)

    # 公司自己的话在前，解释在后
    st.markdown(f"> {region['text']}")
    st.caption("Excerpt, first 400 characters of the passage.")

    st.markdown("**Why it was flagged**")
    st.write(why_flagged(region.get("flag_types", {}), region["n_sentences"]))

    if source:
        st.caption(f"Source: {source['company']} {source['doc_type'].replace('_', ' ')} "
                   f"({Path(source['file']).name}) · published {source['published_date']}")

    with st.expander("Technical detail"):
        st.write({"sent_id_range": [region["start_sent_id"], region["end_sent_id"]],
                  "rel_pos": region["rel_pos"],
                  "n_sentences": region["n_sentences"],
                  "peak_flag_density": region["peak"],
                  "threshold": region["threshold"],
                  "flag_counts": region.get("flag_types", {}),
                  "mechanism": region["mechanism"]})

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
