"""Regression set from spec sec. 10: 12 cases drawn from the corpus, each asserting a
terminal and a label."""
from src.tree import classify

CASES = [
    ("Amazon matched 100% of the electricity consumed by its global operations with renewable energy",
     "MARKET_BASED_IMPLIED", "C"),
    ("Google signed contracts for 8 GW of new clean energy generation in 2024",
     "SUBSTANTIATED_OTHER", "A"),
    ("Our Scope 1 and 2 emissions decreased by 30% from the 2020 base year",
     "SUBSTANTIATED_EMISSIONS", "A"),
    ("Emissions from our direct operations increased 2% compared to 2024",
     "SUBSTANTIATED_EMISSIONS", "A"),
    ("We reduced emissions per shipped unit by 39% compared to 2019",
     "INTENSITY_NO_ABSOLUTE", "C"),
    # Boundary is named (data center) + baseline year 2023 -> A. Gold says A; expected
    # value corrected 2026-09-20.
    ("In 2024, Alphabet reduced its data center energy emissions by 12% compared to 2023",
     "SUBSTANTIATED_EMISSIONS", "A"),
    ("In Asia Pacific, Alphabet's regional average Google CFE was 12%",
     "PROPRIETARY_METRIC", "C"),
    ("In 2024, we diverted 85% of food waste from landfill through composting",
     "SUBSTANTIATED_WASTE", "A"),
    ("In 2025, 2% of Amazon's waste was diverted through incineration with energy recovery",
     "WASTE_BOUNDARY_UNSTATED", "C"),
    ("By 2030, 100% of our electricity consumption will be matched by zero carbon electricity purchases",
     "FUTURE_PROMISE_NO_MILESTONE", "C"),
    ("Nature-based design solutions are reducing Microsoft's environmental footprint at datacenters",
     "VAGUE_NO_QUANTITY", "B"),
    ("In 2021, Google joined the UN Race to Zero Campaign",
     "SKIP", "SKIP"),
]


def run():
    passed = 0
    for text, want_terminal, want_label in CASES:
        r = classify(text)
        ok = r["terminal"] == want_terminal and r["label"] == want_label
        passed += ok
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {text[:62]}")
        if not ok:
            print(f"       want {want_terminal}/{want_label}, got {r['terminal']}/{r['label']}")
        trace = " → ".join(f"{n['node']}[{n['reliability'][0]}]:{n['answer']}" for n in r["path"])
        print(f"       {trace}")
        spans = [n["span"] for n in r["path"] if "span" in n]
        if spans:
            print(f"       span: {spans[-1]!r}")
    print(f"\n{passed}/{len(CASES)} passed")
    return passed == len(CASES)


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
