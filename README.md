# TextQuant

**Finds the absence of information, not the presence of bad words.**

Sustainability reports rarely lie. They state a real figure and leave out the one thing
that would let you check it: the accounting method, the scope boundary, the absolute
total, the definition of the term. A keyword scanner cannot find that, because there is
no keyword to find.

> *"We reduced emissions per shipped unit by 39% compared to 2019."*

True. Also unverifiable in the direction that matters, because intensity falls while
absolute emissions rise if you ship more units. TextQuant reads a report, splits it into
atomic claims, and labels each one by **which piece of verifying information is missing**.

---

## The design thesis

**The architecture generalizes; the rule set does not, and that separation is the point.**

The rules encode greenhouse-gas accounting, so they are worth nothing outside it. The
structure around them — a decision tree that explains itself, a corpus-statistics layer
that handles vocabulary nobody has seen, a model constrained by a written rubric, and
agreement between the three as a confidence signal — applies wherever disclosure is
technically compliant and materially incomplete. Non-GAAP reconciliations. Clinical
endpoint switching. Fund fee disclosure. Each needs a new rule set from a domain expert,
not a retrained model.

Two consequences run through everything below: **nothing is trained on the corpus**, and
**every label ships with the path that produced it.**

---

## What it found

Four numbers, one formula each, reproducible offline (`python -m src.headline`).

| | Formula | |
| --- | --- | --- |
| Document needing no analyst attention | `1 − claims surfaced / sentences` | **97.8%** |
| Commitments that cannot be progress-checked | `targets with <2 observations / targets` | **96.6%** |
| Rule tree and model reaching the same label | `CONFIRMED / (CONFIRMED + CONTESTED)` | **78.6%** |
| Claims true but missing their basis | `C / (A + C)`, precision-corrected | **45–49%** |

The first three are counting facts. The fourth depends on the classifier being right, so
it is the only interval: the raw ratio is 80.9%, but class-C precision is 0.667 on
validated rules and 0.250 on ten a blind test exposed, and carrying the raw count forward
would import that error.

---

## How it works

```
Report (PDF)
  │
  ├─ 1  PREPROCESSING      text, sentences, prose filter        4,084 sentences
  ├─ 2  FEATURE EXTRACTION 7 language signals + 9 accounting rules per sentence
  ├─ 3  ANOMALY DETECTION  flag density vs the report's own baseline   13 passages
  ├─ 4  CLAIM EXTRACTION   atomic, independently checkable      390 → 89 scored
  │
  └─ 5  THREE TRACKS IN PARALLEL
          Track R   22-node decision tree          0 model calls
          Track S   term × qualifier lift          0 model calls
          Track D   four-class rubric, zero-shot
                         ↓
                    CONSENSUS — agreement as a label-free confidence signal
                         ↓
        6  labels · passages · indicators · the question to send investor relations
```

**Four labels, graded like a credit rating rather than judged true or false.** A rating
does not claim to be objectively true; it claims to follow a published methodology,
applied consistently. That is the right shape for this problem.

| | |
| --- | --- |
| **A** | Substantiated: a concrete figure with its scope or method stated |
| **B** | Vague: no verifiable quantity |
| **C** | **Technically true but incomplete: the figure is real, the basis is missing** |
| **D** | Contradicted by other disclosed information |

Class C is the target. **Without the rubric, a language model finds zero class-C claims**
— precision, recall and F1 all exactly 0.000 — while its overall accuracy still reads
respectable, because always answering B scores well.

**Why three tracks.** Each fails differently, so their agreement costs no annotation, and
each absorbs one of the four ways text defeats a reader:

| Track | Absorbs | Fails when |
| --- | --- | --- |
| **R** rules | *biased training data* — it is not trained, so it inherits no habits. *Misinterpretation* — its root-to-leaf path names the reading it took | the wording is novel |
| **S** statistics | *new vocabulary* — lift is learned from the document's own corpus, so an unseen term still scores | the corpus is small |
| **D** model | *tone of voice* — the rubric grades what is disclosed, never how assertively | it drifts |

---

## How it was optimised

**Thirteen rounds. Six shipped, seven rejected on their own numbers.**

The turning point was a failure. I implemented cross-checking from the literature (Hicks
et al., PMC11404377) and it made things worse: class-C balanced accuracy fell 0.868 →
0.697. Phrases like *global operations* recur every few sentences, so "appears nearby"
never proved the qualifier was bound to *that* figure — exactly the pattern class C
exists to catch. After that, every idea had to survive measurement before shipping.

| Round | Result | |
| --- | --- | --- |
| Accept named facility boundaries, not only scope terms | **accuracy 0.690 → 0.793** | Shipped |
| Add specificity and balanced accuracy to the metrics | exposed that C recall 1.000 was bought with specificity 0.550 | Shipped |
| Blind-test the rules gold had never exercised | validated 0.667 precision, unvalidated **0.250** (p = 0.024) | Shipped |
| Context cross-check *(the paper's idea)* | 0.868 → 0.697 | Rejected |
| Feed rule flags to the model as hints | 20% more tokens, 3.5 points lower accuracy | Rejected |
| Ensemble voting | 16 combinations, none beat the tree alone | Rejected |
| Abstain when confidence is low | 5 proxies, none beat random abstention | Rejected |
| TF-IDF + linear SVM | 0.483 leave-one-out vs a 0.448 majority baseline | Rejected |

The one that worked came from the metrics, not from an algorithm: adding specificity
showed the tree was flagging almost everything, and widening the boundary rule fixed it.
All seven rejected experiments are still in the repository, still run by `verify`, in
`src/experiments/` and documented — the measurement that killed an idea is itself a
result.

---

## What is and is not established

**Established.** The rule tree reaches 0.793 accuracy against the model's 0.690 and
class-C F1 of 0.800 against 0.000 without a rubric, at **0 model calls and $0.00** per
100 claims. Separately, needing no accuracy claim at all: **57 of 59 quantified
commitments cannot be progress-checked from the report that states them.**

**Not established.** The five methods tested are statistically indistinguishable here
(Friedman χ² = 4.82, p = 0.31, no pair surviving McNemar). The rule tree scores highest.
That is not a claim of superiority.

**The hardest part was not fooling myself.** Twice a result looked real and was not. A
confidence signal beat its control 0.806 to 0.710 and turned out to be an artifact of how
the samples were drawn; a source-stratified control removed it entirely, and it is
recorded as untestable rather than as a win. Ten rules had never met a human label, and
when blind-tested scored 0.250 precision against 0.667 for the rest. Both times the fix
was a better control, not a better intention.

Methods chosen so conclusions survive 49 labels rather than depend on them: specificity
and balanced accuracy over recall alone · Friedman with Nemenyi critical difference ·
pairwise McNemar with Holm correction · paired bootstrap, 2,000 resamples ·
leave-one-out · parameter sweeps over every threshold · random-abstention controls ·
stratified sampling over never-exercised rules · blind sheets carrying no model output.

---

## Running it

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
./run_all.sh verify          # reproduce every number above
```

No API key, no PDFs, no network, no spend. All 175 model responses are cached and
committed; `verify` clears `ANTHROPIC_API_KEY` first, so a cache miss fails loudly
instead of quietly spending money.

Reproducibility here means byte-identical. Running `verify` twice and diffing every file
it writes caught three modules that drifted on identical input — all three iterated a
Python `set`, whose order is hash-randomised per process, and one was feeding that order
into a seeded RNG, which made the seed useless. Fixed. The only value that still moves
between runs is a wall-clock timing in `data/cost.json`.

Analysing a new PDF needs a key for the extraction stage; copy `.env.example` to `.env`.
Source PDFs are not committed (published corporate documents), but everything derived
from them is, so a fresh clone runs.

---

## Repository

This submission is the algorithm and the backend. A Streamlit interface was built, then
set aside under `archive/` so it is not mistaken for the product.

```
src/                    the algorithm and the backend
├── ingest · signals · rules · filter · anomaly · extract       the reading pipeline
├── tree · termstats · llm · rubric · consensus                 the three tracks
├── headline · indicators · evaluate · stats_tests              the numbers
├── ablation · sensitivity · expand_gold · merge_expand · cost  the evidence
└── experiments/        built, measured, rejected — and still run by `verify`

data/                   all derived data, committed
├── gold.json           29 random blind labels — the accuracy estimate
├── blind_expand.csv    20 stratified blind labels — the per-rule test
└── annotations.csv     model pre-labels; no gold column, by design
cache/                  175 model responses, committed for reproducibility
figures/ · corpus/ · workflow/DECISION_TREE.md · REFERENCES.md
archive/interface/      the Streamlit UI, kept as record, imported by nothing
```

**How the data is used: nothing is fitted to the labels.** There is no training split
because there is no training. The rules are written from GHG Protocol concepts, the lift
table is unsupervised, the model is zero-shot. The 29 gold claims are only ever scored
against. The one leakage channel that remains is worth naming: **the author saw the gold
set while writing the rules**, which is why the rules were then blind-tested against a
quota drawn over the ones gold had never touched, and why that test is reported
separately and never averaged in.

---

## Limits

- **49 blind labels.** The method is general; the measured accuracy is not yet a
  population estimate. This is the binding constraint on every conclusion here.
- **Ten rules score 0.250 precision.** They stay in the tree because 1–2 labels each
  cannot justify deleting them. They are not to be read as validated.
- **One reporting year**, so no comparison against prior disclosures — and a boundary
  that quietly changes between years is the strongest signal there is.
- **No external evidence.** Claims are checked against the document that makes them,
  which is exactly why the 57-of-59 result exists. Retrieval against filings and
  certification registries is the next step.
