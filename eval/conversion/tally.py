"""Tally the blind judges: map A/B back to converters, keep a point only where both passes agree.
Usage: tally.py <work dir>"""

import glob
import json
import sys
from collections import Counter
from pathlib import Path

POINTS = [
    "reading_order",
    "headings",
    "lists",
    "tables",
    "figures",
    "inline_formatting",
    "completeness",
    "noise",
    "overall",
]
work = Path(sys.argv[1])
key = json.loads((work / "key.json").read_text())
runs = {"pass1": {}, "pass2": {}}
for f in glob.glob(str(work / "results" / "*.json")):
    runs[Path(f).stem.split("-")[0]].update(json.loads(Path(f).read_text()))


def named(v, ab):
    """The converter a judge's "A" or "B" stands for; other answers unchanged."""
    return ab.get(v, v)  # "A"/"B" -> converter; tie/na unchanged


agreed, issues = {}, {}
for stem, k in key.items():
    if stem not in runs["pass1"] or stem not in runs["pass2"]:
        print("missing", stem)
        continue
    v1 = {p: named(runs["pass1"][stem].get(p), k["pass1"]) for p in POINTS}
    v2 = {p: named(runs["pass2"][stem].get(p), k["pass2"]) for p in POINTS}
    agreed[stem] = {p: (v1[p] if v1[p] == v2[p] else "split") for p in POINTS}
    issues[stem] = {"ours": [], "docling": []}
    for pass_ in ("pass1", "pass2"):
        for label, name in k[pass_].items():
            issues[stem][name] += runs[pass_][stem].get(f"issues_{label}", [])

print(f"{len(agreed)} pages\n")
print(f"{'point':18} {'ours':>5} {'docling':>8} {'tie':>5} {'split':>6} {'n/a':>5}")
for p in POINTS:
    c = Counter(v[p] for v in agreed.values())
    print(f"{p:18} {c['ours']:>5} {c['docling']:>8} {c['tie']:>5} {c['split']:>6} {c['na']:>5}")
print("\nper page (overall):")
for stem, v in agreed.items():
    print(f"  {stem:50} {v['overall']}")
(work / "tally.json").write_text(json.dumps({"agreed": agreed, "issues": issues}, ensure_ascii=False, indent=1))
