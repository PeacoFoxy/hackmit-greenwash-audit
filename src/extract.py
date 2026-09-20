"""Stage 3b：LLM 把长文本切成原子 claim。data/corpus.json → data/claims.json。[LLM]"""
import json, re, os
from src.llm import ask
from src.segment_patch import windows

# 只保留含环境宣称信号的段落，把 94 万字符砍到可处理规模
SIGNALS = re.compile(
    r"(100%|carbon|renewable|net.?zero|emission|PUE|water|offset|REC|"
    r"PPA|sustainab|green|climate|scope\s*[123])", re.I)

SYSTEM = """You extract atomic environmental claims from corporate reports.
An atomic claim is ONE assertion that can be independently checked for evidence.
Split compound sentences. Skip pure narrative, headers, and page furniture.
Output ONLY a JSON array, no prose, no markdown fences."""

PROMPT = """Extract atomic environmental claims from this excerpt.

COMPANY: {company}
EXCERPT:
{chunk}

Output JSON array, each item:
{{"text": "the claim verbatim or lightly cleaned",
  "topic": "energy|emissions|water|waste|other"}}

Return [] if no real claims. Max 12 items."""


def paragraphs(text, lo=150, hi=1200):
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if lo < len(p.strip()) < hi and SIGNALS.search(p)]


def main(per_doc=45):
    docs = json.load(open("data/corpus.json"))
    claims, n = [], 0
    for d in docs:
        paras = windows(d["text"])
        print(f"{d['id']}: {len(paras)} 个候选段落")
        # 均匀取样，覆盖全文而非只看开头
        step = max(1, len(paras) // per_doc)
        picked = paras[::step][:per_doc]
        for i in range(0, len(picked), 3):
            chunk = "\n\n".join(picked[i:i+3])
            raw = ask(PROMPT.format(company=d["company"], chunk=chunk), system=SYSTEM)
            raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.M).strip()
            try:
                for c in json.loads(raw):
                    n += 1
                    claims.append({
                        "claim_id": f"{d['id']}_{n:03d}",
                        "company": d["company"], "ticker": d["ticker"],
                        "text": c["text"], "topic": c.get("topic", "other"),
                        "source_id": d["id"], "source_url": d["url"],
                        "source_date": d.get("pdf_created")})
            except Exception as e:
                print(f"  parse fail: {e}")
    json.dump(claims, open("data/claims.json", "w"), ensure_ascii=False, indent=1)
    print(f"\n共 {len(claims)} 条 claim → data/claims.json")


if __name__ == "__main__":
    main()
