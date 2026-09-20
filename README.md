# TextQuant — finding the claims that are true and incomplete

HackMIT 2026 · Arrowstreet greenwashing challenge

Corporate environmental reports rarely lie. They disclose a figure and omit the one thing
that would let you check it: the accounting method, the boundary, the absolute total, the
definition of the term. This tool reads a sustainability report, finds the passages where
that pattern clusters, classifies individual claims by *which* disclosure is missing, and
tells an analyst what to ask for.

It is a triage tool, not a verdict machine. Everything it outputs is a pointer to a
passage and a reason, with the company's own words shown first.

---

## Quick start

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app_v2.py
```

That is the whole setup, and it was verified end to end: a clone into an empty directory
plus a fresh virtualenv from `requirements.txt` starts the interface and renders every
panel. **No API key is required** and the page works with the network
off: every LLM call in the demo path is served from the `cache/` directory, keyed by a
hash of the prompt. This was tested by running the app with `ANTHROPIC_API_KEY` unset.

The cache is committed (175 responses, 732 KB), so the evaluation table can be
reproduced without a key and without spending anything: `./run_all.sh` re-runs every
LLM step against it. The calls it holds cost about $0.45 in total.

Uploading your own PDF does need a key for the claim-extraction stage. Without one, the
upload still runs the four deterministic stages (parse, rules, signals, passage
detection) and says so rather than failing.

### API keys

The project calls exactly one external service: the Anthropic API, for claim extraction
and for the LLM comparison baselines. Supply the key either as an environment variable
or in a `.env` file at the repository root:

```bash
cp .env.example .env     # then fill in ANTHROPIC_API_KEY
```

`.env` is excluded by `.gitignore` and is loaded without any extra dependency; an already
exported environment variable always wins. `requirements.txt` holds Python packages only
— never credentials.

**The three source PDFs are not in this repository.** They are published corporate
reports and are excluded by `.gitignore`. Everything derived from them — sentences,
signals, claims, labels, metrics — is committed under `data/`, so a fresh clone runs the
full interface without them.

---

## What the numbers are

Evaluated on 29 human-annotated claims (A 6 / B 13 / C 10). Majority-class baseline is
0.448.

| Method | API calls | accuracy | balanced acc | C precision | C recall | C specificity |
| --- | --- | --- | --- | --- | --- | --- |
| **Rule tree** | **0** | **0.793** | **0.756** | 0.667 | 1.000 | 0.737 |
| LLM, full rubric | 21 / 100 claims | 0.690 | 0.656 | 0.636 | 0.700 | 0.789 |
| LLM + rule hints | 21 / 100 claims | 0.655 | 0.601 | 0.538 | 0.700 | 0.684 |
| LLM, short rubric | 21 / 100 claims | 0.586 | 0.615 | 0.000 | 0.000 | 1.000 |
| TF-IDF + LinearSVC (LOO-CV) | 0 | 0.483 | 0.382 | 0.375 | 0.300 | 0.737 |

**We do not claim the rule tree is more accurate.** A Friedman test across the 29 claims
gives χ² = 4.82, p = 0.31; the Nemenyi critical difference is 1.13 mean-rank units and the
whole field of five methods fits inside it. No pair survives a McNemar test with Holm
correction (0 of 20 comparisons reach p < 0.05). At n = 29 the standard error on accuracy
is about 0.075.

What *is* established: the rule tree costs **0 API calls and ~1 ms per 100 claims**, where
the LLM methods cost 21 calls and $0.037–$0.051 per 100 claims; every decision carries a
root-to-leaf rule path; and it locates the passage in the report.

One result does not depend on any accuracy claim. Without the four-class rubric the model
detects **no** accounting-misleading claims at all — precision, recall and F1 are exactly
zero while overall accuracy stays at 0.586, because "always answer B" scores well on this
distribution. Accuracy alone hides that completely.

---

## The strongest single finding

**57 of 59 quantified commitments cannot be progress-checked from the report that makes
them.** A target is stated; the figures needed to measure progress against it are not in
the same document. This is structural, label-free, and reproducible from
`data/trajectory_audit.json`.

---

## What we measured and then removed

Five ideas were built, measured, and rejected on evidence. They are kept in the repository
with their numbers because a negative result that cost work is still a result.

| Idea | Measured outcome | Status |
| --- | --- | --- |
| Feed rule flags to the LLM as structured hints | 20% more input tokens, 3.5 points *lower* accuracy than the same prompt without hints | Not shipped; kept as an ablation row |
| One near-universal flag (`SCOPE_BOUNDARY_UNCLEAR`, fires on 8–16% of sentences) | Removing it lowered the anomaly threshold 27–42% and *raised* passages found from 11 to 13 | Removed from the detector |
| Context cross-check: clear a flag if the missing qualifier appears in nearby sentences | C balanced accuracy 0.868 → 0.821 (±1 sentence) → 0.697 (±5). Of 8 claims cleared, 1 was correct | Implemented, disabled by default (`CROSS_CHECK_ENABLED = False`) |
| Ensemble voting across methods | 16 voting and cascade combinations tested; none beat the rule tree alone (best 0.759 vs 0.793) | Not shipped |
| Abstention on low confidence | Five confidence proxies tested, including the tree's own CLOSED/OPEN node reliability. None beats random abstention at the 95th percentile; the best is one claim short of significance (17/20, needs 18/20) | Not shipped |

The cross-check failure has a specific cause worth stating: words like `global operations`
recur every few sentences in these reports, so proximity does not imply the qualifier
binds to that figure — which is exactly the misleading pattern the rule was meant to catch.

---

## What the rule layer is actually made of

The decision tree has 26 terminals. A per-rule ablation with a paired bootstrap
(`src/ablation.py`) shows how much of that is load-bearing:

- **5 terminals never fire** on the 390-claim corpus.
- **10 more fire but are never exercised by the gold set**, so their contribution is
  unmeasured.
- Removing all 15 changes the metrics by **exactly nothing** (26 → 12 terminals, identical
  accuracy, recall and specificity).
- Removing the next 4 costs 0.103 accuracy and drops C recall from 1.000 to 0.400.

Only one terminal (`INTENSITY_NO_ABSOLUTE`) has a bootstrap interval excluding zero on its
own. **Individually insignificant is not the same as jointly useless**: the four rules
whose intervals straddle zero collectively carry a tenth of the accuracy. Single-factor
ablation cannot see joint contribution, and an earlier draft of this README drew the wrong
conclusion from it.

---

## The disclosure grade, and how far to trust it

Three sub-scores averaged into a letter (`src/indicators.py`). The thresholds were chosen
by the author, not fitted to outcome data — there is no dataset of correctly graded
reports to calibrate against.

A parameter sweep (`src/sensitivity.py`) is the only honest defence available, and it says
two different things about two different claims:

- **The letter is fragile.** Shifting all three band edges by up to 12 points flips two of
  the three reports. One report sits 3 points from a boundary. The interface shows this
  margin next to the letter.
- **The ordering is not.** Across every sweep — band edges, promise-balance ceiling,
  verification target — the ranking of the three reports never changes once.

One sub-score is inert: sweeping the promise-balance ceiling from 3 to 8 leaves every
letter unchanged on this corpus. It is kept for reports with extreme promise-to-
verification ratios, and the interface says it contributes no separation here.

---

## How a document is processed

```
PDF
 └─ ingest            pypdf → raw text
    └─ signals        sentence split, prose filter (4373 → 4084), 7 scalars per sentence
       ├─ rules       9 accounting regexes per sentence                     0 LLM calls
       ├─ anomaly     8 high-precision flags → smoothed density → mean+2σ   0 LLM calls
       │              → 13 passages across 3 reports
       ├─ extract     atomic claims (batched, capped at 150 sentences)      LLM
       │  └─ tree     22 nodes / 26 terminals → label + mechanism + path    0 LLM calls
       └─ trajectory  quantified targets, paired with observations          LLM
          └─ indicators + grade + recommended action
```

Four mechanisms are distinguished: `UNDISCLOSED_METHOD`, `UNDISCLOSED_BOUNDARY`,
`SELECTIVE_AGGREGATION`, `UNDEFINED_TERM`. Each one maps to a concrete request an analyst
can send to investor relations, shown in the interface under **What to ask for**.

---

## Reproducing

```bash
./run_all.sh            # full pipeline, needs the PDFs and an API key
./run_all.sh offline    # deterministic layers only, no key needed
```

`run_all.sh` regenerates the core data files but **does not cover every module**. Missing
from it: `prelabel`, `trajectory`, `ablation`, `sensitivity`, `rule_evidence`, `cost`,
`stats_tests`, `plot_stats`, `plot_trajectory`, `plot_discard`, `indicators`,
`expand_gold`. Their outputs are committed, so the interface does not depend on running
them; run each with `python -m src.<module>`.

Since the PDFs are not in the repository, a fresh clone cannot run `run_all.sh` at all.
It can run the interface, which was verified by cloning into a clean directory and
starting the app with no API key.

---

## Known limitations

- **29 labelled claims.** This is the binding constraint on everything. It is why no
  metaheuristic feature-selection search was run over the rule set: with 2²⁶ possible
  subsets and 29 items, a wrapper search would fit noise, which the feature-selection
  literature warns about explicitly.
- **10 of 19 accounting rules have never been checked against a human label.** A
  stratified annotation sheet for them is generated by `src/expand_gold.py`; it is not yet
  filled in. The sheet is blind by construction — the answer key it writes alongside is
  excluded from the repository and regenerated deterministically from a fixed seed.
- **C recall is 1.000, and that is not yet falsifiable.** No gold claim exists that the
  tree labels A and a human labels C. Four probe claims are included in the annotation
  sheet specifically to look for such cases.
- **Single reporting year per company.** No comparison against prior disclosures.
- **No external evidence retrieval.** Claims are checked against the document that makes
  them, which is why the 57-of-59 result exists. Checking against life-cycle assessments,
  filings or certification records is the obvious next step and is not implemented.
- **Publication dates are PDF creation dates** read from file metadata, not verified
  publication dates. Source URLs are absent rather than guessed.
- The label taxonomy is single-assignment. A claim that omits both a method and a boundary
  gets one label, decided by traversal order.

---

## Repository map

| Path | What it is |
| --- | --- |
| `app_v2.py` | The interface (analyst terminal layout) |
| `app.py` | Earlier single-column version, kept working |
| `src/tree.py` | The rule decision tree, 0 LLM calls |
| `src/rules.py` `src/signals.py` `src/anomaly.py` | Deterministic feature and passage layers |
| `src/extract.py` `src/llm.py` | Claim extraction and the single cached LLM entry point |
| `src/evaluate.py` `src/stats_tests.py` `src/plot_stats.py` | Metrics, significance tests, figures |
| `src/ablation.py` `src/sensitivity.py` `src/cost.py` | Rule audit, parameter sweeps, cost accounting |
| `src/abstain.py` `src/rule_evidence.py` | The two experiments that produced negative results |
| `src/pipeline.py` | Live upload path |
| `workflow/` | The written specifications the code was built against |
| `data/` | All derived data, committed so the interface runs from a clean clone |
