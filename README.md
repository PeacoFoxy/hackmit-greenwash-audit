# TextQuant

**Turning corporate environmental disclosure into a cross-sectional, point-in-time
signal.**

Sustainability reports rarely contain false statements. They state a figure and omit the
one thing that would verify it — the accounting method, the boundary, the absolute total,
the definition of the term. Finding that by hand does not scale: 50–120 pages per report,
hundreds of reports per portfolio.

TextQuant reads any corporate environmental report and outputs:

1. **Claim labels** — every quantified claim classified by *which* disclosure is missing
2. **Passage locations** — where in the document that pattern clusters
3. **Report-level indicators** — a comparable score per report, with its fragility stated

Company-agnostic by construction: the rules encode greenhouse-gas accounting concepts —
scope boundaries, market- versus location-based methods, intensity versus absolute
figures — not any issuer's vocabulary. Nothing is trained on the validation corpus.

---

## Workflow

```
Any environmental report (PDF)
        │
        ▼
  1. PREPROCESSING          text extraction, sentence split, prose filter
        │
        ▼
  2. FEATURE EXTRACTION     7 language signals + 9 accounting rules per sentence
        │
        ▼
  3. ANOMALY DETECTION      flag density vs the report's own baseline → passages
        │
        ▼
  4. CLAIM EXTRACTION       atomic, independently checkable assertions
        │
        ▼
  5. THREE PARALLEL TRACKS ──┬── Track R   rule decision tree     0 model calls
                             ├── Track S   lift statistics        0 model calls
                             └── Track D   language model
        │                            │
        │                            ▼
        │                    CONSENSUS LAYER
        │                    agreement between tracks as a
        │                    label-free confidence signal
        ▼
  6. SIGNAL OUTPUT          labels · passages · indicators · recommended action
```

### Why three tracks

Each fails differently, so agreement between them is itself a signal.

| Track | Method | Fails when |
| --- | --- | --- |
| **R** rule-based | 22-node decision tree, 26 terminals | the wording is novel |
| **S** statistical | how often a term appears with its required qualifier | the corpus is small |
| **D** language model | four-class rubric, batched | it hallucinates or drifts |

Track R also carries the explanation: every label ships with the root-to-leaf path that
produced it, so a judgment can be audited instead of trusted.

### Four labels

Graded alignment, modelled on credit-rating scales rather than a binary verdict.

| | Meaning |
| --- | --- |
| **A** | Substantiated: concrete figure with its scope or method stated |
| **B** | Vague: no verifiable quantity |
| **C** | Technically true but incomplete: the figure is real, the basis is missing |
| **D** | Contradicted by other disclosed information |

Class C is the target: what a keyword scanner cannot find, and what a model without a
rubric misses entirely.

---

## How the algorithm was optimised

Eleven rounds, each one measure → change → re-measure. Five shipped, six rejected on
their own numbers.

| # | Round | Measured result | Outcome |
| --- | --- | --- | --- |
| 1 | Drop a flag that fires on 8–16% of all sentences | Detection threshold fell 27–42%; passages found rose 11 → 13 | **Shipped** |
| 2 | Add specificity, balanced accuracy, F-beta to the metrics | Exposed that class-C recall of 1.000 was bought with specificity of 0.550 | **Shipped** |
| 3 | Accept named facility boundaries, not only GHG-Protocol scope terms | Accuracy 0.690 → 0.793; two thirds of the gain from code, one third from a label fix | **Shipped** |
| 4 | Show grade fragility next to the grade | Band edges moved ±12 points flip 2 of 3 reports; the ranking never flips | **Shipped** |
| 5 | Per-mechanism recommended action | Turns a label into a request that can be sent to investor relations | **Shipped** |
| 6 | Feed rule flags to the model as structured hints | 20% more input tokens, 3.5 points *lower* accuracy | Rejected |
| 7 | Context cross-check: clear a flag if the qualifier appears nearby | C balanced accuracy 0.868 → 0.697; of 8 claims cleared, 1 was right | Rejected |
| 8 | Ensemble voting across tracks | 16 combinations tested, none beat the rule tree alone | Rejected |
| 9 | Abstain when confidence is low | 5 confidence proxies, none beats random abstention | Rejected |
| 10 | Unsupervised rule scoring from corpus statistics | Ranked the one provably useful rule as least suspicious | Rejected |
| 11 | Conventional small-data ML (TF-IDF + linear SVM) | 0.483 under leave-one-out, against a 0.448 majority baseline | Rejected |

Round 7 is worth keeping for its cause: *global operations* recurs every few sentences,
so proximity never proved the qualifier bound to that figure — the pattern the rule was
built to catch.

A per-rule ablation found the tree over-specified: 15 of 26 terminals can be removed with
**no change to any metric**, while removing the next four costs 0.103 accuracy. Rules
that are individually insignificant are not jointly useless.

---

## How it was validated

The validation corpus is three reports: 4,084 sentences, 390 extracted claims, 29
blind-annotated labels. The methods below were chosen so conclusions survive that sample
size rather than depend on it.

| Method | What it protects against |
| --- | --- |
| Specificity and balanced accuracy, not recall alone | Recall bought by over-flagging |
| Friedman test + Nemenyi critical difference | Declaring a winner among tied methods |
| Pairwise McNemar with Holm correction | Multiple-comparison inflation |
| Paired bootstrap, 2,000 resamples | Judging a rule off one point estimate |
| Leave-one-out cross-validation | Scoring a baseline on its own training data |
| Parameter sweeps over every threshold | A result that holds at one cut-off only |
| Random-abstention control | Mistaking fewer answers for better answers |

**Not established.** The five methods are statistically indistinguishable here: Friedman
χ² = 4.82, p = 0.31, the whole field inside one critical difference, no pair surviving
McNemar. The rule tree scores highest; that is not a claim of superiority.

**Established.** The rule tree costs **0 model calls** against 21 per 100 claims, and
every label carries an auditable path. Without the four-class rubric a language model
finds **no** class-C claims at all — precision, recall and F1 exactly zero — while
overall accuracy stays respectable, because always answering B scores well.

Needing no accuracy claim at all: **57 of 59 quantified commitments cannot be
progress-checked from the report that states them.**

---

## Repository

```
TextQuant/
├── app_v2.py                  interface: analyst terminal layout
├── app.py                     earlier single-column version, still runs
├── run_all.sh                 pipeline; `verify` mode reproduces every number
├── requirements.txt
│
├── src/
│   ├── ingest.py              PDF → text
│   ├── signals.py             sentence split, prose filter, 7 language signals
│   ├── rules.py               9 accounting rules, regex only
│   ├── anomaly.py             flag density → passages worth reading
│   ├── extract.py             atomic claim extraction
│   │
│   ├── tree.py                Track R — decision tree, 26 terminals, 0 model calls
│   ├── termstats.py           Track S — lift statistics, 0 model calls
│   ├── llm.py                 Track D — the single cached model entry point
│   ├── consensus.py           agreement between the three tracks
│   │
│   ├── evaluate.py            metrics and confusion matrix
│   ├── stats_tests.py         Friedman, Nemenyi, McNemar, mean ranks
│   ├── ablation.py            per-rule contribution with bootstrap intervals
│   ├── sensitivity.py         parameter sweeps
│   ├── abstain.py             abstention curves against a random control
│   ├── cost.py                calls, tokens and dollars per 100 claims
│   ├── trajectory.py          quantified commitments and their evidence
│   ├── indicators.py          report-level indicators and grade
│   └── pipeline.py            live path for an uploaded PDF
│
├── data/                      all derived data, committed
├── cache/                     175 model responses, committed for reproducibility
├── figures/
└── workflow/                  the written specifications the code was built against
```

---

## Running it

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app_v2.py
```

No API key needed: every model call on the demo path is served from `cache/`, so the
interface works with the network off.

```bash
./run_all.sh verify     # reproduce every number above: no PDFs, no key, no spend
```

`verify` clears `ANTHROPIC_API_KEY` first, so a cache miss fails loudly instead of
quietly spending money. Tested by cloning into an empty directory: all 20 steps completed
and every published figure matched.

Analysing a new PDF needs a key for the extraction stage — copy `.env.example` to `.env`.
Without one, the upload still runs the four deterministic stages and says so.

Source PDFs are not in the repository (published corporate documents, excluded by
`.gitignore`). Everything derived from them is committed, so a fresh clone runs.

---

## Limits

- **Validation scale.** 29 blind labels. The method is general; the measured accuracy is
  not a population estimate. No feature-selection search was run for that reason — 2²⁶
  candidate subsets against 29 items fits noise.
- **Rule coverage.** 10 of 19 class-C rules have never met a human label.
  `src/expand_gold.py` generates a stratified blind sheet for them.
- **Recall is not yet falsifiable.** No label exists where the tree says A and a human
  says C. Four probe claims are in that sheet to look for one.
- **Single reporting year**, so no comparison against prior disclosures.
- **No external evidence.** Claims are checked against the document that makes them —
  the reason the 57-of-59 result exists. Retrieval against filings and certification
  records is the next step.
- **One label per claim**, chosen by traversal order when several apply.
