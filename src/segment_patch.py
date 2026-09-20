"""Cut long text into candidate passages for the model. Used by extract.py, not run alone."""
import re, json

SIGNALS = re.compile(
    r"(100%|carbon|renewable|net.?zero|emission|PUE|water|offset|REC|"
    r"PPA|sustainab|green|climate|scope\s*[123])", re.I)

def windows(text, size=5, lo=200, hi=1500):
    """Split on sentences, then window them. PDF text has no reliable paragraph breaks."""
    text = re.sub(r"\s+", " ", text)
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    out, i = [], 0
    while i < len(sents):
        w = " ".join(sents[i:i+size]).strip()
        if lo < len(w) < hi and SIGNALS.search(w):
            out.append(w)
        i += size
    return out

if __name__ == "__main__":
    for d in json.load(open("data/corpus.json")):
        print(f"{d['id']}: {len(windows(d['text']))} candidate windows")
