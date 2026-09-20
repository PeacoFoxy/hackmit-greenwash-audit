# Classification layer v2 — three parallel NLP tracks

Implementation spec for `src/tree.py`, `src/termstats.py` and `src/consensus.py`.
Replaces the flat flag list in `src/rules.py` and the single-shot LLM classifier.

Status: **spec, not implemented.**

---

## 0. Where this sits in the pipeline

Stages 1–4 are built and frozen. This document specifies stage 5.

```
Stage 1  INGEST                     3 PDFs, 938k chars
                    │
Stage 2  PREPROCESSING              4,084 prose sentences
         line-join repair, sentence split, 6.6% filtered
                    │
         ┌──────────┴──────────┐
Stage 3a FEATURE EXTRACTION    Stage 3b  CLAIM EXTRACTION
         7 signals/sentence         390 claims → 89 candidates
                    │                      │
Stage 4a TEXT ANALYSIS                     │
         PVR, z-scores,                    │
         13 anomaly regions                │
         (unsupervised)                    │
                                           ▼
Stage 5  ═════════════ CLASSIFICATION LAYER ═════════════

         ┌─────────────┬─────────────┬─────────────┐
         │  TRACK R    │  TRACK D    │  TRACK S    │
         │ rules-based │ deep-learn  │ statistical │
         │   (tree)    │  (rubric)   │ (term risk) │
         │  0 API      │  1 call     │  0 API      │
         │  calls      │  per claim  │  calls      │
         └──────┬──────┴──────┬──────┴──────┬──────┘
                │             │             │
                └─────────────┼─────────────┘
                              ▼
                     CONSENSUS LAYER  (§4)
                     agree → label + high confidence
                     differ → contested, ranked first
                              │
Stage 6  EVALUATION    against 30 blind gold labels
```

**All three tracks run on every claim.** No routing, no branching between them.
Each produces its own verdict independently, and the consensus layer compares.

**What stage 5 consumes**: one atomic claim from stage 3b, its `company`,
`source_url`, `source_date`, and the seven signal values for its sentence.

**What it replaces**: `flags()` and the single-shot classifier. `vagueness()`
stays — the signal and anomaly layers depend on it and are untouched.

---

## 1. Why three parallel tracks

**Disagreement is the product.** A deterministic tree and a semantic model fail
in different ways. The tree misses paraphrase; the model over-suspects — of 7
gold-A claims it labelled 5 as C. Where both agree, confidence is high. Where
they differ, a human should look. That ranking is useful **without any ground
truth**, which matters because the labels come from one annotator.

A routing design would pick one track per claim and discard this signal
entirely.

**Each track answers a different question.**

| track | question | fails when |
| --- | --- | --- |
| R — rules | Are the required disclosures literally present? | the disclosure is paraphrased |
| D — deep learning | Does this read as adequately disclosed? | it over-suspects; it doesn't know REC accounting |
| S — statistical | Does this term usually appear without its qualifier? | the term is rare in the corpus |

**Measured justification.** Track D alone scores **0.000 C-class F1** without the
rubric and 0.600 with it. Track R supplies knowledge the model does not have.
Neither dominates.

---

## 2. Design rules

1. Every claim passes through all three tracks.
2. The tree reaches a terminal for every claim — no claim exits unlabelled.
3. `A` is reachable in the tree. At least one terminal per domain returns it.
4. Every terminal names one mechanism (§3).
5. The consensus layer never invents a label the tracks did not produce.
6. Contested claims are surfaced, not silently resolved.

---

## 3. Mechanism taxonomy

Every terminal maps to exactly one mechanism. This is the framework claim:
vocabulary changes constantly, the mechanisms appear closed.

| mechanism | definition | canonical example |
| --- | --- | --- |
| `UNDISCLOSED_METHOD` | An accounting choice exists and was not stated | market-based vs location-based Scope 2 |
| `UNDISCLOSED_BOUNDARY` | Coverage of the figure is unstated | which facilities, which scope, which fiscal period |
| `SELECTIVE_AGGREGATION` | A favourable slice replaces the whole | fleet-best PUE, intensity without absolute, regional CFE |
| `UNDEFINED_TERM` | A term with no standard definition carries the claim | *diverted*, *inset*, *replenished* |

The coverage-gap scan produced 51 candidate terms from 58 unflagged quantitative
claims; every surviving one fell into these four. A future candidate fitting
none of them is a finding about the framework — record it rather than force it.

---

## 4. Consensus layer

Input: `(label_R, terminal_R, severity_R)`, `(label_D, confidence_D,
reasoning_D)`, `(risk_S, contributing_terms_S)`.

### Output states

| state | condition | final label | triage rank |
| --- | --- | --- | --- |
| `CONFIRMED` | `label_R == label_D` | that label | by severity |
| `CONTESTED` | `label_R != label_D` | both reported | **first** |
| `RULE_ONLY` | tree hit a sev-3 CLOSED terminal, model said A | `C`, noted | **first** |
| `NOVEL` | tree says A, model says C, and `risk_S` is high | `C`, noted | **first** |

`RULE_ONLY` exists because sev-3 CLOSED terminals are terms of art — if
`matched` is present and no method is stated, that is a fact about the sentence,
not an interpretation. The tree is not overruled there.

`NOVEL` is the rule-discovery path: the tree has no branch for the term, the
model is suspicious, and the statistical layer confirms the term habitually
appears without qualifiers. **These are the claims that should become new tree
branches.** Log them to `data/candidate_rules.json`.

### What not to do

**Do not average the two labels or pick a winner by confidence.** Model
self-reported confidence is not calibrated, and you have 30 labels — nowhere
near enough to fit a weighting. Report both, rank contested first, move on.

### The metric this enables

Split the 30-claim gold set by consensus state and report accuracy separately:

```
                    n    accuracy
CONFIRMED          ??       ??
CONTESTED          ??       ??
```

**If accuracy on `CONFIRMED` is materially higher than on `CONTESTED`, the
agreement flag is a working confidence signal** — a real result, and it needs no
extra labelling. If the two are equal, agreement carries no information and you
report that instead.

---

## 5. Track S — statistical NLP

Learned from the corpus. No labels, no API calls.

### The idea

Some terms reliably appear alongside their qualifier; others reliably do not.
*Scope 2* almost always appears near a method statement. *Matched* almost never
does. That difference is measurable directly from 4,084 sentences, and it is a
learned statistical property of the corpus — not a rule anyone wrote.

### Definition

For each qualifier class `Q` (reuse the tree's CLOSED regex tests):

- `method_stated` — market-based | location-based | grid-supplied
- `baseline_stated` — since 20XX | vs 20XX | base year
- `scope_stated` — scope 1/2/3 | direct operations | value chain
- `verifier_named` — assured | verified | audited | third-party | certified

For each candidate term `t` (unigrams, bigrams and trigrams appearing ≥ 5
times, stopwords removed):

```
P(Q)        = sentences containing Q / all sentences          # base rate
P(Q | t)    = sentences containing both t and Q / sentences containing t
lift(t, Q)  = P(Q | t) / P(Q)
```

**`lift < 1` means the term systematically appears without that qualifier.**

Report alongside the raw count — a term seen 6 times with lift 0.0 is weaker
evidence than one seen 80 times with lift 0.3.

### Per-claim risk score

```
risk_S(claim) = mean over terms t in claim of (1 - min(lift(t, Q_relevant), 1))
```

where `Q_relevant` is chosen by the claim's domain: energy → `method_stated`,
emissions → `scope_stated` and `baseline_stated`, and so on.

### The forward-looking use

This is what makes the layer predictive rather than descriptive. A new term
appears in a report — *insetting*, *hourly matching*, *Scope 4*. It has no tree
branch. Compute its lift profile:

- **Low lift, sufficient count** → it behaves like `matched`: a term that carries
  quantitative claims while the qualifier stays absent. **Candidate new rule.**
- **High lift** → it usually travels with its disclosure. Not a risk term.

The rule layer stops being a fixed list and becomes something the corpus
extends. This is the answer to "won't your rules go stale?"

### Honest limits — state these in the README

- **4,084 sentences is small for n-gram statistics.** Terms need ≥ 5
  occurrences, and even then the intervals are wide.
- **One year, one sector, three issuers.** These priors do not transfer. An
  energy company's corpus would produce different lifts.
- **Lift is co-occurrence, not causation.** A low lift means the qualifier is
  usually absent nearby — it does not establish intent.
- **The true version is temporal.** Pull each issuer's reports for 2019–2025
  and compute lift per year. A term whose lift *declines* over time is one
  whose disclosure quality is eroding. That needs a multi-year corpus, which is
  a download away but not in scope tonight.

### Output

`data/term_risk.json`, sorted by lift ascending within each qualifier class.
Print the 20 lowest-lift terms with count ≥ 10 — that list is a demo artifact
on its own.

---

## 6. Track R — the decision tree

Node format: `ID [RELIABILITY] question`

`CLOSED` = the concept has a fixed vocabulary of terms of art, so a regex miss
reliably means the concept is absent. `OPEN` = the concept has many phrasings,
so a miss is only weak evidence. **Both are evaluated by regex in this track** —
the marking tells you where the tree is weak, and predicts where it will differ
from track D.

```
T0  [OPEN]   Is this a claim about the company's own environmental performance?
    ├── no ──────────────────────────────────────────────► SKIP
    └── yes
        │
T1  [CLOSED] Does the claim contain a quantity?
        │    digits, or all/every/none/100%
        ├── no ──────────────────────────────────────────► B  (vague)
        └── yes
            │
T2  [CLOSED] Is the quantity forward-looking?
            │  will | by 20XX | aim to | target | plan to | expect | commit to
            ├── yes ─► T3
            └── no  ─► T4
```

### T3 — targets

```
T3  [OPEN]   Interim milestone or accountability mechanism present?
    ├── no ──► C  FUTURE_PROMISE_NO_MILESTONE      sev 2   UNDISCLOSED_BOUNDARY
    └── yes
        │
T3a [OPEN]   Target scope or baseline stated?
        ├── no ──► C  TARGET_SCOPE_UNSTATED        sev 2   UNDISCLOSED_BOUNDARY
        └── yes ─► A  SUBSTANTIATED_TARGET
```

### T4 — domain routing

```
T4  [CLOSED] Which domain?
    PUE | CFE | WUE | efficiency | index ─► T9     ← check first
    energy | electricity | power ────────► T5
    emission | carbon | CO2 | GHG ───────► T6
    water | watershed ──────────────────► T7
    waste | recycl | landfill | circular ► T8
    (none) ─────────────────────────────► T10
```

T9 is tested first — "carbon-free energy percentage" is a composite metric, not
an energy claim.

### T5 — energy

```
T5  [CLOSED] Accounting method stated?
    │        market-based | location-based | grid-supplied | on-site generation
    ├── yes ─► T5c
    └── no
        │
T5a [CLOSED] Matching language present?
        │    matched | matching | equivalent to | offset by
        ├── yes ► C  MARKET_BASED_IMPLIED          sev 3   UNDISCLOSED_METHOD
        └── no
            │
T5b [CLOSED] PPAs, RECs or certificates cited?
            ├── yes ► C  INSTRUMENT_NO_METHOD      sev 3   UNDISCLOSED_METHOD
            └── no  ► C  METHOD_UNSTATED           sev 2   UNDISCLOSED_METHOD

T5c [OPEN]   Grid region stated?
    ├── no ──► C  GRID_MISMATCH_RISK               sev 2   UNDISCLOSED_BOUNDARY
    └── yes
        │
T5d [OPEN]   Coverage stated (global / fleet / named facilities)?
        ├── no ──► C  COVERAGE_UNSTATED            sev 1   UNDISCLOSED_BOUNDARY
        └── yes ─► A  SUBSTANTIATED_ENERGY
```

### T6 — emissions

```
T6  [CLOSED] Scope stated?
    │        scope 1 | scope 2 | scope 3 | direct operations | value chain
    ├── no ──► C  SCOPE_UNSTATED                   sev 2   UNDISCLOSED_BOUNDARY
    └── yes
        │
T6a [CLOSED] Intensity metric?
        │    per unit | per shipped | per employee | per dollar |
        │    intensity | normalized
        ├── yes
        │   │
        │   T6a2 [OPEN] Absolute figure also given?
        │       ├── no ──► C  INTENSITY_NO_ABSOLUTE  sev 3  SELECTIVE_AGGREGATION
        │       └── yes ─► T6b
        └── no ─► T6b
            │
T6b [OPEN]   Percentage change given without a baseline year?
            │  since 20XX | vs 20XX | from our 20XX baseline | base year
            ├── baseline missing ► C  NO_BASELINE_YEAR  sev 2  UNDISCLOSED_BOUNDARY
            └── otherwise ─► T6c
                │
T6c [CLOSED]    Neutrality or net-zero asserted?
                ├── no ──────────► A  SUBSTANTIATED_EMISSIONS
                └── yes
                    │
T6c2 [OPEN]         Role of offsets disclosed?
                    ├── no ──► C  OFFSET_UNDISCLOSED  sev 3  UNDISCLOSED_METHOD
                    └── yes ─► A  SUBSTANTIATED_EMISSIONS
```

### T7 — water

```
T7  [CLOSED] Composite water term used?
    │        water positive | water neutral | replenish | restored
    ├── yes
    │   └── [OPEN] Methodology or verifier named?
    │       ├── no ──► C  WATER_TERM_UNDEFINED     sev 3   UNDEFINED_TERM
    │       └── yes ─► A  SUBSTANTIATED_WATER
    └── no
        │
T7a [OPEN]   Watershed or facility scope stated?
        ├── no ──► C  WATER_BOUNDARY_UNSTATED      sev 2   UNDISCLOSED_BOUNDARY
        └── yes ─► A  SUBSTANTIATED_WATER
```

### T8 — waste

```
T8  [CLOSED] Diversion or circularity term used?
    │        diverted | diversion | circular | recovered | recycled content
    ├── yes
    │   │
    │   T8a [CLOSED] Treatment pathway named?
    │       │        composting | recycling | incineration | energy recovery |
    │       │        landfill | anaerobic digestion
    │       ├── no ──► C  DIVERSION_UNDEFINED      sev 3   UNDEFINED_TERM
    │       └── yes ─► T8b
    └── no ─► T8b
        │
T8b [OPEN]   Waste stream or site scope stated?
        ├── no ──► C  WASTE_BOUNDARY_UNSTATED      sev 2   UNDISCLOSED_BOUNDARY
        └── yes ─► A  SUBSTANTIATED_WASTE
```

Incineration-with-energy-recovery counting as *diversion* is a definitional
choice the issuer makes silently. Naming the pathway is what makes the figure
checkable — not the number.

### T9 — efficiency and composite metrics

```
T9  [OPEN]   Metric issuer-defined rather than an industry standard?
    │        standards: PUE, WUE, CUE. Anything else (e.g. "Google CFE") is
    │        issuer-defined.
    ├── yes
    │   └── [OPEN] Definition given or referenced?
    │       ├── no ──► C  PROPRIETARY_METRIC       sev 3   UNDEFINED_TERM
    │       └── yes ─► T9a
    └── no ─► T9a
        │
T9a [OPEN]   Fleet-wide or aggregate figure?
        │    fleet | global | average across | all facilities | portfolio
        ├── yes ─► A  SUBSTANTIATED_METRIC
        └── no
            │
T9b [OPEN]   Regional or per-site breakdown present?
            ├── yes ► C  REGIONAL_ONLY             sev 2   SELECTIVE_AGGREGATION
            └── no  ► C  CHERRY_PICKED_METRIC      sev 3   SELECTIVE_AGGREGATION
```

### T10 — other quantified claims

```
T10  [OPEN]  Verifier or assurance source named?
     ├── yes ─► A  SUBSTANTIATED_OTHER
     └── no
         │
T10a [OPEN]  Coverage boundary stated?
         ├── no ──► C  UNSCOPED_FIGURE             sev 1   UNDISCLOSED_BOUNDARY
         └── yes ─► A  SUBSTANTIATED_OTHER
```

---

## 7. Severity

| sev | meaning | triage rank |
| --- | --- | --- |
| 3 | Active misdirection — a term of art or slice choice reading stronger than it is | first |
| 2 | Material omission — the figure cannot be checked without it | second |
| 1 | Minor omission — checkable with effort | last |

Exactly one terminal per claim; no aggregation needed.

---

## 8. Output contract

```python
{
  "claim_id": "amzn_sr_00297",

  "track_R": {
    "label": "C",
    "terminal": "MARKET_BASED_IMPLIED",
    "mechanism": "UNDISCLOSED_METHOD",
    "severity": 3,
    "path": [
      {"node": "T0",  "reliability": "OPEN",   "answer": "yes"},
      {"node": "T1",  "reliability": "CLOSED", "answer": "yes"},
      {"node": "T2",  "reliability": "CLOSED", "answer": "no"},
      {"node": "T4",  "reliability": "CLOSED", "answer": "energy"},
      {"node": "T5",  "reliability": "CLOSED", "answer": "no"},
      {"node": "T5a", "reliability": "CLOSED", "answer": "yes",
       "span": "matched 100% of the electricity"}
    ]
  },

  "track_D": {
    "label": "C",
    "confidence": 0.81,
    "reasoning": "uses matching language without stating accounting method"
  },

  "track_S": {
    "risk": 0.74,
    "contributing_terms": [
      {"term": "matched", "lift": 0.08, "count": 34, "qualifier": "method_stated"}
    ]
  },

  "consensus": {
    "state": "CONFIRMED",
    "label": "C",
    "triage_rank": 1
  }
}
```

`track_R.path` is the reasoning trace the UI renders. `track_S.contributing_terms`
is what makes the risk score inspectable rather than a black-box number.

---

## 9. Migration from v1

| v1 flag | v2 terminal(s) |
| --- | --- |
| `SCOPE2_METHOD_UNSTATED` | `METHOD_UNSTATED` (2) / `MARKET_BASED_IMPLIED` (3) / `INSTRUMENT_NO_METHOD` (3) |
| `MATCHING_LANGUAGE` | folded into `MARKET_BASED_IMPLIED` |
| `NO_BASELINE_YEAR` | `NO_BASELINE_YEAR` (T6b) |
| `OFFSET_UNDISCLOSED` | `OFFSET_UNDISCLOSED` (T6c2) |
| `GRID_MISMATCH_RISK` | `GRID_MISMATCH_RISK` (T5c) |
| `CHERRY_PICKED_METRIC` | `CHERRY_PICKED_METRIC` / `REGIONAL_ONLY` (T9) |
| `WATER_ACCOUNTING_VAGUE` | `WATER_TERM_UNDEFINED` / `WATER_BOUNDARY_UNSTATED` |
| `FUTURE_PROMISE_NO_MILESTONE` | `FUTURE_PROMISE_NO_MILESTONE` (T3) |
| `SCOPE_BOUNDARY_UNCLEAR` | **retired** |

`SCOPE_BOUNDARY_UNCLEAR` fired on 8–16% of sentences near-uniformly and made up
the majority of all flag hits. Removing it from the anomaly detector lowered
per-company thresholds 27–42% and *increased* regions found from 11 to 13.
Retired, not ported.

**New in v2**, from the coverage-gap scan: `INTENSITY_NO_ABSOLUTE`,
`PROPRIETARY_METRIC`, `REGIONAL_ONLY`, `DIVERSION_UNDEFINED`,
`TARGET_SCOPE_UNSTATED`, `INSTRUMENT_NO_METHOD`.

---

## 10. Regression tests

Terminal and label must both match. All drawn from the corpus.

| claim (abbreviated) | terminal | label |
| --- | --- | --- |
| "Amazon matched 100% of the electricity consumed by its global operations with renewable energy" | `MARKET_BASED_IMPLIED` | C |
| "Google signed contracts for 8 GW of new clean energy generation in 2024" | `SUBSTANTIATED_OTHER` | A |
| "Our Scope 1 and 2 emissions decreased by 30% from the 2020 base year" | `SUBSTANTIATED_EMISSIONS` | A |
| "Emissions from our direct operations increased 2% compared to 2024" | `SUBSTANTIATED_EMISSIONS` | A |
| "We reduced emissions per shipped unit by 39% compared to 2019" | `INTENSITY_NO_ABSOLUTE` | C |
| "In 2024, Alphabet reduced its data center energy emissions by 12% compared to 2023" | `SCOPE_UNSTATED` | C |
| "In Asia Pacific, Alphabet's regional average Google CFE was 12%" | `PROPRIETARY_METRIC` | C |
| "In 2024, we diverted 85% of food waste from landfill through composting" | `SUBSTANTIATED_WASTE` | A |
| "In 2025, 2% of Amazon's waste was diverted through incineration with energy recovery" | `WASTE_BOUNDARY_UNSTATED` | C |
| "By 2030, 100% of our electricity consumption will be matched by zero carbon electricity purchases" | `FUTURE_PROMISE_NO_MILESTONE` | C |
| "Nature-based design solutions are reducing Microsoft's environmental footprint at datacenters" | — (T1 exit) | B |
| "In 2021, Google joined the UN Race to Zero Campaign" | — (T0 exit) | SKIP |

The two *diverted* cases are the discriminating pair: both name a pathway, but
the second lacks a stated waste-stream denominator and exits at T8b.

---

## 11. Implementation and evaluation

### Build order

1. **`src/tree.py`** — nodes as `{id: Node(reliability, test_fn, yes, no)}`,
   terminals as `{id: (label, mechanism, severity)}`. Traverse from T0,
   accumulate path, stop at terminal. Every `test_fn` pure. Zero API calls.
2. **`src/termstats.py`** — lift table over the 4,084 sentences. Zero API calls.
3. **`src/consensus.py`** — join the three tracks, assign state, rank.
4. Track D already exists as `baseline2` in `evaluate.py`.

### Methods to report

| method | API calls | what it measures |
| --- | --- | --- |
| `track_R` | 0 | the rules layer alone |
| `track_D` | 1/claim | existing `baseline2` |
| `consensus` | 1/claim | agreement-gated |

Plus the split table from §4: accuracy on `CONFIRMED` vs `CONTESTED`.

### Do not tune the tree on the gold set

Branch conditions come from the accounting rules, not from fitting the 30
labelled items. Fitting 27 nodes to 29 scored items is exactly the overfitting
this project exists to detect. Write the tree, then measure once.

### Expected outcomes

- `track_R` will likely trail `track_D` on overall accuracy and **may beat it on
  A-class recall**, since the tree has explicit certify-as-A paths and the model
  does not. Either result is reportable.
- `CONFIRMED` accuracy should exceed `CONTESTED`. If it does not, agreement
  carries no information — report that.
- Track S will produce wide intervals on rare terms. Filter to count ≥ 10 before
  drawing any conclusion.

---

## 12. Open questions

- **Fiscal vs calendar year.** Microsoft reports on a fiscal year; a percentage
  change against "2020" means something different from Alphabet's calendar 2020.
  No node tests this. Genuine `UNDISCLOSED_BOUNDARY`, probably belongs at T6b.
- **Scope 3 category share.** "Category 1 represents 34.04% of Scope 3" gives a
  share with no denominator but currently exits at `SUBSTANTIATED_EMISSIONS`
  because scope *is* stated. Likely needs `SHARE_NO_DENOMINATOR` under
  `SELECTIVE_AGGREGATION`.
- **Multi-claim sentences.** One sentence can carry two claims with different
  terminals. The tree assumes one claim per input; splitting is stage 3b's job.
- **Track S sample size.** 4,084 sentences may be too few for stable trigram
  lifts. If the count ≥ 10 filter leaves under 50 terms, report unigrams and
  bigrams only.
- **Consensus on B.** Both tracks agreeing on B is common and uninformative —
  vague claims are easy. Consider reporting `CONFIRMED` accuracy excluding B to
  avoid inflating it.
