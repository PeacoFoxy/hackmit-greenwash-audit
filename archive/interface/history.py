"""Upload history: record every analysed document and keep its result, so the page can
be reopened and the analysis revisited.

data/uploads/<hash>.json holds the full result; data/upload_history.json is the index.
"""
import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # repo root: archive/interface/ -> .
DATA = ROOT / "data"
STORE = DATA / "uploads"
INDEX = DATA / "upload_history.json"


def file_hash(file_bytes):
    return hashlib.md5(file_bytes).hexdigest()[:12]


def load_index():
    if not INDEX.exists():
        return []
    try:
        return json.loads(INDEX.read_text(encoding="utf-8"))
    except Exception:
        return []


def save(result, file_bytes, grade=None):
    """Write the result and prepend to the index. Re-uploading a file only updates its
    timestamp; it is not listed twice."""
    STORE.mkdir(parents=True, exist_ok=True)
    h = file_hash(file_bytes)
    (STORE / f"{h}.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")

    entry = {
        "hash": h,
        "filename": result.get("filename", "unknown.pdf"),
        "analysed_at": time.strftime("%Y-%m-%d %H:%M"),
        "sentences": result.get("n_sentences", 0),
        "passages": len(result.get("regions", [])),
        "claims": len(result.get("claims", [])),
        "commitments": result.get("n_commitments", 0),
        "grade": grade,
        "partial": bool(result.get("extract_error")),
    }
    index = [e for e in load_index() if e["hash"] != h]
    index.insert(0, entry)
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    return entry


def load(h):
    path = STORE / f"{h}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def forget(h):
    """Drop one entry from the index and delete its result file."""
    (STORE / f"{h}.json").unlink(missing_ok=True)
    INDEX.write_text(json.dumps([e for e in load_index() if e["hash"] != h],
                                ensure_ascii=False, indent=1), encoding="utf-8")
