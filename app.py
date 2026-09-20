"""TextQuant -- the v1 Streamlit interface: three preloaded reports plus a live pipeline
for uploaded PDFs.

Run:            streamlit run app.py
Offline check:  env -u ANTHROPIC_API_KEY streamlit run app.py
"""
import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import streamlit as st

from src.claim_api import classify_claim, is_cached
from src.pipeline import analyse
from src.plot_signals import draw_overlay
from src.ui_text import (MECHANISM_COLORS, PRESETS, label_badge, mechanism_badge,
                         mechanism_of_region, say_mechanism, why_flagged)

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "corpus"
DATA = ROOT / "data"
FIGS = ROOT / "figures"
MIN_MARK_PX = 8

st.set_page_config(page_title="TextQuant", layout="wide")


@st.cache_data
def load_sources():
    return json.loads((CORPUS / "sources.json").read_text(encoding="utf-8"))


def resolve(query, sources):
    """Exact match on company name or ticker, case-insensitive. Returns None on no match;
    never raises."""
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
def load_company_stats():
    """Company-level PVR and friends, sorted by PVR descending."""
    rows = json.loads((DATA / "anomaly_company.json").read_text(encoding="utf-8"))
    return sorted(rows, key=lambda r: -r["pvr"])


@st.cache_data
def load_audit():
    return json.loads((DATA / "trajectory_audit.json").read_text(encoding="utf-8"))


@st.cache_data
def load_gaps():
    return json.loads((DATA / "trajectory_gaps.json").read_text(encoding="utf-8"))


@st.cache_data
def load_metrics():
    return json.loads((DATA / "metrics.json").read_text(encoding="utf-8"))


@st.cache_data
def load_sentence_counts():
    rows = json.loads((DATA / "signals.json").read_text(encoding="utf-8"))
    return Counter(r["company"] for r in rows)


@st.cache_data(show_spinner=False)
def analyse_upload(file_bytes, filename, _on_stage=None):
    """Keyed on file contents, so re-uploading the same PDF is instant. _on_stage is
    excluded from the cache key."""
    result = analyse(file_bytes, filename, on_stage=_on_stage)
    for r in result["regions"]:
        r["mechanism"] = mechanism_of_region(r.get("flag_types", {}))
    return result


def render_map(regions, counts):
    """One 0-to-1 bar per company, with hits drawn as blocks. Narrow spans are widened to
    8px so they stay clickable."""
    companies = list(counts)
    fig, ax = plt.subplots(figsize=(10, 0.9 * len(companies) + 1.1))
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.6, len(companies) - 0.4)

    # Lay out first, then measure the axis width, so 8px can be converted to data units
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
    ax.invert_yaxis()   # first company on top, matching reading order
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


def run_claim(text):
    """Classify one claim and store the result in session_state. Failures become a notice,
    never a traceback."""
    cached = is_cached(text)
    try:
        r = classify_claim(text)
        st.session_state.claim_result = {**r, "claim": text.strip()}
    except Exception as exc:
        st.session_state.claim_result = {
            "error": ("Live analysis unavailable — showing nothing rather than guessing. "
                      f"({type(exc).__name__}) "
                      + ("This claim is not in the local cache."
                         if not cached else "Cached result could not be read.")),
            "claim": text.strip()}


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
uploaded = None
if upload is not None:
    with st.status(f"Analysing {upload.name}", expanded=True) as status:
        try:
            uploaded = analyse_upload(upload.getvalue(), upload.name,
                                      _on_stage=lambda n, d: st.write(f"**{n}** — {d}"))
            if uploaded.get("extract_error"):
                st.write("**Classifying claims** — live extraction unavailable; the rule "
                         "layers above still ran with no network.")
            status.update(label=f"{upload.name}: {uploaded['n_sentences']:,} sentences, "
                                f"{len(uploaded['regions'])} passages to review",
                          state="complete")
        except Exception as exc:
            status.update(label="Could not read that PDF", state="error")
            st.warning(f"Upload analysis failed ({type(exc).__name__}). "
                       "The three preloaded reports below still work.")
elif query and selected is None:
    st.info("No report loaded for that name. Preloaded reports: "
            + ", ".join(f"{s['company']} ({s['ticker']})" for s in sources)
            + ". Anything else, upload the PDF above.")
elif selected:
    st.success(f"Loaded {selected['company']} — {selected['doc_type'].replace('_', ' ')}, "
               f"{selected.get('title') or ''}")
elif analyze:
    st.info("Type a company or ticker first, or upload a PDF.")

st.divider()

# ------------------------------------------------------------- SECTION 1-7
# A successful upload switches the whole page to that document; otherwise the preloaded
# path is used. Both have to work.
if uploaded:
    regions = uploaded["regions"]
    counts = Counter({uploaded["company"]: uploaded["n_sentences"]})
    st.caption(f"Showing your upload: {uploaded['filename']}. "
               "Reload the page to go back to the preloaded reports.")
else:
    regions = load_regions()
    counts = load_sentence_counts()

has_regions = bool(regions)
if not has_regions:
    st.header("No passages crossed the review threshold")
    st.caption(f"Out of {sum(counts.values()):,} sentences. The flag density in this report "
               "never rose two standard deviations above its own mean.")
else:
    st.header(f"{len(regions)} passages need review")
    st.caption(f"Out of {sum(counts.values()):,} sentences across {len(counts)} "
               f"report{'s' if len(counts) > 1 else ''}.")

if has_regions:
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
                          key=f"region_choice_{'upload' if uploaded else 'preloaded'}")
    st.session_state.selected_region = regions[choice]
else:
    st.session_state.selected_region = None

st.divider()
st.header("What this passage says, and what it leaves out")

region = st.session_state.get("selected_region")
if not region:
    st.info("Pick a passage above.")
else:
    source = next((s for s in sources if s["company"] == region["company"]), None)
    start_pct, end_pct = (p * 100 for p in region["rel_pos"])

    st.markdown(f"{mechanism_badge(region['mechanism'])} &nbsp; **{region['company']}** "
                f"· {start_pct:.0f}–{end_pct:.0f}% into the report "
                f"· {region['n_sentences']} sentences")

    # The company's own words first, the explanation after
    st.markdown(f"> {region['text']}")
    st.caption("Excerpt, first 400 characters of the passage.")

    st.markdown("**Why it was flagged**")
    st.write(why_flagged(region.get("flag_types", {}), region["n_sentences"]))

    if uploaded:
        st.caption(f"Source: {uploaded['filename']} (uploaded this session; "
                   "no publication date available)")
    elif source:
        st.caption(f"Source: {source['company']} {source['doc_type'].replace('_', ' ')} "
                   f"({Path(source['file']).name})")

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
st.caption("The four presets read from the local cache, so they work with no network. "
           "Free text is a live call.")

with st.container(horizontal=True):
    for i, p in enumerate(PRESETS):
        if st.button(p["button"], key=f"preset_{i}"):
            run_claim(p["claim"])

free_text = st.text_area("Or paste a claim", height=80,
                         placeholder="Paste one sentence from a sustainability report …")
if st.button("Classify", key="classify_free"):
    if free_text.strip():
        run_claim(free_text)
    else:
        st.info("Paste a claim first, or press one of the presets.")

result = st.session_state.get("claim_result")
if result and result.get("error"):
    st.warning(result["error"])
elif result:
    st.markdown(f"> {result['claim']}")
    st.markdown(label_badge(result["label"])
                + ("  :gray-badge[from cache]" if result["cached"] else ""))
    st.write(result["reasoning"])
    with st.expander("Raw model output"):
        st.code(result["raw"], language="json")

# ---------------------------------------------------- 4 · cross-company signals
st.divider()
st.header("How the three reports compare")

if uploaded:
    st.caption("Computed from your upload. The preloaded three-report comparison is only "
               "available for the bundled reports.")
    us = uploaded["company_stats"][0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Promises per verification", f"{us['pvr']:.2f}")
    c2.metric("Sentences per forward-looking claim", f"{us['future_interval']:.0f}")
    c3.metric("Sentences per verification mention", f"{us['verification_interval']:.0f}")

    fig, ax = plt.subplots(figsize=(10, 3.4))
    draw_overlay(ax, uploaded["rows"], uploaded["company"], legend=True)
    ax.set_xlabel("Relative position in report")
    fig.tight_layout()
    st.pyplot(fig, width="stretch")
    st.caption("Promises in blue, third-party verification in green, for this report only.")

company_stats = load_company_stats()
for col, s in zip(st.columns(len(company_stats)), company_stats):
    col.metric("Promises per verification", f"{s['pvr']:.2f}", label_visibility="visible",
               help=f"{s['future_total']} forward-looking markers, "
                    f"{s['verification_total']} verification mentions")
    col.caption(s["company"])

most, least = company_stats[0], company_stats[-1]
st.caption(
    f"{most['company']} makes a forward-looking claim every {most['future_interval']:.0f} "
    f"sentences and mentions third-party verification every "
    f"{most['verification_interval']:.0f}. {least['company']} is the reverse: every "
    f"{least['future_interval']:.0f} sentences against every "
    f"{least['verification_interval']:.0f}."
)

st.markdown("**The three preloaded reports**" if uploaded else "")
st.image(str(FIGS / "sig_overlay_all.png"))
st.caption("Promises in blue, third-party verification in green, on shared axes. Two reports "
           "pivot to verification in the back half; the third has no such section.")

# ------------------------------------------------ 5 · commitment verifiability
st.divider()
st.header("Can these commitments be progress-checked?")

if uploaded:
    st.subheader(f"{uploaded['n_commitments']} quantified commitments found in this report.")
    st.write("Checking whether each one can be progress-checked needs the trajectory pass "
             "(two LLM stages over the whole document). That runs offline on the preloaded "
             "reports below; it is not run for uploads.")

audit = load_audit()
n_targets = len(audit)
n_zero = sum(a["reason"] == "no_observations" for a in audit)
n_one = sum(a["reason"] == "only_one_observation" for a in audit)
n_kept = sum(a["outcome"] == "kept" for a in audit)
n_untrackable = n_zero + n_one

st.markdown("**The three preloaded reports**" if uploaded else "")
st.subheader(f"{n_untrackable} of {n_targets} quantified commitments cannot be "
             f"progress-checked from the report that makes them.")

st.dataframe([
    {"observations found in the same report": "none",
     "commitments": n_zero, "share": f"{n_zero / n_targets:.0%}"},
    {"observations found in the same report": "one",
     "commitments": n_one, "share": f"{n_one / n_targets:.0%}"},
    {"observations found in the same report": "two (enough to measure pace)",
     "commitments": n_kept, "share": f"{n_kept / n_targets:.0%}"},
], hide_index=True)

st.image(str(FIGS / "commitment_verifiability.png"))

with st.expander(f"The {n_kept} that did produce a trajectory are extraction errors"):
    for g in load_gaps():
        st.markdown(f"**{g['company']} — {g['metric']}**  \n"
                    f"{g['prior_year']}: {g['prior_value']:g} → {g['latest_year']}: "
                    f"{g['latest_value']:g}, target {g['target_value']:g}{g['unit']} "
                    f"by {g['target_year']} · status `{g['status']}`")
    st.write("The extractor read a baseline-relative reduction as a level, and a prior-year "
             "achieved value as a target. That is the same ambiguity the rule layer exists to "
             "detect — a figure whose boundary is not stated can be read two ways. Counting "
             "these as real trajectories would overstate what the corpus supports, so the "
             "honest figure is zero verifiable trajectories out of "
             f"{n_targets} commitments.")

# ------------------------------------------------------------ 6 · evaluation
st.divider()
st.header("How it was evaluated")

metrics = load_metrics()
st.dataframe([{"method": m,
               "accuracy": round(v["accuracy"], 3),
               "macro F1": round(v["macro_f1"], 3),
               "F1 on technically-true claims": round(v["C_f1"], 3),
               "API calls": "0" if m == "tree_only" else "1 per claim"}
              for m, v in metrics["metrics"].items()], hide_index=True)

st.image(str(FIGS / "confusion.png"))

b1, b2 = metrics["metrics"]["baseline1"], metrics["metrics"]["baseline2"]
pipe = metrics["metrics"]["pipeline"]
st.write(
    f"Ground truth is {metrics['n']} claims blind-annotated by one person against a written "
    "rubric. The annotator saw the claim text only — no rule output, no model output."
)
st.write(
    f"Without the rubric the model detects **zero** accounting-misleading claims "
    f"(F1 {b1['C_f1']:.3f}). Given the same rubric it reaches {b2['C_f1']:.3f}. The knowledge "
    "the model lacks is not in the sentence; it is in how carbon accounting works."
)
st.write(
    f"Adding the regex flags on top of the rubric did not help — F1 {pipe['C_f1']:.3f} against "
    f"{b2['C_f1']:.3f}, which at n={metrics['n']} is a difference of one claim. That null "
    "result is reported rather than buried. The rules layer earns its place elsewhere: it runs "
    "with no API calls, it explains itself, and it is what finds the passages in section one."
)

# ------------------------------------------------------ 7 · what this is not
st.divider()
st.header("What this does not claim")
st.markdown("""
- Ground truth is one annotator. Three of five pipeline layers need no labels at all, which is why.
- n=29 scored items. A three-point accuracy difference is one item and means nothing.
- No evidence retrieval. Label D is structurally unreachable — zero instances, and it could not
  have been otherwise.
- The rules encode power-procurement carbon accounting. They do not transfer to other sectors.
  The architecture does.
- This measures disclosure form, not corporate conduct. It does not establish that any company
  is misleading anyone.
- PVR is a candidate factor. It has never been tested against returns, restatements, or
  regulatory outcomes.
""")
