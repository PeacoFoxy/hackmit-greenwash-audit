"""全项目唯一的 LLM 入口：带磁盘缓存 + 重试。缓存命中不发请求，断网也能复现结果。"""
import os, json, hashlib, time
from pathlib import Path

from anthropic import Anthropic


def _load_env(path=Path(__file__).resolve().parent.parent / ".env"):
    """读项目根目录的 .env。不引入依赖；已存在的环境变量优先，文件缺失就跳过。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""), timeout=120.0)
CACHE = "cache"
os.makedirs(CACHE, exist_ok=True)


def ask(prompt, system="", model="claude-sonnet-4-6", max_tokens=2000, tries=3):
    """带磁盘缓存 + 重试的 LLM 调用。缓存命中不发请求。"""
    key = hashlib.md5((model + system + prompt).encode()).hexdigest()
    path = os.path.join(CACHE, f"{key}.json")
    if os.path.exists(path):
        return json.load(open(path))["text"]

    last = None
    for i in range(tries):
        try:
            kw = {"model": model, "max_tokens": max_tokens,
                  "messages": [{"role": "user", "content": prompt}]}
            if system:
                kw["system"] = system
            resp = client.messages.create(**kw)
            text = resp.content[0].text
            json.dump({"prompt": prompt, "system": system, "text": text},
                      open(path, "w"), ensure_ascii=False)
            return text
        except Exception as e:
            last = e
            print(f"  (重试 {i+1}/{tries}: {type(e).__name__})")
            time.sleep(2 * (i + 1))
    raise last
