# src/experiments/

Ideas that were built, measured, and rejected on their own numbers.

They are not archived, and `run_all.sh verify` still runs all three, because in this
project the measurement that killed an idea *is* the result. The README cites each of
them. An idea that was never tried proves nothing; an idea that was tried and failed
narrows the search.

| Module | The idea | What the measurement said |
| --- | --- | --- |
| `abstain.py` | Let the system answer "not sure" on low-confidence claims. Five proxies: fraction of CLOSED nodes on the path, whether the deciding node was CLOSED, terminal severity, agreement with one model, agreement with three. | **None beats random abstention.** Dropping any claims raises accuracy by shrinking the sample, so the control is discarding the same number at random. Every proxy landed inside it. |
| `rule_evidence.py` | Score rules without labels, using Track S lift as an unsupervised fitness in place of MAD (Abualigah & Khader 2017). A rule whose claims sit in a low percentile is pointing at a systematic gap. | **Self-refuting.** It ranked the one rule with a bootstrap interval clear of zero as the least suspicious of all. Kept with that diagnosis written into the module. |
| `evidence_tier.py` | Use "has this rule ever been checked against a human label?" as a confidence signal. The tier was fixed before the stratified claims were annotated, so it is a genuine prior prediction. | **Untestable here, and the naive control says otherwise.** It beats a pooled-random control, 0.806 against p95 0.710. The tier is almost collinear with which sample a claim came from, and the two samples differ in accuracy by design; a source-stratified control removes the effect entirely. Recorded as untestable, not as a win. |

Two more rejected ideas live elsewhere, because they are changes to a module rather
than modules of their own:

- **Context cross-checking** (`src/tree.py`, `CROSS_CHECK_ENABLED = False`). Clear a
  flag when the disclosure it says is missing appears in a nearby sentence. Class-C
  balanced accuracy fell 0.868 to 0.697; of 8 claims cleared, 1 was right. Boundary
  phrases recur every few sentences, so proximity never proved the qualifier was bound
  to that figure. The implementation and all three window measurements are kept in
  comments beside the switch.
- **Flag hints to the model** and **ensemble voting** (`src/evaluate.py`, as the
  `pipeline_allflags` arm and the combination sweep). 20% more input tokens for 3.5
  points lower accuracy; 16 voting combinations, none beating the rule tree alone.
