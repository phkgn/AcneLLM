import json, sys, collections
sys.path.insert(0, "src")
from acne_llm.chat.extraction_confidence import extract_with_confidence

rows = [json.loads(l) for l in open("data/golden_extraction_gen.jsonl", encoding="utf-8") if l.strip()]
def ninf(v): return None if v in (None,"none","unknown") else v
cm = collections.Counter()
fp = collections.defaultdict(collections.Counter); fn = collections.defaultdict(collections.Counter)
for r in rows:
    t = r.get("text","")
    if not t: continue
    ec = extract_with_confidence(t)
    cm[(str(ninf(r.get("inflammation"))), str(ninf(ec.inflammation.value)))] += 1
    for f, pv in [("products",ec.products),("treatment_goals",ec.treatment_goals),
                  ("red_flags",ec.red_flags)]:
        g=set(r.get(f,[]) or []); p=set(pv.values)
        for x in p-g: fp[f][x]+=1
        for x in g-p: fn[f][x]+=1
nl=["None","mild","moderate","severe"]
print("INFLAMMATION  gold\\pred", nl)
for g in nl: print(f"{g:>9}", [cm.get((g,p),0) for p in nl])
for f in ["products","treatment_goals","red_flags"]:
    print(f"\n{f} FP:", fp[f].most_common(15))
    print(f"{f} FN:", fn[f].most_common(15))
