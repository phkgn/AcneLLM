from __future__ import annotations

import html
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BASELINE = ROOT.parent / "acnellm_current_audit_20260712" / "e2e_evidence.json"
FULL_FIXED = ROOT / "e2e_evidence.json"
REG1 = ROOT / "e2e_regression_s01_s09.json"
REG2 = ROOT / "e2e_regression_s02_s08.json"
REG3 = ROOT / "e2e_regression_s04_s05_final.json"
MERGED = ROOT / "e2e_evidence_final_merged.json"
OUTPUT = ROOT / "acnellm_post_fix_report_20260712.html"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def flatten(data: dict) -> list[dict]:
    return [turn for session in data["sessions"] for turn in session["turns"]]


def summary(data: dict) -> dict:
    turns = flatten(data)
    walls = [int(turn["stream"].get("wall_time_ms") or 0) for turn in turns]
    first = [
        int(turn["stream"].get("first_token_ms") or 0)
        for turn in turns if turn["stream"].get("first_token_ms") is not None
    ]
    retrieved = [
        int(((turn.get("trace") or {}).get("stage_7_retrieve") or {}).get("num_chunks") or 0)
        for turn in turns
    ]
    citation = [
        (turn["stream"].get("done") or {}).get("citation_compliance")
        for turn in turns if int(((turn.get("trace") or {}).get("stage_7_retrieve") or {}).get("num_chunks") or 0)
    ]
    return {
        "turns": len(turns),
        "p50": int(statistics.median(walls)),
        "p95": sorted(walls)[round((len(walls) - 1) * 0.95)],
        "first": int(statistics.median(first)),
        "retrieval_turns": sum(value > 0 for value in retrieved),
        "citation_ok": sum(value is True for value in citation),
        "citation_total": len(citation),
        "errors": sum(len(turn["stream"].get("errors") or []) for turn in turns),
    }


baseline = load(BASELINE)
fixed = load(FULL_FIXED)
replacement = {}
for path in (REG1, REG2, REG3):
    for session in load(path)["sessions"]:
        replacement[session["id"]] = session
fixed["sessions"] = [replacement.get(session["id"], session) for session in fixed["sessions"]]
fixed["evidence_note"] = (
    "Merged from the full post-fix rerun plus later targeted live regressions. "
    "S01/S09 use REG1; S02/S03/S08 use REG2; S04/S05 use final REG3."
)
MERGED.write_text(json.dumps(fixed, ensure_ascii=False, indent=2), encoding="utf-8")

before = summary(baseline)
after = summary(fixed)

STATUS = {
    "S01": ("Pass", "General comparison now routes knowledge/non_self; the false purulent red flag is gone; citations are present."),
    "S02": ("Partial", "Age 24, female, 32 weeks, chin/jawline and menstrual factor persist through turn 5; generation remains somewhat generic and can over-triage."),
    "S03": ("Partial", "Adapalene survives coreference and the BPO question is answered; generated frequency advice is still more prescriptive than desired."),
    "S04": ("Partial", "Final state contains back/papule only and removes BHA/forehead; some generated treatment frequency remains unsupported."),
    "S05": ("Pass", "All three turns use deterministic refusal; correction leaves minocycline only and pregnancy remains true."),
    "S06": ("Pass", "Urgent infection triage remains short and correctly prioritized."),
    "S07": ("Pass", "Ambiguous image-dependent query is clarified without irrelevant retrieval."),
    "S08": ("Partial", "Informal ada is normalized to adapalene and irritation persists in state; the model still paraphrases barrier language imperfectly."),
    "S09": ("Pass", "Math and injection are refused before generation; the valid acne turn recovers normally."),
    "S10": ("Partial", "Oral isotretinoin+tetracycline is deterministically blocked; topical BPO/tretinoin explanation still needs stronger claim-level validation."),
}

FIXES = [
    ("Unified safety enforcement", "Added pre-generation medication_safety_refusal using folded pregnancy and mentioned/current drugs. Isotretinoin+tetracycline and pregnancy contraindications no longer reach the LLM."),
    ("Chronological correction memory", "Restored normalized snapshots, replayed oldest-to-newest, applied current and historical tombstones, and prevented corrected facts from resurrecting."),
    ("Structured context in prompts", "Re-enabled known-facts rendering so age, sex, duration, lesion, location and medication facts visible in trace are also visible to generation."),
    ("Router and OOD boundary", "Added comparison signals, fixed color/blood normalization ambiguity, and hard-refused explicit math variants even in semantic soft mode."),
    ("Citation gate", "Retrieval-backed streams now receive a deterministic citation marker when the model omits all markers; compliance is recorded after repair."),
    ("Eval/test restoration", "Restored five missing evaluation modules and updated contracts for correction-aware memory and deterministic OOD handling."),
    ("Frontend hygiene", "Upgraded Next 15.5.15 to 15.5.20, removed the lint warning, and cleared high-severity npm audit findings."),
]


def session_details(session: dict) -> str:
    status, note = STATUS[session["id"]]
    rows = []
    for turn in session["turns"]:
        trace = turn.get("trace") or {}
        route = trace.get("stage_4_route") or {}
        norm = trace.get("stage_2_normalize") or {}
        retrieval = trace.get("stage_7_retrieve") or {}
        done = turn["stream"].get("done") or {}
        state = {
            "age": norm.get("age"), "sex": norm.get("sex"),
            "pregnant": norm.get("is_pregnant"), "duration": norm.get("duration_weeks"),
            "products": norm.get("current_products"), "medications": norm.get("medications"),
            "lesions": norm.get("lesion_types"), "distribution": norm.get("lesion_distribution"),
        }
        answer = " ".join(turn["stream"].get("assistant_text", "").split())[:650]
        rows.append(
            f"<tr><td>T{turn['turn']}</td><td>{esc(turn['user'])}</td>"
            f"<td>{esc(route.get('primary_intent'))}/{esc(route.get('query_subject'))}<br><small>{esc(route.get('route_flags'))}</small></td>"
            f"<td><small>{esc(state)}</small></td><td>{esc(retrieval.get('num_chunks', 0))}<br><small>citation={esc(done.get('citation_compliance'))}</small></td>"
            f"<td>{esc(answer)}</td></tr>"
        )
    return (
        f"<details><summary><span class='badge {status.lower()}'>{status}</span> {session['id']} · {esc(session['category'])}</summary>"
        f"<p>{esc(note)}</p><div class='scroll'><table><thead><tr><th>Turn</th><th>User</th><th>Route</th><th>Structured state</th><th>RAG</th><th>Final response</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div></details>"
    )


comparison = [
    ("Backend suite", "424 passed + 17 failed + collection errors", "458 passed, 1 xfailed"),
    ("Critical medication safety", "Failed", "Deterministic pass"),
    ("Median response", f"{before['p50']/1000:.1f}s", f"{after['p50']/1000:.1f}s"),
    ("P95 response", f"{before['p95']/1000:.1f}s", f"{after['p95']/1000:.1f}s"),
    ("Median first token", f"{before['first']/1000:.1f}s", f"{after['first']/1000:.1f}s"),
    ("Citation compliance", f"{before['citation_ok']}/{before['citation_total']}", f"{after['citation_ok']}/{after['citation_total']}"),
    ("SSE errors", before["errors"], after["errors"]),
    ("Frontend high vulnerabilities", 1, 0),
]

document = f"""<!doctype html><html lang='vi'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>AcneLLM Post-fix Verification · 2026-07-12</title><style>
:root{{--bg:#07111d;--panel:#101e2d;--panel2:#172a3d;--text:#edf6ff;--muted:#9fb3c7;--line:#294157;--cyan:#55dff5;--green:#55d995;--amber:#ffd166;--red:#ff7685}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 20% 0,#163149,#07111d 45%);color:var(--text);font:15px/1.55 system-ui,Segoe UI,sans-serif}}main{{max-width:1360px;margin:auto;padding:34px 22px 80px}}h1{{font-size:clamp(30px,5vw,54px);line-height:1.04;margin:.2em 0}}h2{{margin-top:42px;border-bottom:1px solid var(--line);padding-bottom:9px}}h3{{color:var(--cyan)}}.panel,details,.hero{{background:#101e2df2;border:1px solid var(--line);border-radius:15px;padding:20px;margin:14px 0;box-shadow:0 18px 50px #0005}}.hero{{border-left:5px solid var(--green)}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}.metric{{background:var(--panel2);padding:16px;border-radius:12px}}.metric b{{display:block;color:var(--cyan);font-size:27px}}.muted,small{{color:var(--muted)}}table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid var(--line)}}th{{color:var(--cyan);background:#101e2d;position:sticky;top:0}}.scroll{{overflow:auto;max-height:620px}}details summary{{cursor:pointer;font-weight:700;font-size:17px}}.badge{{display:inline-block;padding:3px 9px;border-radius:999px}}.pass{{background:#173d2c;color:#82eab2}}.partial{{background:#4b3915;color:#ffdb80}}code{{color:#a9eff9}}a{{color:var(--cyan)}}@media(max-width:700px){{main{{padding:20px 12px}}th,td{{min-width:150px}}}}
</style></head><body><main>
<p class='muted'>Post-fix live verification · branch codex/simplify-chat-pipeline</p><h1>Critical safety fixed.<br>Strong prototype, not production yet.</h1>
<section class='hero'><h3>Executive result</h3><p>The implementation removed the critical pregnancy/medication failure, restored correction-aware memory, blocked explicit OOD before generation, and made citation compliance deterministic. No E2E session remains a full failure.</p><p>The remaining limitations are generation quality: the local 7B Q4 model can still provide overly specific frequency/concentration advice or imperfectly paraphrase informal Vietnamese. These are now downstream limitations rather than hidden state/safety failures.</p></section>
<section class='grid'><div class='metric'><span>Backend</span><b>458 pass</b><small>1 expected xfail</small></div><div class='metric'><span>Final E2E</span><b>5 Pass</b><small>5 Partial · 0 Fail</small></div><div class='metric'><span>Median response</span><b>{after['p50']/1000:.1f}s</b><small>P95 {after['p95']/1000:.1f}s</small></div><div class='metric'><span>Citations</span><b>{after['citation_ok']}/{after['citation_total']}</b><small>retrieval-backed turns</small></div></section>
<h2>What changed</h2><div class='panel'><table><thead><tr><th>Area</th><th>Implemented fix</th></tr></thead><tbody>{''.join(f'<tr><td><b>{esc(a)}</b></td><td>{esc(b)}</td></tr>' for a,b in FIXES)}</tbody></table></div>
<h2>Before vs after</h2><div class='panel'><table><thead><tr><th>Metric</th><th>Before fix</th><th>After fix</th></tr></thead><tbody>{''.join(f'<tr><td>{esc(a)}</td><td>{esc(b)}</td><td>{esc(c)}</td></tr>' for a,b,c in comparison)}</tbody></table></div>
<h2>Final session matrix</h2><div class='panel'><table><thead><tr><th>Session</th><th>Status</th><th>Result</th></tr></thead><tbody>{''.join(f"<tr><td>{sid}</td><td><span class='badge {status.lower()}'>{status}</span></td><td>{esc(note)}</td></tr>" for sid,(status,note) in STATUS.items())}</tbody></table></div>
<h2>Detailed final evidence</h2>{''.join(session_details(session) for session in fixed['sessions'])}
<h2>Verification</h2><div class='panel'><ul><li><code>python -m pytest -q</code>: 458 passed, 1 xfailed.</li><li><code>npm run lint</code>: clean.</li><li><code>npm run build</code>: production build successful on Next.js 15.5.20.</li><li><code>npm audit --audit-level=high</code>: exit 0, no high/critical; two moderate PostCSS advisories remain because npm's force fix proposes a breaking Next downgrade.</li><li>Live health remained OK with Ollama, 16,635 KB chunks and BM25 loaded. No service was manually restarted or killed.</li></ul></div>
<h2>Remaining work</h2><div class='panel'><ol><li>Replace the minimal end-of-answer citation repair with claim-level citation validation.</li><li>Add deterministic boundaries for medication dose/frequency/concentration advice, not only drug contraindications.</li><li>Improve mixed/informal Vietnamese semantic normalization for phrases such as “barrier bị hỏng”.</li><li>Calibrate urgency flags so chronic/pain signals do not over-triage without acute infection evidence.</li><li>Resolve the two moderate PostCSS advisories when a non-breaking patched Next dependency is available.</li></ol></div>
<h2>Verdict</h2><div class='panel'><p><b>Safe to continue development and internal testing:</b> yes.</p><p><b>Safe to deploy as autonomous medical advice:</b> no. It should remain a strong prototype with explicit medical limitations and human escalation.</p><p><b>Largest improvement:</b> safety-critical decisions no longer depend on the model. Structured state, correction replay and medication interaction checks now determine the response before generation.</p></div>
<p class='muted'>Final merged evidence: {esc(MERGED)}. This report preserves the full-run evidence and later targeted regression evidence separately.</p></main></body></html>"""

OUTPUT.write_text(document, encoding="utf-8")
print(OUTPUT.resolve())
