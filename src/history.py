"""上传历史：记录每一份分析过的文档，并把结果存下来，重开页面还能点回去看。

data/uploads/<hash>.json 存完整结果，data/upload_history.json 存索引。
"""
import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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
    """写结果 + 追加索引。同一份文件重传只更新时间戳，不重复入列。"""
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
    """从索引里移除一条（结果文件一并删除）。"""
    (STORE / f"{h}.json").unlink(missing_ok=True)
    INDEX.write_text(json.dumps([e for e in load_index() if e["hash"] != h],
                                ensure_ascii=False, indent=1), encoding="utf-8")
