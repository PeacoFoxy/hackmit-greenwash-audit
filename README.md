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

### What it found

Four numbers, one formula each, reproducible offline (`python -m src.headline`).

| | Formula | Result |
| --- | --- | --- |
| Document that needs no analyst attention | `1 − claims surfaced / sentences` | **97.8%** (89 of 4,084) |
| Quantified commitments that cannot be progress-checked | `targets with <2 observations / targets` | **96.6%** (57 of 59) |
| Rule tree and language model reaching the same label | `CONFIRMED / (CONFIRMED + CONTESTED)` | **78.6%** (22 of 28) |
| Quantified claims that are technically true but missing their basis | `C / (A + C)`, corrected for measured rule precision | **45–49%** |

The fourth is reported as an interval, and the raw count is not the headline. `C / (A+C)`
comes to 80.9%, but class-C precision is 0.667 on validated rules and 0.250 on the ten
the blind test exposed — carrying the raw count forward would import that error. Each C
is instead weighted by the measured precision of the rule that produced it. It is the
only one of the four that depends on the classifier being right; the other three are
counting facts.

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

### Four ways text defeats a reader

Each track exists because a different one of these breaks a different method.

| Challenge | What it looks like here | Which track absorbs it |
| --- | --- | --- |
| **Biased training data** | A model trained on disclosure learns the register of disclosure, and fluent hedging reads as substantiated | **R** is not trained at all. Its rules encode GHG-accounting concepts, so they cannot inherit a corpus's habits |
| **Misinterpretation** | *100% renewable* is literally true on a market-based basis and false on a location-based one. Both readings are defensible; only one is checkable | **R**'s root-to-leaf path names which reading it took, so a wrong one is visible rather than silent |
| **New vocabulary** | Every issuer coins terms — *carbon-free energy percentage*, *water positive*. A fixed keyword list ages out within one reporting cycle | **S** learns term × qualifier lift from the document's own corpus, so an unseen term still gets scored on whether its qualifier travels with it |
| **Tone of voice** | Confident prose and cautious prose can carry identical information content; rhetoric is not evidence | The rubric grades on *what is disclosed*, never on how assertively. A confident sentence with no boundary is still C |

No track handles all four. That is the argument for running them in parallel and treating
their agreement as the confidence signal, rather than picking a winner.

---

## How the data is used

**Nothing is fitted to the labels.** There is no training split, because there is no
training.

| Stage | What it consumes | Labels involved |
| --- | --- | --- |
| **Track R** (rule tree) | nothing — the rules are written from GHG Protocol concepts | none |
| **Track S** (lift table) | the 4,084-sentence corpus, unsupervised | none |
| **Track D** (language model) | a pre-trained model, zero-shot with the four-class rubric | none — no fine-tuning, no few-shot examples |
| **Predicting** on a new upload | the same three tracks, unchanged | none |
| **Testing** | 29 randomly drawn claims, blind-annotated | held out, used only to score |
| **Round 11's supervised control** (TF-IDF + linear SVM) | the only component that trains | leave-one-out, so it never scores on what it fitted |

This removes the usual leakage channel and leaves a subtler one, which is worth naming:
**the author saw the gold set while writing the rules.** Round 3 below changed a regex
after reading the errors it produced, and gained 0.103 accuracy. That gain is fitted to
those 29 claims in the human-in-the-loop sense, however the code is structured — which is
why the rules were then tested against claims drawn to a quota over the rules the gold
set had never exercised (Round 12), and why that test is reported separately and never
averaged in.

Two annotation sheets, two jobs:

- `data/blind30.csv`, `data/blind_expand.csv` — the annotator sees claim text and nothing
  else. No model label, no rule terminal, no flags. This is the only source of gold.
- `data/annotations.csv` — the model's pre-labels, which feed the report-level
  indicators. It has no gold column, by construction: it used to have a blank one, and
  all 89 rows came back matching the model's own answer.

---

## How the algorithm was optimised

Thirteen rounds, each one measure → change → re-measure. Six shipped, seven rejected on
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
| 12 | Blind-annotate 20 claims drawn to a quota over the rules gold had never exercised | Rules with prior evidence: C precision 0.667. Rules with none: **0.250** (Fisher p = 0.024) | **Shipped** as a measurement |
| 13 | Use "has this rule ever been checked?" as a confidence proxy | Beats the naive control (0.806 vs p95 0.710) and fails the correct one | Rejected |

Round 7 is worth keeping for its cause: *global operations* recurs every few sentences,
so proximity never proved the qualifier bound to that figure — the pattern the rule was
built to catch.

Round 13 is worth keeping for a different reason: the first control said it worked. The
tier is nearly collinear with which sample a claim came from, and the two samples differ
in accuracy by design, so resampling the pooled set lets the control draw a favourable
mix. Holding the source composition fixed removes the effect entirely. The result is
reported as untestable on this data, not as a win.

A per-rule ablation found the tree over-specified: 15 of 26 terminals can be removed with
**no change to any metric**, while removing the next four costs 0.103 accuracy. Rules
that are individually insignificant are not jointly useless.

Re-run once the stratified labels gave those rules any coverage at all, the picture
sharpens. Of 19 class-C terminals: 5 never fire on 390 claims; 5 fire but **not one of
2,000 bootstrap resamples favours keeping them**; 1 (intensity reported without an
absolute) earns its place with an interval clear of zero; the rest are ties. All of them
are still in the tree. Each of the five rests on one or two labels, drawn by a quota
designed to test that rule — enough to stop calling them validated, not enough to delete
them on. They are documented here instead, which is the same standard applied to the five
dead rules.

---

## How it was validated

The validation corpus is three reports: 4,084 sentences, 390 extracted claims, and 49
blind-annotated labels in two sets that are never averaged together — 29 drawn at random,
which is what estimates accuracy, and 20 drawn to a per-terminal quota, which is what
measures individual rules. The methods below were chosen so conclusions survive that
sample size rather than depend on it.

| Method | What it protects against |
| --- | --- |
| Specificity and balanced accuracy, not recall alone | Recall bought by over-flagging |
| Friedman test + Nemenyi critical difference | Declaring a winner among tied methods |
| Pairwise McNemar with Holm correction | Multiple-comparison inflation |
| Paired bootstrap, 2,000 resamples | Judging a rule off one point estimate |
| Leave-one-out cross-validation | Scoring a baseline on its own training data |
| Parameter sweeps over every threshold | A result that holds at one cut-off only |
| Random-abstention control | Mistaking fewer answers for better answers |
| Stratified sampling over never-exercised rules | Rules whose accuracy was unmeasured being read as adequate |
| Source-stratified resampling control | A confidence signal that is really a sampling artefact |
| Blind annotation sheets with no model output | An annotator anchored on the answer being scored |

**Not established.** The five methods are statistically indistinguishable here: Friedman
χ² = 4.82, p = 0.31, the whole field inside one critical difference, no pair surviving
McNemar. The rule tree scores highest; that is not a claim of superiority.

**Established.** The rule tree costs **0 model calls** against 21 per 100 claims, and
every label carries an auditable path. Without the four-class rubric a language model
finds **no** class-C claims at all — precision, recall and F1 exactly zero — while
overall accuracy stays respectable, because always answering B scores well.

**Established, and unflattering.** The rules that had evidence behind them reach class-C
precision of 0.667. The ten that had never been exercised by a gold label reach **0.250**
on 16 blind judgments (Fisher exact, p = 0.024). Of the 12 disagreements, 9 are claims
the tree called incomplete that the annotator read as substantiated. Those rules touch 10
of 89 scored claims, so the effect on the headline is small — but "never measured" turned
out to mean "measurably worse", not "probably fine".

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
├── LICENSE
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
│   ├── headline.py            the four corpus-level percentages above
│   ├── evaluate.py            metrics and confusion matrix
│   ├── stats_tests.py         Friedman, Nemenyi, McNemar, mean ranks
│   ├── ablation.py            per-rule contribution with bootstrap intervals
│   ├── sensitivity.py         parameter sweeps
│   ├── abstain.py             abstention curves against a random control
│   ├── expand_gold.py         stratified blind sheet over never-exercised rules
│   ├── merge_expand.py        per-rule verdicts, kept separate from the random gold
│   ├── evidence_tier.py       the confidence proxy that failed its correct control
│   ├── cost.py                calls, tokens and dollars per 100 claims
│   ├── trajectory.py          quantified commitments and their evidence
│   ├── indicators.py          report-level indicators and grade
│   └── pipeline.py            live path for an uploaded PDF
│
├── data/                      all derived data, committed
│   ├── gold.json              29 random blind labels — the accuracy estimate
│   ├── blind_expand.csv       20 stratified blind labels — the per-rule test
│   └── annotations.csv        model pre-labels; no gold column, by design
├── cache/                     175 model responses, committed for reproducibility
├── figures/
├── workflow/                  the written specifications the code was built against
└── submission/                the write-up, in Markdown, Word and PDF
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
quietly spending money. Tested by cloning into an empty directory: all 23 steps completed
and every published number matched.

Analysing a new PDF needs a key for the extraction stage — copy `.env.example` to `.env`.
Without one, the upload still runs the four deterministic stages and says so.

Source PDFs are not in the repository (published corporate documents, excluded by
`.gitignore`). Everything derived from them is committed, so a fresh clone runs.

---

## Limits

- **Validation scale.** 29 random blind labels. The method is general; the measured
  accuracy is not a population estimate. No feature-selection search was run for that
  reason — 2²⁶ candidate subsets against 29 items fits noise.
- **Rule coverage is now measured, and it is poor.** The 10 class-C rules with no prior
  coverage score 0.250 precision against 0.667 for the rest. They stay in the tree
  because 1–2 labels each cannot justify deleting them; they are not to be read as
  validated.
- **Recall survived its first real attempt to break it.** Four probe claims the tree
  calls A or B were annotated blind; none turned out to be a missed flag. Four probes
  cannot establish recall of 1.000 — they can only fail to refute it, which is what
  happened.
- **One confidence signal remains untestable here.** Whether a rule has ever been
  checked is collinear with which sample its claims came from, so this data cannot
  separate the two. Testing it needs more *random* annotation, not more strata.
- **Single reporting year**, so no comparison against prior disclosures.
- **No external evidence.** Claims are checked against the document that makes them —
  the reason the 57-of-59 result exists. Retrieval against filings and certification
  records is the next step.
- **One label per claim**, chosen by traversal order when several apply.
