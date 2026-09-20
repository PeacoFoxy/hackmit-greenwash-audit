"""TextQuant v2 -- the analyst terminal layout, per FRONTEND_V2.md.

app.py (v1) stays working; the two live side by side.
Run:            streamlit run app_v2.py
Offline check:  env -u ANTHROPIC_API_KEY streamlit run app_v2.py
"""
import json
import time
from pathlib import Path

import streamlit as st

from src.indicators import (band_margin, cached_bundle, claims_needing_review,
                            grade_components,
                            indicators_for, promises_per_verification, verification_density)
from src.claim_api import classify_claim, is_cached
from src.pipeline import MAX_CLAIM_SENTENCES, analyse
from src.tree import classify as tree_classify
from src.report_map import load_regions, region_option, render_map, span_caption
from src import history
from src.ui_text import (GRADE_BADGE_COLOR, GRADE_DISCLAIMER, GRADE_FRAGILITY_NOTE,
                         GRADE_READINGS, GRADE_TOOLTIP, HISTORY_PANEL,
                         INDICATORS, INERT_SUBSCORE_NOTE, KEY_TERMS,
                         KEY_TERM_QUALIFIER, PASSAGE_PANEL, STAGES, TREE_MARKS,
                         WORK_TREE, label_badge, mechanism_badge,
                         mechanism_of_region, say_margin, say_mechanism, say_span,
                         recommended_action, say_source, say_terminal,
                         term_hover, term_pill, why_flagged)

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "corpus"
DATA = ROOT / "data"
FIGS = ROOT / "figures"

# Spacer height used to bottom-align the left column. Streamlit has no real sticky
# positioning, so a fixed height approximates it.
LEFT_SPACER_PX = 220

st.set_page_config(page_title="TextQuant", layout="wide")


@st.cache_data
def load_bundles():
    """The three preloaded reports, with claims / sentences / audit split by company."""
    return cached_bundle()


def tag_mechanisms(result):
    for r in result.get("regions", []):
        r["mechanism"] = mechanism_of_region(r.get("flag_types", {}))
    return result


@st.cache_data(show_spinner=False)
def analyse_upload(file_bytes, filename, _on_stage=None, _on_partial=None):
    """Keyed on the file bytes, so re-uploading the same PDF is instant. Underscore-prefixed
    parameters are excluded from the cache key."""
    return tag_mechanisms(analyse(file_bytes, filename,
                                  on_stage=_on_stage, on_partial=_on_partial))


def analyse_passage(text):
    """Rule tree (zero calls) + an optional one-line rationale + the key terms this passage
    hits. Never raises."""
    tree = tree_classify(text)
    spans = [n["span"] for n in tree["path"] if "span" in n]
    out = {"text": text, "tree": tree, "span": spans[-1] if spans else None,
           "terms": key_terms_present([{"text": text}], load_term_risk()),
           "reasoning": None, "llm_label": None, "cached": is_cached(text)}
    try:
        r = classify_claim(text)
        out["reasoning"], out["llm_label"] = r["reasoning"], r["label"]
    except Exception:
        pass   # no network or no key: fall back to the rule tree's answer alone
    return out


def upload_indicators(result):
    """The four indicators for the upload path. The trajectory scan is not part of the
    upload flow, so the fourth comes back None."""
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
    """Track S lift table. Returns None when it has not been built, and the pills then
    render without colouring."""
    path = DATA / "term_risk.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def key_terms_present(sentences, term_risk):
    """sec. 4.1: accounting terms that appear in this report and carry a quantified claim."""
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
    """Exact match on company name or ticker, case-insensitive. Returns None on no match;
    never raises."""
    q = (query or "").strip().lower()
    if not q:
        return None
    return next((s for s in sources if q in (s["company"].lower(), s["ticker"].lower())), None)


def panel(title, note, height="content"):
    """Placeholder panel: a title plus a note that it is not built yet."""
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
        st.success(f"Loaded {selected.get('title') or selected['company']}")
    elif analyze:
        st.info("Type a company or ticker first, or upload a PDF.")

bundles = load_bundles()
bundle = bundles.get(selected["company"]) if selected else None

with bar_grade:
    grade_slot = st.container(border=True)   # filled after the pipeline finishes on upload


def render_grade(slot, grade, subject, blocked=None):
    with slot:
        st.caption("Disclosure grade", help=GRADE_TOOLTIP)
        letter_col, read_col = st.columns([1, 3], vertical_alignment="center")
        if grade:
            letter_col.markdown(f"# :{GRADE_BADGE_COLOR[grade['letter']]}[{grade['letter']}]")
            read_col.write(GRADE_READINGS[grade["letter"]])
            read_col.caption(f"Score {grade['score']:.0f} of 100 — {subject}")
            read_col.caption(say_margin(band_margin(grade["score"])))
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
                st.caption(INERT_SUBSCORE_NOTE)
                st.caption(GRADE_FRAGILITY_NOTE)
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
    with st.container(border=True):
        st.markdown(f"**{HISTORY_PANEL['title']}**")
        st.caption(HISTORY_PANEL["hint"])
        entries = history.load_index()
        if not entries:
            st.caption(HISTORY_PANEL["empty"])
        else:
            for e in entries[:8]:
                grade_txt = f" · grade {e['grade']}" if e.get("grade") else ""
                flag = f" · {HISTORY_PANEL['partial']}" if e.get("partial") else ""
                if st.button(e["filename"], key=f"hist_{e['hash']}", width="stretch"):
                    st.session_state.active_hash = e["hash"]
                    loaded = history.load(e["hash"])
                    st.session_state.upload_result = tag_mechanisms(loaded) if loaded else None
                    st.rerun()
                st.caption(f"{e['analysed_at']} · {e['sentences']:,} sentences · "
                           f"{e['passages']} passages{grade_txt}{flag}")

uploaded = st.session_state.get("upload_result")
if upload is None and not st.session_state.get("active_hash"):
    uploaded = None
values = (upload_indicators(uploaded) if uploaded
          else (indicators_for(bundle) if bundle else None))
# With no claims the completeness denominator is empty and the formula degenerates to a
# perfect score. Withholding the letter is better than reporting that.
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

        # Fewer than three observations: no trend line (sec. 4.4 / sec. 9)
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

    # ---- Where to look (ported unchanged from v1)
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

    # ---- Analyse a passage (paste text; rule tree costs nothing, LLM rationale optional)
    with st.container(border=True):
        st.markdown(f"**{PASSAGE_PANEL['title']}**")
        st.caption(PASSAGE_PANEL["hint"])
        pasted = st.text_area("Passage", height=90, label_visibility="collapsed",
                              placeholder=PASSAGE_PANEL["placeholder"],
                              key="passage_text")
        go = st.button("Analyse passage", key="passage_go")

        if go and pasted.strip():
            st.session_state.passage_result = analyse_passage(pasted.strip())
        elif go:
            st.caption("Paste a passage first.")

        res = st.session_state.get("passage_result")
        if res:
            tree = res["tree"]
            st.markdown(f"{label_badge(tree['label'])} &nbsp; "
                        f"{say_terminal(tree['terminal'], tree['mechanism'])}")
            if res.get("reasoning"):
                st.write(res["reasoning"])
            else:
                st.caption(PASSAGE_PANEL["rule_only"])
            if res["span"]:
                st.caption(f"Triggered on {say_span(res['span'])}")
            action = recommended_action(tree["mechanism"], tree["terminal"])
            if action:
                st.markdown("**What to ask for**")
                st.write(action)
            if res["terms"]:
                st.markdown(" ".join(term_pill(t["term"], t["lift"]) for t in res["terms"]))
            else:
                st.caption(PASSAGE_PANEL["no_terms"])
            with st.expander("Technical detail"):
                st.write({"terminal": tree["terminal"], "mechanism": tree["mechanism"],
                          "severity": tree["severity"], "label": tree["label"],
                          "path": [f"{n['node']}:{n['answer']}" for n in tree["path"]],
                          "llm_label": res.get("llm_label"), "cached": res.get("cached")})

    # ---- Selected passage (order matters: the company's own words come first)
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
            action = recommended_action(region.get("mechanism"))
            if action:
                st.markdown("**What to ask for**")
                st.write(action)
            if uploaded:
                st.caption(f"Source: {uploaded['filename']} (uploaded this session; "
                           "no publication date available)")
            elif source:
                st.caption(say_source(source))
            with st.expander("Technical detail"):
                st.write({"sent_id_range": [region["start_sent_id"], region["end_sent_id"]],
                          "rel_pos": region["rel_pos"], "peak_flag_density": region["peak"],
                          "threshold": region["threshold"],
                          "flag_counts": region.get("flag_types", {}),
                          "mechanism": region["mechanism"]})

# ============================================================ BELOW THE FOLD
st.divider()
st.header("How the analysis runs")
st.caption("Every stage is deterministic except claim extraction. The marker shows where "
           "the current run is.")
tree_slot = st.container()


def render_tree(slot, state):
    """state: {stage_name: done|running|pending|failed}. Renders the whole tree with the
    current stage highlighted."""
    with slot:
        for title, children, stage_name in WORK_TREE:
            mark = TREE_MARKS[state.get(stage_name, "pending")]
            st.markdown(f"{mark} **{title}**")
            for child in children:
                st.caption(f"　　{child}")


tree_state = st.session_state.get("tree_state", {})
render_tree(tree_slot, tree_state)

st.divider()
st.header("How it was evaluated")
panel("Ablation table and confusion matrix", "Carried over from v1 unchanged")

st.divider()
st.header("What this does not claim")
panel("Limitations", "Carried over from v1 unchanged")

# ======================================================= UPLOAD RUN (last)
# The pipeline runs last, so the work tree is already on screen and lights up stage by
# stage. It reruns on completion, which is how the panels above receive the data.
if upload is not None:
    file_bytes = upload.getvalue()
    h = history.file_hash(file_bytes)
    if st.session_state.get("active_hash") != h:
        state = {name: "pending" for _, _, name in WORK_TREE}
        order = [name for _, _, name in WORK_TREE]

        def on_stage(name, detail):
            if name in state:
                state[name] = "done"
                nxt = order.index(name) + 1
                if nxt < len(order):
                    state[order[nxt]] = "running"
            tree_slot.empty()
            render_tree(tree_slot, state)

        state[order[0]] = "running"
        tree_slot.empty()
        render_tree(tree_slot, state)

        try:
            result = analyse_upload(file_bytes, upload.name, _on_stage=on_stage,
                                    _on_partial=lambda p: st.session_state.__setitem__(
                                        "upload_partial", tag_mechanisms(p)))
            g = (grade_components(result["claims"], result["rows"])
                 if result.get("claims") else None)
            history.save(result, file_bytes, g["letter"] if g else None)
            st.session_state.update(upload_result=result, active_hash=h,
                                    tree_state={n: "done" for n in order})
        except Exception as exc:
            partial = st.session_state.get("upload_partial")
            for name in order:
                if state.get(name) == "running":
                    state[name] = "failed"
            st.session_state.update(upload_result=partial, active_hash=h, tree_state=state)
            st.warning(f"The analysis stopped during processing ({type(exc).__name__}). "
                       + (f"Partial results are above: {partial.get('n_sentences', 0):,} "
                          f"sentences, {len(partial.get('regions', []))} passages."
                          if partial else "No stage completed."))
        st.rerun()
