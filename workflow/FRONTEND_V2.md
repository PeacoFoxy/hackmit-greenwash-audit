# Frontend v2 — analyst terminal layout

Redesign of `app.py`. Replaces the single-column scrolling page with a
two-column terminal: input and process on the left, analysis on the right.

Status: **built.** `app_v2.py` implements this spec; the corpus-level headline
strip above the two columns was added afterwards and is not described here.

Supersedes `FRONTEND.md` §3 and §4. Everything in `FRONTEND.md` §2 (language
rules) and §5 (offline safety) still applies unchanged.

---

## 1. What changes and why

The v1 page reads as a research writeup. This reads as a tool an analyst opens
every morning. Three differences:

**Any company, not three.** The preloaded reports become examples, not the
product. Upload is the primary path; the three cached companies exist so the
demo starts instantly.

**A grade, not a scroll.** The user sees one letter within a second of the
analysis finishing. Everything else explains that letter.

**Process is visible.** The pipeline takes time. Showing which stage is running
turns a wait into a demonstration of depth.

---

## 2. Layout

A full-width top bar above both columns, then `st.columns([3, 7])`. The top bar
carries the two things that apply to the whole page — what is loaded, and the
verdict on it. Left column is sticky context, right column is analysis.

```
┌───────────────────────────────────────────────────────────────────────┐
│ TOP BAR  full width                                                   │
│ ┌───────────────────────────────┐  ┌────────────────────────────────┐ │
│ │ Company / ticker              │  │  DISCLOSURE GRADE        C     │ │
│ │ [_______________________] [→] │  │  technically true,             │ │
│ │ or upload a PDF               │  │  materially thin               │ │
│ └───────────────────────────────┘  └────────────────────────────────┘ │
├────────────────────────┬──────────────────────────────────────────────┤
│ LEFT  30%              │ RIGHT  70%                                   │
│                        │                                              │
│ ┌────────────────────┐ │ ┌──────────────────────────────────────────┐ │
│ │ RELATED SOURCES    │ │ │  KEY TERMS FOUND                         │ │
│ │ · headline one     │ │ │  matched · carbon-free · diverted ·      │ │
│ │ · headline two     │ │ │  inset · replenished · net zero          │ │
│ │ · headline three   │ │ └──────────────────────────────────────────┘ │
│ └────────────────────┘ │                                              │
│                        │ ┌────────┬────────┬────────┬──────────────┐ │
│                        │ │ Claims │ Promise│ Verif. │ Commitments  │ │
│                        │ │ needing│  per   │ density│  trackable   │ │
│         (space)        │ │ review │ verif. │        │              │ │
│                        │ │  31%   │  4.86  │ 1 in 30│    3%        │ │
│                        │ └────────┴────────┴────────┴──────────────┘ │
│                        │                                              │
│                        │ ┌──────────────────────────────────────────┐ │
│                        │ │  COMMITMENT TRAJECTORY                   │ │
│                        │ │  target vs observed pace                 │ │
│                        │ │  or the honest empty state               │ │
│ ┌────────────────────┐ │ └──────────────────────────────────────────┘ │
│ │ RUNNING            │ │                                              │
│ │ ✓ Reading PDF      │ │ ┌──────────────────────────────────────────┐ │
│ │ ✓ 4,084 sentences  │ │ │  WHERE TO LOOK                           │ │
│ │ ✓ 9 rules applied  │ │ │  ▁▁█▁▁▁▁██▁▁▁▁▁█▁▁▁▁▁▁█▁▁▁▁▁▁▁▁▁█▁▁     │ │
│ │ ⟳ Classifying…     │ │ │  13 passages · click to read             │ │
│ │ ○ Trajectory       │ │ └──────────────────────────────────────────┘ │
│ └────────────────────┘ │                                              │
│  pinned to the bottom  │ ┌──────────────────────────────────────────┐ │
│                        │ │  SELECTED PASSAGE                        │ │
│                        │ │  quote, then why, then source            │ │
│                        │ └──────────────────────────────────────────┘ │
└────────────────────────┴──────────────────────────────────────────────┘
```

Two consequences of moving input and grade into the top bar:

- §3.1 and §3.2 still define the input and the grade; they now render in the
  top bar rather than the left column. Their content rules are unchanged.
- The left column holds exactly two blocks: related sources at the top,
  execution status pinned at the bottom, with the gap between them left empty.
  The status block is the last thing on screen at the end of a run, which is
  where the eye lands when the analysis finishes.

Right-column order is: key terms, four indicators, commitment trajectory,
report map, selected passage.

Below the fold, unchanged from v1: how it was evaluated, and what this does not
claim. Those stay — they are the credibility of everything above.

---

## 3. Left column

### 3.1 Input

`st.text_input` for company or ticker, `st.file_uploader` beneath it.

Resolution: case-insensitive match against `corpus/sources.json`. On a miss,
do not error — show:

> No report loaded for **{name}**. Upload their sustainability report as a PDF,
> or try one of: Alphabet, Microsoft, Amazon.

Upload is the primary path and should look like it. The three cached names are
a convenience, not the offering.

### 3.2 Disclosure grade

The headline. One letter, large, with a one-line plain reading beneath.

| grade | reading |
| --- | --- |
| A | Figures are scoped and verifiable |
| B | Mostly scoped, some gaps |
| C | Technically true, materially thin |
| D | Claims contradict available figures |

**This grades the document, never the company.** Copy must say "disclosure
grade", and the tooltip must read:

> Measures how completely this report discloses the basis for its own figures.
> It is not a judgment of environmental performance or of the company.

Definition in §5. It must be mechanical and shown on demand.

### 3.3 Related sources

Headlines and links relevant to the company's environmental disclosure.

**This is the only network-dependent element on the page and it must never
block anything.** Render it last, in its own try/except, with three states:

- results → up to 5 headlines with source and date, each a link
- no results → "No recent coverage found."
- offline or error → "Source lookup unavailable offline."

Implementation: a web search tool if one is available in the environment;
otherwise a static `data/related_sources.json` keyed by company, populated
ahead of the demo. **Never a live crawl of the company's own site.**

If search is unavailable at build time, ship the static file and label the
panel honestly. A working static panel beats a spinner that never resolves.

### 3.4 Running

`st.status` with one line per stage. Plain language, not module names.

```
✓ Reading the PDF                4,084 sentences
✓ Checking disclosures           9 rules, 13 passages flagged
✓ Measuring language             7 signals
⟳ Classifying claims             89 claims
○ Extracting commitments
```

Persist after completion as a collapsed summary with total runtime. The audit
trail is part of the product.

---

## 4. Right column

### 4.1 Key terms found

A row of pills: the accounting terms present in this report that carry
quantified claims. Derived from `data/term_risk.json` where it exists, else
from the flag-trigger vocabulary.

Colour each pill by lift: low lift (term usually appears without its
qualifier) gets the warning tint; high lift gets neutral. Hover shows
`appears N times, qualifier present in M%`.

This is the first thing the user sees and it orients them: *this report leans
on `matched`, `diverted` and `inset`.*

### 4.2 Four indicators

`st.columns(4)`, each an `st.metric`. Definitions in §6. All four computed for
any report, uploaded or cached.

| indicator | form | reading |
| --- | --- | --- |
| Claims needing review | percentage | share of quantified claims that are technically true but incomplete |
| Promises per verification | ratio | forward-looking statements per mention of third-party assurance |
| Verification density | 1 in N | sentences between assurance mentions |
| Commitments trackable | percentage | targets with enough history in the same report to check progress |

Each gets a `help` tooltip with its formula. No indicator is shown without its
definition available.

### 4.3 Where to look

The report map from v1, unchanged: one strip per report, flagged regions
coloured by mechanism, plain-language legend, 8px minimum mark width, selectbox
beneath.

For a single uploaded report, one strip at full width.

### 4.4 Commitment trajectory

The regression panel. **Its honest form is usually empty, and that emptiness is
the finding.**

Where a target has two or more observations of the same metric, plot: a bar to
the current value, a marker at the target, a dotted line at the observed pace
extended to where it meets the target, annotated with the projected year.

Where it does not — which was 57 of 59 on the reference corpus — show:

> **{n} of {m} quantified commitments have no trackable history in this report.**
> A target is stated; the figures needed to check progress against it are not
> in the same document.

Then the discard breakdown table.

**Do not fabricate a trend line from one point.** The empty state is a stronger
result than a fitted line through insufficient data, and it is the one a judge
will remember.

### 4.5 Selected passage

Unchanged from v1 §4 section 2. Badge, quote, why, source, technical expander.
Order fixed: the company's words first, the interpretation second.

---

## 5. The disclosure grade

### Constraint

A single letter per company is the most dangerous element on this page. It is
one step from "this company greenwashes", which the data does not support.

Three protections, all mandatory:

1. The label is always "disclosure grade", never "ESG grade" or "greenwashing
   score"
2. The tooltip states it grades the document, not the company
3. Clicking it opens the full computation — every input, every threshold

### Definition

Three sub-scores, each 0 to 100, averaged.

```
completeness = (1 - C_rate) * 100
    where C_rate = C claims / (A claims + C claims)
    B and SKIP excluded — this measures quantified claims only

promise_balance = clamp((5 - PVR) / 4, 0, 1) * 100
    PVR <= 1 scores 100, PVR >= 5 scores 0

verification = clamp(verif_per_100_sentences / 5, 0, 1) * 100
    5 assurance mentions per 100 sentences scores 100

grade_score = mean of the three
```

| score | grade |
| --- | --- |
| >= 75 | A |
| >= 55 | B |
| >= 35 | C |
| < 35 | D |

### Thresholds are chosen, not learned

**State this in the expander, verbatim:**

> The thresholds in this grade were chosen by the author, not fitted to
> outcome data. There is no dataset of "correctly graded" reports to calibrate
> against. The grade is a transparent, reproducible summary of three measured
> quantities — not a validated rating.

That sentence is the difference between a defensible design decision and an
overclaim.

### Commitment trackability is deliberately excluded

It was near zero for all three reference reports. A component with no variance
carries no information and would drag every grade to D. It stays as a
standalone indicator in §4.2.

---

## 6. Indicator definitions

All computable from existing pipeline outputs. Implement in
`src/indicators.py` so both cached and uploaded paths use one code path.

```python
def claims_needing_review(claims):
    """% of quantified claims that are technically true but incomplete."""
    scored = [c for c in claims if c.label in ("A", "C")]
    return 100 * sum(c.label == "C" for c in scored) / max(len(scored), 1)

def promises_per_verification(sentences):
    """Forward-looking markers per assurance mention."""
    f = sum(s.future for s in sentences)
    v = sum(s.verification for s in sentences)
    return f / max(v, 1)

def verification_density(sentences):
    """Sentences between assurance mentions. Returned as N for '1 in N'."""
    v = sum(s.verification for s in sentences)
    return len(sentences) / max(v, 1)

def commitments_trackable(audit):
    """% of extracted targets with >= 2 observations of the same metric."""
    return 100 * audit.n_with_two_obs / max(audit.n_targets, 1)
```

Reference values, for sanity-checking the implementation:

| | Alphabet | Microsoft | Amazon |
| --- | --- | --- | --- |
| Promises per verification | 1.15 | 4.86 | 0.50 |
| Verification density | 1 in 17 | 1 in 30 | 1 in 9 |

---

## 7. Upload path

Primary path. Must produce every panel above from a PDF with no cached data.

```
PDF → ingest → clean → rules → signals → anomaly
                                   ↓
                     claims → classify → indicators → grade
```

`@st.cache_data` keyed on file hash, so re-uploading is instant.

**Cap claim extraction at the first 150 qualifying sentences** and say so in
the progress text. A 300-page report otherwise runs past any reasonable demo
window.

**Every stage writes its partial result to session state as it completes**, and
the right column renders progressively. If classification fails, the report map
and three of four indicators are already on screen. A partial analysis is
useful; a spinner is not.

---

## 8. Build order

Each step must run before the next begins. Commit at every boundary.

| # | step | time | risk |
| --- | --- | --- | --- |
| 1 | Two-column skeleton, all panels as placeholders | 20 min | none |
| 2 | `src/indicators.py` plus the four metrics, cached path only | 30 min | none |
| 3 | Grade block with expander showing the computation | 25 min | none |
| 4 | Move report map and passage detail into the right column | 20 min | low — code exists |
| 5 | Key terms pill row | 20 min | low |
| 6 | Commitment trajectory panel including the empty state | 25 min | low |
| 7 | Running-status panel | 20 min | low |
| 8 | **Offline test, key unset, WiFi off** | 10 min | **do not skip** |
| 9 | Upload path with progressive rendering | 60 min | moderate |
| 10 | Related sources, static file or search | 20 min | isolated |

**Tag the working v1 before starting:**

```bash
git tag frontend-v1
git push --tags
```

If v2 is unfinished when time runs out, `git reset --hard frontend-v1` returns
a complete working page in one command.

---

## 9. What not to build

- **Live crawling of company websites.** Conference WiFi, bot blocking, scanned
  PDFs. The failure is a network failure and it will read as a broken project.
- **A fitted regression through fewer than three points.** §4.4.
- **A grade without its computation visible.** §5.
- **Tabs.** Hidden panels are panels a judge does not see.
- **Custom CSS beyond the column split.** Streamlit defaults are adequate and
  time is not.

---

## 10. Open questions

- **Grade for a multi-report view.** With three cached companies loaded, is
  there one grade per company or none until a company is selected? Proposal:
  no grade until one is selected; the map shows all three.
- **Key-term pills without `term_risk.json`.** If Track S has not run, fall
  back to the flag-trigger vocabulary and omit the lift colouring.
- **Related-sources relevance.** A generic company-name search returns earnings
  coverage, not disclosure coverage. Constrain the query to sustainability and
  emissions terms, and accept that precision will be low.
- **Grade stability.** With one reference corpus, the thresholds have never been
  tested against a report that should clearly score A. If an uploaded report
  from a strong discloser still grades C, the thresholds are wrong and that
  should be said rather than tuned away during the demo.
