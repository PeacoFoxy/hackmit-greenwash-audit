# archive/

Work that is not part of the algorithm submission, kept because deleting it would
delete the record of how the project got here.

Nothing in this folder is imported by `src/` or run by `run_all.sh`. Removing the
whole directory would not change a single reported number.

## interface/

A Streamlit analyst terminal, built over two versions, then set aside.

The submission is the algorithm and the backend. The interface was a deliberate
trade rather than an unfinished corner: at the end of the first day it was clear
that the interface, the backend and the algorithm could not all be good under the
deadline, so the interface stopped and the algorithm continued. Leaving it in the
main tree would invite it to be judged as the product, which it is not.

| File | What it was |
| --- | --- |
| `app_v2.py` | Two-column terminal: input and process on the left, analysis on the right |
| `app.py` | The first version, a single scrolling column |
| `ui_text.py` | Every user-facing string, so internal codes could never reach the screen |
| `claim_api.py` | Classify one pasted passage: rule tree plus an optional model rationale |
| `pipeline.py` | The live path for an uploaded PDF, stage by stage |
| `report_map.py` | The document map: where flagged passages sit in the report |
| `history.py` | Previously analysed documents, so a result could be reloaded without re-running |
| `FRONTEND.md`, `FRONTEND_V2.md` | The specs both versions were built against |

Both apps still run, from the repository root:

```bash
.venv/bin/streamlit run archive/interface/app_v2.py
```

Paths were rewritten when the files moved here, and both were re-tested headless
afterwards with `AppTest`: no exception, and the metric values unchanged. No API
key is needed; the demo path is served from `cache/`.

## What is NOT archived

Experiments that were measured and rejected live in `src/experiments/`, not here.
They still run under `run_all.sh verify`, because the measurement that rejected
them is itself a result the README cites. See `src/experiments/README.md`.
