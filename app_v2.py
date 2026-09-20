"""TextQuant v2 — 分析终端布局。FRONTEND_V2.md 步骤 1：骨架，所有面板为占位。

v1 的 app.py 保持可用，两者并存直到 v2 完成。
运行: streamlit run app_v2.py
离线自检: env -u ANTHROPIC_API_KEY streamlit run app_v2.py
"""
import json
from pathlib import Path

import streamlit as st

from src.indicators import (cached_bundle, claims_needing_review, grade_components,
                            indicators_for, promises_per_verification, verification_density)
from src.pipeline import MAX_CLAIM_SENTENCES, analyse
from src.report_map import load_regions, region_option, render_map, span_caption
from src.ui_text import mechanism_of_region
from src.ui_text import (STAGES, KEY_TERMS, KEY_TERM_QUALIFIER, term_hover, term_pill,
                         mechanism_badge, say_mechanism, why_flagged,
                         GRADE_BADGE_COLOR, GRADE_DISCLAIMER, GRADE_READINGS,
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


@st.cache_data(show_spinner=False)
def analyse_upload(file_bytes, filename, _on_stage=None):
    """按文件字节缓存，同一份 PDF 再传是瞬时的。_on_stage 不参与缓存键。"""
    result = analyse(file_bytes, filename, on_stage=_on_stage)
    for r in result["regions"]:
        r["mechanism"] = mechanism_of_region(r.get("flag_types", {}))
    return result


def upload_indicators(result):
    """上传路径的四个指标。轨迹扫描不在上传流程里，第四项返回 None。"""
    rows, claims = result["rows"], result["claims"]
    return {"claims_needing_review": claims_needing_review(claims) if claims else None,
            "promises_per_verification": promises_per_verification(rows),
            "verification_density": verification_density(rows),
            "commitments_trackable": None}


@st.cache_data
def load_gaps():
    path = DATA / "trajectory_gaps.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


@st.cache_data
def load_term_risk():
    """Track S 的 lift 表。没跑过就返回 None，药丸退化为不着色。"""
    path = DATA / "term_risk.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def key_terms_present(sentences, term_risk):
    """§4.1：本报告里出现、且承载量化声明的会计术语。"""
    blob = " ".join(s["text"] for s in sentences).lower()
    out = []
    for term in KEY_TERMS:
        n = blob.count(term.lower())
        if not n:
            continue
        lift = cooc = None
        if term_risk:
            q = KEY_TERM_QUALIFIER.get(term, "verifier_named")
            row = next((r for r in term_risk["terms"].get(q, [])
                        if r["term"] == term.lower()), None)
            if row:
                lift, cooc = row["lift"], row["cooc"]
        out.append({"term": term, "count": n, "lift": lift, "cooc": cooc})
    return sorted(out, key=lambda t: (t["lift"] if t["lift"] is not None else 9, -t["count"]))


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

with bar_grade:
    grade_slot = st.container(border=True)   # 上传时管线跑完再填


def render_grade(slot, grade, subject, blocked=None):
    with slot:
        st.caption("Disclosure grade", help=GRADE_TOOLTIP)
        letter_col, read_col = st.columns([1, 3], vertical_alignment="center")
        if grade:
            letter_col.markdown(f"# :{GRADE_BADGE_COLOR[grade['letter']]}[{grade['letter']}]")
            read_col.write(GRADE_READINGS[grade["letter"]])
            read_col.caption(f"Score {grade['score']:.0f} of 100 — {subject}")
        else:
            letter_col.markdown("# —")
            read_col.write(blocked or "No report selected yet.")

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
    with st.container(border=True):
        st.markdown("**Running**")
        if upload is not None:
            lines = st.container()
            def stage(name, detail):
                lines.caption(f"✓ {name} — {detail}")
            try:
                uploaded = analyse_upload(upload.getvalue(), upload.name, _on_stage=stage)
                st.session_state.upload_result = uploaded
                if uploaded.get("extract_error"):
                    lines.caption("○ Classifying claims — live extraction unavailable; "
                                  "the rule stages above still ran with no network")
                else:
                    lines.caption(f"Claim extraction was capped at the first "
                                  f"{MAX_CLAIM_SENTENCES} qualifying sentences.")
                st.caption(f"Cached by file contents — re-uploading {upload.name} is instant.")
            except Exception as exc:
                st.caption(f"○ Could not read that PDF ({type(exc).__name__}).")
                st.session_state.upload_result = None
        else:
            stage_values = {
                "sentences": sum(len(b["sentences"]) for b in bundles.values()) if not bundle
                             else len(bundle["sentences"]),
                "regions": len(load_regions([selected["company"]] if selected else None)),
                "claims": len(bundle["claims"]) if bundle else sum(len(b["claims"])
                                                                   for b in bundles.values()),
                "commitments": len(bundle["audit"]) if bundle else sum(len(b["audit"])
                                                                       for b in bundles.values()),
            }
            for name, detail in STAGES:
                st.caption(f"✓ {name} — {detail.format(**stage_values)}")
            st.caption("Cached run — these stages were computed ahead of time and read from "
                       "disk, so the page works with no network.")

uploaded = st.session_state.get("upload_result") if upload is not None else None
values = (upload_indicators(uploaded) if uploaded
          else (indicators_for(bundle) if bundle else None))
# 没有 claim 时 completeness 的分母为空，公式会退化成满分 —— 宁可不给字母
grade = None
blocked = None
if uploaded:
    if uploaded["claims"]:
        grade = grade_components(uploaded["claims"], uploaded["rows"])
    else:
        blocked = ("Grade needs the claim classification stage, which did not run. "
                   "The measured indicators are shown on the right.")
elif bundle:
    grade = grade_components(bundle["claims"], bundle["sentences"])
subject = (f"{uploaded['filename']} (uploaded)" if uploaded
           else (f"{selected['company']} {selected['doc_type'].replace('_', ' ')}"
                 if selected else ""))
render_grade(grade_slot, grade, subject, blocked)

# ---------------------------------------------------------- RIGHT 70%
with right:
    with st.container(border=True):
        st.markdown("**Key terms found**")
        term_risk = load_term_risk()
        sents = (uploaded["rows"] if uploaded else
                 (bundle["sentences"] if bundle
                  else [s for b in bundles.values() for s in b["sentences"]]))
        terms = key_terms_present(sents, term_risk)
        if terms:
            st.markdown(" ".join(term_pill(t["term"], t["lift"]) for t in terms))
            with st.expander("What the colours mean"):
                st.caption("Amber marks a term that usually appears without the qualifier "
                           "it needs — the method, the scope or the verifier. Grey marks a "
                           "term that normally travels with its qualifier."
                           if term_risk else
                           "Language statistics have not been computed for this report, so "
                           "the pills are not tinted.")
                for t in terms:
                    st.caption(term_hover(t["term"], t["lift"], t["count"], t["cooc"]))
        else:
            st.caption("No accounting terms from the vocabulary appear in this report.")

    ind = st.columns(4)
    for col, spec in zip(ind, INDICATORS):
        v = values.get(spec["key"]) if values else None
        col.metric(spec["label"], spec["fmt"](v) if v is not None else "—",
                   help=spec["help"])
    if not values:
        st.caption("Pick a company above, or upload a report, to fill these in.")
    elif uploaded:
        st.caption("Commitments trackable needs the trajectory pass, which is not part of "
                   "the upload flow — the other three are computed from your report.")

    with st.container(border=True):
        st.markdown("**Commitment trajectory**")
        if uploaded:
            audit, gaps = [], []
        else:
            audit = (bundle["audit"] if bundle
                     else [a for b in bundles.values() for a in b["audit"]])
            gaps = [g for g in load_gaps()
                    if not selected or g["company"] == selected["company"]]
        n_targets = len(audit)
        n_zero = sum(a["reason"] == "no_observations" for a in audit)
        n_one = sum(a["reason"] == "only_one_observation" for a in audit)
        n_two = sum(a["outcome"] == "kept" for a in audit)

        # 少于三个观测点不拟合趋势线（§4.4 / §9）
        plottable = [g for g in gaps if g.get("observations_found", 2) >= 3]

        if uploaded:
            st.markdown(f"**{uploaded['n_commitments']} quantified commitments found in "
                        f"this report.**")
            st.caption("Checking whether each one can be progress-checked needs the "
                       "trajectory pass — two further LLM stages over the whole document. "
                       "It is not part of the upload flow.")
        elif n_targets == 0:
            st.caption("No quantified commitments were extracted from this report.")
        else:
            st.markdown(f"**{n_zero + n_one} of {n_targets} quantified commitments have no "
                        f"trackable history in this report.** A target is stated; the figures "
                        f"needed to check progress against it are not in the same document.")
            st.dataframe([
                {"observations in the same report": "none", "commitments": n_zero,
                 "share": f"{n_zero / n_targets:.0%}"},
                {"observations in the same report": "one", "commitments": n_one,
                 "share": f"{n_one / n_targets:.0%}"},
                {"observations in the same report": "two or more", "commitments": n_two,
                 "share": f"{n_two / n_targets:.0%}"},
            ], hide_index=True)

            if plottable:
                st.image(str(FIGS / "trajectory_gap.png"))
            elif gaps:
                st.caption(f"{len(gaps)} commitment(s) reached two observations — too few "
                           "points to fit a pace line, so none is drawn. The pairs are "
                           "listed below for inspection.")
                for g in gaps:
                    st.caption(f"{g['metric']}: {g['prior_year']} {g['prior_value']:g} → "
                               f"{g['latest_year']} {g['latest_value']:g}, target "
                               f"{g['target_value']:g}{g['unit']} by {g['target_year']}")

    # ---- Where to look（步骤 4：从 v1 原样移植）
    with st.container(border=True):
        if uploaded:
            regions = uploaded["regions"]
            counts = {uploaded["company"]: uploaded["n_sentences"]}
        else:
            regions = load_regions([selected["company"]] if selected else None)
            counts = ({selected["company"]: len(bundle["sentences"])} if bundle
                      else {c: len(b["sentences"]) for c, b in bundles.items()})
        if regions:
            st.markdown(f"**{len(regions)} passages need review**")
            st.caption(f"Out of {sum(counts.values()):,} sentences across {len(counts)} "
                       f"report{'s' if len(counts) > 1 else ''}.")
            st.pyplot(render_map(regions, counts), width="stretch")
            st.caption(span_caption(regions))
            pick = st.selectbox("Jump to a passage", options=range(len(regions)),
                                format_func=lambda i: region_option(regions[i]),
                                key=f"v2_region_{'upload' if uploaded else 'cached'}")
            st.session_state.selected_region = regions[pick]
        else:
            st.markdown("**No passages crossed the review threshold**")
            st.session_state.selected_region = None

    # ---- Selected passage（步骤 4：顺序不变，公司自己的话在前）
    with st.container(border=True):
        region = st.session_state.get("selected_region")
        if not region:
            st.markdown("**Selected passage**")
            st.caption("Pick a passage above.")
        else:
            source = None if uploaded else next(
                (x for x in sources if x["company"] == region["company"]), None)
            lo, hi = (p * 100 for p in region["rel_pos"])
            st.markdown(f"{mechanism_badge(region['mechanism'])} &nbsp; "
                        f"**{region['company']}** · {lo:.0f}–{hi:.0f}% into the report "
                        f"· {region['n_sentences']} sentences")
            st.markdown(f"> {region['text']}")
            st.caption("Excerpt, first 400 characters of the passage.")
            st.markdown("**Why it was flagged**")
            st.write(why_flagged(region.get("flag_types", {}), region["n_sentences"]))
            if uploaded:
                st.caption(f"Source: {uploaded['filename']} (uploaded this session; "
                           "no publication date available)")
            elif source:
                st.caption(f"Source: {source['company']} "
                           f"{source['doc_type'].replace('_', ' ')} "
                           f"({Path(source['file']).name}) · published "
                           f"{source['published_date']}")
            with st.expander("Technical detail"):
                st.write({"sent_id_range": [region["start_sent_id"], region["end_sent_id"]],
                          "rel_pos": region["rel_pos"], "peak_flag_density": region["peak"],
                          "threshold": region["threshold"],
                          "flag_counts": region.get("flag_types", {}),
                          "mechanism": region["mechanism"]})

# ============================================================ BELOW THE FOLD
st.divider()
st.header("How it was evaluated")
panel("Ablation table and confusion matrix", "Carried over from v1 unchanged")

st.divider()
st.header("What this does not claim")
panel("Limitations", "Carried over from v1 unchanged")
