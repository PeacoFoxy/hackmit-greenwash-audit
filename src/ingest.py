"""PDF → 纯文本。corpus/*.pdf + corpus/sources.json → data/corpus.json。"""
import json, os
from pypdf import PdfReader

def load(path):
    if path.endswith(".pdf"):
        return "\n".join(p.extract_text() or "" for p in PdfReader(path).pages)
    return open(path, encoding="utf-8").read()

if __name__ == "__main__":
    srcs = json.load(open("corpus/sources.json"))
    out = []
    for s in srcs:
        if not os.path.exists(s["file"]):
            print(f"  [skip] {s['file']} 不存在")
            continue
        s["text"] = load(s["file"])
        print(f"  [ok] {s['id']}: {len(s['text'])} 字符")
        out.append(s)
    json.dump(out, open("data/corpus.json", "w"), ensure_ascii=False)
    print(f"\n共 {len(out)} 份文档")
