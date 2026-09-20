# Frontend build spec — Streamlit

Implementation spec for `app.py`. First version of the user-facing interface.

Status: **built, then superseded.** `app.py` implements this spec and still runs.
`FRONTEND_V2.md` replaced its layout; its sec. 2 language rules are still in force.

---

## 1. What the interface is for

An analyst has a sustainability report and no time to read 200 pages. The
interface answers one question:

> **Which passages should I read, and why?**

Everything on screen serves that. Nothing decorative, nothing that requires
learning the internal taxonomy.

### Three states of the input

| input | behaviour | risk |
| --- | --- | --- |
| Preloaded company (Alphabet, Microsoft, Amazon) | Loads cached analysis instantly | none |
| PDF upload | Runs the full pipeline live, ~90s | moderate, worth it |
| Any other company name | "No report loaded" plus guidance to upload | none |

**No live web crawling.** The demo runs on conference WiFi with two-second
latency and intermittent DNS. A crawler failure on stage reads as a broken
project even though the failure is a network problem. State this out loud
rather than faking it:

> "Three reports are preloaded. Anything else, you upload the PDF and it runs
> in about ninety seconds. I'm not crawling the web live, because the failure
> modes there are network problems, not analysis problems."

---

## 2. Language rules

**The single highest-value decision in this build.** Internal mechanism names
never reach the screen.

| internal | shown to user |
| --- | --- |
| `UNDISCLOSED_METHOD` | Method not stated |
| `UNDISCLOSED_BOUNDARY` | Coverage not stated |
| `SELECTIVE_AGGREGATION` | Partial figure only |
| `UNDEFINED_TERM` | Term undefined |
| `MARKET_BASED_IMPLIED` | Purchased, not consumed |
| `INTENSITY_NO_ABSOLUTE` | Per-unit figure only |
| `NO_BASELINE_YEAR` | No baseline year |
| `FUTURE_PROMISE_NO_MILESTONE` | No interim milestone |
| `PROPRIETARY_METRIC` | Company-defined metric |
| `DIVERSION_UNDEFINED` | Disposal route unstated |
| Label A | Substantiated |
| Label B | Unverifiable |
| Label C | Technically true, incomplete |
| Label D | Contradicted |

Keep the codes in the JSON. Show them only in an expandable "technical detail"
block on the passage panel.

Other copy rules:

- Headlines are sentences with the answer in them, not chart titles.
  "13 passages need review" not "Anomaly region distribution".
- Axis labels in plain words. "Start of report" and "end", not 0.0 and 1.0.
- Never say "greenwashing" as a verdict about a company. The system measures
  disclosure form. Say "incomplete disclosure" or "needs review".
- Sentence case everywhere.

---

## 3. Page layout

Single scrolling page. No tabs — a judge should see everything by scrolling,
and hidden tabs are hidden work.

```
┌──────────────────────────────────────────────────────┐
│  HEADER                                              │
│  TextQuant                                           │
│  Finds claims that are true and incomplete.          │
├──────────────────────────────────────────────────────┤
│  INPUT ROW                                           │
│  [ company or ticker    ] [Analyze]   or  [Upload ▾] │
│  Preloaded: Alphabet · Microsoft · Amazon            │
├──────────────────────────────────────────────────────┤
│  SECTION 1 — REPORT MAP                    ◄ the hook│
│  "13 passages need review"                           │
│  three document strips with coloured marks           │
│  plain-language legend                               │
├──────────────────────────────────────────────────────┤
│  SECTION 2 — PASSAGE DETAIL                          │
│  quote with trigger highlighted, then why            │
│  source and date                                     │
├──────────────────────────────────────────────────────┤
│  SECTION 3 — CLAIM CLASSIFIER                        │
│  four preset examples + free text box                │
│  label, rule path, reasoning                         │
├──────────────────────────────────────────────────────┤
│  SECTION 4 — CROSS-COMPANY SIGNALS                   │
│  promise-to-verification ratio                       │
│  promises vs verification chart                      │
├──────────────────────────────────────────────────────┤
│  SECTION 5 — COMMITMENT VERIFIABILITY                │
│  "57 of 59 commitments cannot be progress-checked"   │
├──────────────────────────────────────────────────────┤
│  SECTION 6 — HOW IT WAS EVALUATED                    │
│  ablation table, confusion matrix                    │
├──────────────────────────────────────────────────────┤
│  SECTION 7 — WHAT THIS DOES NOT CLAIM                │
│  limitations, stated in the UI not buried in README  │
└──────────────────────────────────────────────────────┘
```

Section 1 is the hook. If a judge only sees the top of the page, they should
already understand the product.

Section 7 in the UI rather than only the README is deliberate. Most projects
hide limitations. Putting them on screen is a signal about how the work was
done.

---

## 4. Section specifications

### Header

Title, one-line description, nothing else. No logo, no hero image.

```
TextQuant
Finds claims that are true and incomplete. Nothing is false, so
fact-checking doesn't fire. Nothing is obviously vague, so a reader
doesn't either.
```

### Input row

`st.text_input` for company or ticker, `st.file_uploader` for PDF, both on one
row via `st.columns([3, 1, 2])`.

Resolution order: exact match against `corpus/sources.json` company or ticker,
case-insensitive. On miss, show an info box naming the three available reports
and pointing at the uploader. Never error.

On upload: run the pipeline with `st.status` showing each stage as it
completes. Stage names in plain words, not module names.

```
Reading the PDF                    4,084 sentences found
Checking accounting disclosures    9 rules applied
Measuring language patterns        7 signals computed
Finding passages to review         13 regions flagged
Classifying claims                 89 claims labelled
```

Cache with `@st.cache_data` keyed on file hash so re-uploading the same report
is instant.

### Section 1 — report map

The hook. One horizontal strip per company, marks at `rel_start` to `rel_end`,
coloured by mechanism.

Implementation: `st.plotly_chart` so marks are clickable, or matplotlib plus a
`st.selectbox` of regions as the fallback. **Build the fallback first** — a
non-clickable chart with a dropdown works, a broken click handler does not.

Headline above the chart, computed live:

```
{n_regions} passages need review
Out of {n_sentences:,} sentences across {n_companies} reports.
```

**Minimum mark width of 8px** even when the true proportion is smaller,
otherwise a 29-sentence region in a 1,178-sentence report is unclickable. Keep
the true width in the hover text.

Legend in plain language, horizontal, below the chart.

### Section 2 — passage detail

Driven by the map selection. Shows:

1. A badge with the plain-language mechanism, plus company, position, length
2. The passage text, with the trigger span highlighted in amber
3. **Below the quote**, the explanation of why it was flagged
4. Source document name and publication date
5. Collapsed `st.expander` with the technical detail: terminal name, rule path,
   severity, claim ids

Order matters. The company's own words come first, the interpretation second.

### Section 3 — claim classifier

Four preset buttons, one per class, plus a free-text box.

**Presets are essential.** Judges will not type their own text, and presets run
from cache so they cannot fail on stage. Free text is a live call and may fail
on bad WiFi — put the presets first so a failure reads as "their text is new"
rather than "his thing is broken".

Suggested presets:

| button | claim |
| --- | --- |
| Substantiated | "Our Scope 1 and 2 emissions decreased by 30% from the 2020 base year" |
| Unverifiable | "Nature-based design solutions are reducing our environmental footprint" |
| **Technically true** | "Amazon matched 100% of the electricity consumed by its global operations with renewable energy" |
| Per-unit only | "We reduced emissions per shipped unit by 39% compared to 2019" |

The third is the demo climax. Highlight `matched` and explain the term of art.

Output: label as a coloured badge, the rule path as a breadcrumb, the model
reasoning as one sentence, and an expander with the raw JSON.

### Section 4 — cross-company signals

Two elements.

**PVR metric row** — `st.columns(3)`, one `st.metric` per company. Label
"Promises per verification". Values 4.86, 1.15, 0.50. Caption below:

> Microsoft makes a forward-looking claim every 6 sentences and mentions
> third-party verification every 30. Amazon is the reverse.

**The three-panel figure** — `figures/sig_overlay_all.png`, shared axes. This
is the strongest visual in the project. Caption explaining that two reports
pivot to verification in the back half and the third has no such section.

### Section 5 — commitment verifiability

One number, stated as a sentence:

> **57 of 59 quantified commitments cannot be progress-checked from the report
> that makes them.**

Then the breakdown table: 50 with zero trackable observations, 7 with one, 2
with two that both turned out to be extraction errors.

Then `figures/commitment_verifiability.png`, the per-company bar chart.

**Report the two extraction errors honestly** in an expander. The extractor
confused a baseline-relative reduction with a level — which is exactly the
ambiguity the rule layer exists to detect. That is worth stating, not hiding.

### Section 6 — how it was evaluated

The ablation table as `st.dataframe`, the confusion matrix image, and three
short paragraphs:

- Ground truth is 30 claims blind-annotated by one person against a written
  rubric
- Without the rubric the model detects **zero** accounting-misleading claims
- Adding regex flags on top did not help, and that null result is reported

### Section 7 — what this does not claim

Plain list. No hedging language, no apology.

- Ground truth is one annotator. Three of five pipeline layers need no labels
  at all, which is why.
- n=29 scored items. A three-point accuracy difference is one item and means
  nothing.
- No evidence retrieval. Label D is structurally unreachable — zero instances,
  and it could not have been otherwise.
- The rules encode power-procurement carbon accounting. They do not transfer
  to other sectors. The architecture does.
- This measures disclosure form, not corporate conduct. It does not establish
  that any company is misleading anyone.
- PVR is a candidate factor. It has never been tested against returns,
  restatements, or regulatory outcomes.

---

## 5. Offline safety

**The demo must survive a dead network.** Non-negotiable, and it must be
tested, not assumed.

- Every preset claim and every preloaded company reads from `cache/`
- `src/llm.py` already uses `os.environ.get(...)` so import succeeds with no key
- Wrap live calls in try/except, show `st.warning("Live analysis unavailable,
  showing cached result")` rather than a traceback
- All figures load from `figures/` as static PNG, never regenerated at runtime

**Test before presenting:**

```bash
env -u ANTHROPIC_API_KEY streamlit run app.py
```

Then disconnect WiFi and click every preset. If all four produce results, the
demo is safe.

---

## 6. Build order

Strict order. Each step must run before starting the next.

| # | step | time | notes |
| --- | --- | --- | --- |
| 1 | Skeleton: header, input row, seven empty sections | 15 min | commit here |
| 2 | Section 1 report map, static matplotlib, selectbox for region choice | 30 min | the hook |
| 3 | Section 2 passage detail wired to the selectbox | 20 min | |
| 4 | Section 3 classifier with four presets from cache | 25 min | commit here |
| 5 | Sections 4, 5, 6 — mostly `st.image` and `st.dataframe` | 25 min | |
| 6 | Section 7 limitations, static text | 5 min | |
| 7 | Offline test with key unset and WiFi off | 10 min | **do not skip** |
| 8 | Upload flow with staged progress | 40 min | **only if 1–7 are done** |

**Step 8 is last and optional.** A working page with three preloaded reports
beats a half-working uploader. If time runs out, the ticker box still resolves
the three companies and the uploader says "coming soon" — which is true.

---

## 7. File layout

```
app.py                    all UI code, single file
src/ui_text.py            mechanism name mapping, preset claims,
                          limitation copy
figures/*.png             pre-rendered, never generated at runtime
data/*.json               pipeline outputs, read-only
cache/*.json              LLM cache, makes presets offline-safe
```

Keep `app.py` as one file. Splitting a Streamlit app across modules costs more
than it saves at this size, and a judge reading the repo can follow one file.

---

## 8. What not to build

- **Tabs or multipage.** Hidden content is content a judge does not see.
- **Live web crawling.** Stated above.
- **A chat interface.** The product is triage, not conversation. A chat box
  invites judges to test the LLM instead of looking at the analysis.
- **Custom CSS beyond a few lines.** Streamlit defaults are fine and time is
  better spent elsewhere.
- **Anything requiring a database.** JSON files on disk.
- **Regenerating figures at runtime.** Pre-render everything.

---

## 9. Open questions

- **Three strips or one?** Three supports the cross-sectional story and pairs
  with section 4. One gives the passage panel more room. Three, then click into
  Amazon, is the demo path.
- **Clickable marks.** Plotly click events in Streamlit need
  `streamlit-plotly-events` or a recent Streamlit with `on_select`. Verify
  before committing to it; the selectbox fallback is not a downgrade worth
  debugging under time pressure.
- **Upload runtime.** A 300-page report may take longer than 90 seconds. Cap
  extraction at the first N qualifying sentences and say so in the progress
  text.
