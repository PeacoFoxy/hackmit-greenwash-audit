"""PDF to plain text. corpus/*.pdf + corpus/sources.json -> data/corpus.json."""
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
            print(f"  [skip] {s['file']} not found")
            continue
        s["text"] = load(s["file"])
        print(f"  [ok] {s['id']}: {len(s['text'])} characters")
        out.append(s)
    json.dump(out, open("data/corpus.json", "w"), ensure_ascii=False)
    print(f"\n{len(out)} documents")
