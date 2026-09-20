"""The single model entry point for the project: disk cache plus retries. A cache hit
sends nothing, so results reproduce with the network off."""
import os, json, hashlib, time
from pathlib import Path

from anthropic import Anthropic


def _load_env(path=Path(__file__).resolve().parent.parent / ".env"):
    """Read .env from the project root. No dependency; an exported variable wins, and a
    missing file is simply skipped."""
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
    """Model call with disk cache and retries. A cache hit sends no request."""
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
            print(f"  (retry {i+1}/{tries}: {type(e).__name__})")
            time.sleep(2 * (i + 1))
    raise last
