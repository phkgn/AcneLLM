"""Generate the standalone final comprehensive AcneLLM audit report."""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
from statistics import median


HERE = Path(__file__).resolve().parent
SUMMARY = json.loads((HERE / "final_summary.json").read_text(encoding="utf-8"))
LIVE = json.loads((HERE / "live_final_audit_evidence.json").read_text(encoding="utf-8"))
RETRY = json.loads((HERE / "targeted_clean_retry.json").read_text(encoding="utf-8"))
OUT = HERE / "acnellm_final_comprehensive_audit_20260713.html"


def h(value) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def cls(status: str) -> str:
    return status.lower().replace(" ", "-")


def badge(status: str) -> str:
    return f'<span class="badge {cls(status)}">{h(status)}</span>'


def trunc(text: str, limit: int = 1800) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + " … [truncated; full text in JSON evidence]"


def chunk_summary(turn: dict) -> str:
    chunks = (turn.get("trace") or {}).get("stage_7_retrieve", {}).get("chunks", [])
    return " · ".join(
        f"{chunk.get('source_type') or 'unknown'}:{chunk.get('source') or '?'}"
        for chunk in chunks
    ) or "none"


def detail_cards(data: dict, findings: dict, ids: list[str], prefix: str) -> str:
    by_id = {row["id"]: row for row in data["sessions"]}
    cards = []
    for sid in ids:
        session = by_id[sid]
        judgment = findings[sid]
        turns = []
        for turn in session["turns"]:
            stream = turn.get("stream") or {}
            trace = turn.get("trace") or {}
            prompt = trace.get("stage_8_prompt", {}).get("user_message", "")
            prompt_note = ""
            if prompt:
                prompt_note = (
                    f'<details class="nested"><summary>Prompt snapshot · {len(prompt)} chars</summary>'
                    f'<pre>{h(trunc(prompt, 1200))}</pre></details>'
                )
            turns.append(
                f"""
                <div class="turn">
                  <div class="turn-head"><b>{h(sid)}/T{turn['turn']}</b><span>{stream.get('wall_time_ms', 0)/1000:.1f}s · first {((stream.get('first_token_ms') or 0)/1000):.1f}s · {stream.get('event_counts', {}).get('token', 0)} token events</span></div>
                  <p><strong>User</strong> {h(turn.get('user'))}</p>
                  <p><strong>Final chunks</strong> {h(chunk_summary(turn))}</p>
                  <p><strong>Answer</strong> {h(trunc(stream.get('assistant_text', '')))}</p>
                  {prompt_note}
                </div>
                """
            )
        cards.append(
            f"""
            <details id="{prefix}-{sid.lower()}" class="session-card" {'open' if judgment['status']=='Fail' else ''}>
              <summary><span>{h(sid)} · {h(session['category'])}</span>{badge(judgment['status'])}</summary>
              <div class="detail"><div class="finding">{h(judgment['finding'])}</div>{''.join(turns)}</div>
            </details>
            """
        )
    return "".join(cards)


def status_rows(findings: dict, data: dict, prefix: str) -> str:
    by_id = {row["id"]: row for row in data["sessions"]}
    rows = []
    for sid, item in findings.items():
        session = by_id[sid]
        errors = sum(
            1 for turn in session["turns"]
            if turn.get("stream_error") or (turn.get("stream", {}).get("event_counts", {}).get("error") or 0)
        )
        chunk_count = sum(
            len((turn.get("trace") or {}).get("stage_7_retrieve", {}).get("chunks", []))
            for turn in session["turns"]
        )
        rows.append(
            f"<tr data-status='{cls(item['status'])}'><td><a href='#{prefix}-{sid.lower()}'>{h(sid)}</a></td>"
            f"<td>{h(session['category'])}</td><td>{len(session['turns'])}</td><td>{errors}</td>"
            f"<td>{chunk_count}</td><td>{h(item['finding'])}</td><td>{badge(item['status'])}</td></tr>"
        )
    return "".join(rows)


fix_rows = "".join(
    f"<tr data-status='{cls(item['status'])}'><td>{item['id']}</td><td><b>{h(item['issue'])}</b></td>"
    f"<td>{badge(item['status'])}</td><td>{h(item['evidence'])}</td></tr>"
    for item in SUMMARY["fixes"]
)

session_rows = status_rows(SUMMARY["session_findings"], LIVE, "std")
jitter_rows = status_rows(SUMMARY["jitter_findings"], LIVE, "jit")
retry_rows = status_rows(SUMMARY["retry_findings"], RETRY, "retry")

normalizer_rows = "".join(
    f"<tr><td>{h(field)}</td><td>{values['before']:.3f}</td><td>{values['after']:.3f}</td>"
    f"<td class='delta {'up' if values['delta']>0 else 'down' if values['delta']<0 else ''}'>{values['delta']:+.3f}</td></tr>"
    for field, values in SUMMARY["normalizer_delta"].items()
)

score_rows = "".join(
    f"<tr><td>{h(row['layer'])}</td><td>{row['before']:.1f}</td><td>{row['after']:.1f}</td>"
    f"<td class='delta {'up' if row['after']>row['before'] else 'down' if row['after']<row['before'] else ''}'>{row['after']-row['before']:+.1f}</td>"
    f"<td><div class='bar'><span style='width:{row['after']*10:.0f}%'></span></div></td><td>{h(row['reason'])}</td></tr>"
    for row in SUMMARY["scores"]
)

new_rows = "".join(
    f"<tr data-severity='{item['severity'].lower()}'><td>{badge(item['severity'])}</td>"
    f"<td><b>{h(item['id'])} · {h(item['title'])}</b></td><td>{h(item['evidence'])}</td></tr>"
    for item in SUMMARY["new_findings"]
)

raw_rows = "".join(
    f"<tr><td>RAW {index}</td><td>{row['wall_time_ms']/1000:.1f}s</td><td>{h(row['prompt'])}</td>"
    f"<td>{h(trunc(row.get('assistant_text',''), 650))}</td></tr>"
    for index, row in enumerate(LIVE["raw_model_baseline"], 1)
)

retrieval_rows = []
for name, after_chunks in SUMMARY["retrieval_after"].items():
    before_chunks = SUMMARY["retrieval_before"][name]
    before_top = before_chunks[0]
    after_top = after_chunks[0]
    authorities = [row for row in after_chunks if row["source_type"] in {"aad_guideline", "nice_guideline"}]
    authority_note = (
        f"first authority rank {authorities[0]['rank']} · {authorities[0]['score']:.3f}"
        if authorities else "no AAD/NICE in top 10"
    )
    retrieval_rows.append(
        f"<tr><td>{h(name)}</td><td>{before_top['score']:.3f} · {h(before_top['source_type'])}</td>"
        f"<td>{after_top['score']:.3f} · {h(after_top['source_type'])}</td><td>{h(authority_note)}</td></tr>"
    )

std = SUMMARY["current_standard"]
prev = SUMMARY["immediate_prior_standard"]
retry_m = SUMMARY["targeted_retry"]
raw_median = median(SUMMARY["raw_model_baseline"]["latencies_s"])

CSS = r"""
:root{--bg:#090d13;--panel:#111823;--panel2:#151e2a;--line:#273243;--text:#e8eef7;--muted:#9caabd;--cyan:#42d3ff;--green:#44d18b;--amber:#ffbd59;--red:#ff6577;--violet:#a88bff;--blue:#5f8cff}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(circle at 88% -10%,#162339 0,transparent 34%),var(--bg);color:var(--text);font:15px/1.58 Inter,Segoe UI,Arial,sans-serif}.layout{display:grid;grid-template-columns:250px 1fr;min-height:100vh}aside{position:sticky;top:0;height:100vh;padding:24px 18px;border-right:1px solid var(--line);background:rgba(9,13,19,.92);overflow:auto}.brand{font-weight:800;font-size:18px;color:#fff;margin-bottom:4px}.brand small{display:block;color:var(--cyan);font-size:11px;letter-spacing:.14em;text-transform:uppercase;margin-top:5px}nav{margin-top:20px}nav a{display:block;color:var(--muted);text-decoration:none;padding:7px 9px;border-radius:7px;font-size:13px}nav a:hover{color:white;background:#172131}main{max-width:1460px;padding:42px 42px 90px}.eyebrow{text-transform:uppercase;letter-spacing:.15em;color:var(--cyan);font-size:12px;font-weight:800}.hero{font-size:clamp(36px,5vw,68px);line-height:1.01;margin:12px 0 18px;max-width:1000px}.lede{font-size:19px;color:#c3cedd;max-width:1050px}.chips{display:flex;flex-wrap:wrap;gap:8px;margin:22px 0}.chip{border:1px solid var(--line);background:#111a26;color:#cbd7e6;border-radius:999px;padding:6px 10px;font-size:12px}.stats{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:24px 0}.stat{background:linear-gradient(145deg,var(--panel),#0d141e);border:1px solid var(--line);border-radius:12px;padding:16px}.stat b{display:block;font-size:26px;color:#fff}.stat small{color:var(--muted)}section{margin-top:64px;scroll-margin-top:20px}h2{font-size:29px;margin:0 0 8px}h3{font-size:18px;margin-top:26px}.intro{color:var(--muted);max-width:1040px}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.two{display:grid;grid-template-columns:1fr 1fr;gap:14px}.card,.callout{border:1px solid var(--line);background:var(--panel);border-radius:12px;padding:18px}.callout{margin:16px 0}.callout.good{border-left:4px solid var(--green)}.callout.warn{border-left:4px solid var(--amber)}.callout.bad{border-left:4px solid var(--red)}.flow{display:grid;grid-template-columns:repeat(6,1fr);gap:9px;margin:22px 0}.node{position:relative;background:var(--panel2);border:1px solid var(--line);border-radius:11px;padding:15px;text-align:center}.node b{display:block;color:#fff}.node small{color:var(--muted)}.node:not(:last-child):after{content:'→';position:absolute;right:-10px;top:34%;color:var(--cyan);z-index:2}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:12px;background:var(--panel)}table{border-collapse:collapse;width:100%;min-width:760px}th,td{padding:12px 13px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}th{color:#aebbd0;background:#151f2c;font-size:12px;text-transform:uppercase;letter-spacing:.06em}tr:last-child td{border-bottom:0}a{color:var(--cyan)}code,pre{font-family:Cascadia Code,Consolas,monospace}code{color:#c4b7ff}pre{white-space:pre-wrap;background:#0a1018;border:1px solid var(--line);border-radius:8px;padding:12px;color:#cbd5e3;font-size:12px}.badge{display:inline-block;border-radius:999px;padding:3px 8px;font-size:11px;font-weight:800;white-space:nowrap}.fixed-core,.pass{color:#75e6ad;background:#123728}.partial,.medium{color:#ffd18a;background:#3b2d15}.not-fixed,.fail,.critical{color:#ff91a0;background:#3c1820}.high,.new-blocker{color:#ffba77;background:#3a2414}.filters{display:flex;gap:7px;flex-wrap:wrap;margin:14px 0}.filters button{border:1px solid var(--line);background:#111924;color:var(--muted);padding:6px 10px;border-radius:999px;cursor:pointer}.filters button.active{border-color:var(--cyan);color:white}.session-card{border:1px solid var(--line);background:var(--panel);border-radius:11px;margin:10px 0;overflow:hidden}.session-card>summary{cursor:pointer;display:flex;justify-content:space-between;gap:12px;padding:14px 16px;font-weight:700}.detail{padding:0 16px 16px}.finding{border-left:3px solid var(--violet);padding:9px 12px;background:#111a27;color:#cbd6e5}.turn{margin-top:12px;border:1px solid var(--line);border-radius:9px;padding:12px;background:#0d141d}.turn p{margin:8px 0}.turn-head{display:flex;justify-content:space-between;gap:10px;color:var(--muted)}.turn-head b{color:var(--cyan)}.nested{margin-top:10px}.nested summary{cursor:pointer;color:var(--muted)}.delta{font-weight:800}.delta.up{color:var(--green)}.delta.down{color:var(--red)}.bar{width:130px;height:8px;background:#273140;border-radius:99px;overflow:hidden}.bar span{display:block;height:100%;background:linear-gradient(90deg,var(--violet),var(--cyan))}.verdict{display:grid;grid-template-columns:160px 1fr;border:1px solid #6b4b2b;background:#241b12;border-radius:14px;overflow:hidden}.grade{display:grid;place-items:center;font-size:48px;font-weight:900;color:var(--amber);border-right:1px solid #6b4b2b}.verdict-body{padding:22px}.compact{margin:8px 0;padding-left:20px;color:#c7d1df}.compact li{margin:6px 0}.timeline{border-left:2px solid var(--line);margin:18px 0 18px 9px}.event{position:relative;padding:0 0 18px 21px}.event:before{content:'';position:absolute;left:-7px;top:4px;width:12px;height:12px;border-radius:50%;background:var(--cyan)}.event b{display:block}.event span{color:var(--muted)}footer{margin-top:70px;color:var(--muted);font-size:12px}
@media(max-width:1100px){.layout{display:block}aside{position:relative;height:auto;border-right:0;border-bottom:1px solid var(--line)}nav{display:flex;flex-wrap:wrap}main{padding:30px 22px 70px}.stats{grid-template-columns:repeat(3,1fr)}.grid{grid-template-columns:repeat(2,1fr)}.flow{grid-template-columns:repeat(3,1fr)}.node:nth-child(3):after{display:none}}
@media(max-width:680px){main{padding:24px 14px 60px}.stats,.grid,.two{grid-template-columns:1fr}.flow{grid-template-columns:1fr}.node:not(:last-child):after{content:'↓';left:48%;right:auto;top:auto;bottom:-19px}.verdict{grid-template-columns:1fr}.grade{border-right:0;border-bottom:1px solid #6b4b2b}}
"""

HTML = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AcneLLM Final Comprehensive Audit · 2026-07-13</title><style>{CSS}</style></head><body><div class="layout">
<aside><div class="brand">AcneLLM<small>Final comprehensive audit</small></div><nav>
<a href="#summary">Executive</a><a href="#method">Method</a><a href="#architecture">Architecture</a><a href="#delta">Before / After</a><a href="#gates">Regression gates</a><a href="#fixes">Fix matrix</a><a href="#sessions">S01–S12</a><a href="#jitter">Seeded jitter</a><a href="#retry">Clean retry</a><a href="#raw">Raw vs pipeline</a><a href="#normalizer">Normalizer</a><a href="#retrieval">Retrieval</a><a href="#persistence">SQLite</a><a href="#failures">New findings</a><a href="#scores">Scores</a><a href="#priority">Priority</a><a href="#verdict">Verdict</a><a href="#evidence">Evidence</a>
</nav></aside><main>
<header id="summary"><div class="eyebrow">Current working tree · same protocol · evidence-first</div><h1 class="hero">The runtime recovered.<br>The safety contract did not.</h1><p class="lede">Final replay on <b>{h(SUMMARY['snapshot']['head'][:8])}</b> plus staged changes: <b>3/12 reported issues fixed at core, 1/12 partial, 8/12 not fixed</b>. Clean transport is materially better, but critical unsafe self-procedure output, zero Vietnamese guideline reachability, prompt/context leakage and absent cancellation keep the repo below production readiness.</p>
<div class="chips"><span class="chip">{h(SUMMARY['snapshot']['branch'])}</span><span class="chip">jitter seed {SUMMARY['snapshot']['jitter_seed']}</span><span class="chip">12 standard · 31 turns</span><span class="chip">4 jitter · 8 turns</span><span class="chip">6 retry · 12 turns</span><span class="chip">5 raw prompts</span><span class="chip">baseline source not edited</span></div>
<div class="stats"><div class="stat"><b>3/12</b><small>fixed core</small></div><div class="stat"><b>3 / 5 / 4</b><small>Pass / Partial / Fail</small></div><div class="stat"><b>0</b><small>SSE errors in clean full+retry</small></div><div class="stat"><b>1,201</b><small>max output token events</small></div><div class="stat"><b>0</b><small>AAD/NICE final chunks</small></div><div class="stat"><b>5.4/10</b><small>engineering score</small></div></div>
<div class="verdict"><div class="grade">5.4</div><div class="verdict-body"><b>Strong prototype · not close to production</b><p>Build and persistence are usable. Safety, grounding, output control and cancellation are still invariants enforced probabilistically—or not enforced at all.</p></div></div></header>

<section id="method"><h2>Method & Integrity</h2><p class="intro">Same production path and same prompts as the prior audit, with a new deterministic jitter seed. No source/config/model parameter was edited by the audit.</p><div class="timeline"><div class="event"><b>Snapshot</b><span>HEAD {h(SUMMARY['snapshot']['head'])}; working tree = HEAD + staged user changes; installed Ollama SYSTEM independently verified.</span></div><div class="event"><b>Regression</b><span>Full backend suite, frontend lint/build, normalizer n=1000, SQLite unit tests and disposable migration fixture.</span></div><div class="event"><b>Live path</b><span>Trace + real SSE for S01–S12, J01–J04, R01–R06; raw model baseline via Ollama.</span></div><div class="event"><b>Resume transparency</b><span>Initial process had persisted 9 complete turns before its shell was interrupted; the final evidence resumes at S03/T3 with the same session ID. No completed turn was rerun or omitted.</span></div><div class="event"><b>Frontend recovery</b><span>Running production build beside the pre-existing dev server replaced shared .next chunks and temporarily caused a missing-module 500. Restarting the exact npm run dev process restored HTTP 200; source build remained green.</span></div><div class="event"><b>Retrieval</b><span>Same six paired Vietnamese/English dense/sparse/hybrid probes.</span></div></div><div class="callout warn"><b>Interpretation:</b> 0 current SSE errors means this clean worker was stable. It does not close F12: the API still never observes client disconnect, and output generation remains unbounded for knowledge intent.</div></section>

<section id="architecture"><h2>Current Pipeline</h2><p class="intro">The major refactor makes Modelfile SYSTEM the sole behavioral prompt and moves sessions from JSONL to SQLite.</p><div class="flow"><div class="node"><b>Preprocess</b><small>clean · normalize · route</small></div><div class="node"><b>Session</b><small>SQLite fold · facts</small></div><div class="node"><b>Query</b><small>raw-first · aliases</small></div><div class="node"><b>RAG</b><small>hybrid · rerank .58</small></div><div class="node"><b>Ollama</b><small>Modelfile SYSTEM only</small></div><div class="node"><b>Post</b><small>marker repair · suffix</small></div></div><div class="two"><div class="card"><h3>What genuinely improved</h3><ul class="compact"><li>Installed model contains the staged safety/grounding SYSTEM.</li><li>Runtime-system drop is now an intentional single-source contract.</li><li>SQLite store passes 8 focused tests and sustained multi-turn live replay.</li><li>Clean transport recovered from 7 SSE errors + 1 timeout to 0.</li></ul></div><div class="card"><h3>What regressed or stayed fragile</h3><ul class="compact"><li>Endpoint-local prompt constraints were removed; model leaks prompt/context.</li><li>Safety suffix remains lexical and misses paraphrases.</li><li>Guideline floor/top-k, citation gate and duplicate context unchanged.</li><li>Model behavior now depends on external tag rebuild without lineage.</li></ul></div></div></section>

<section id="delta"><h2>Immediate Before / After</h2><div class="table-wrap"><table><thead><tr><th>Metric</th><th>Prior report</th><th>Final rerun</th><th>Judgment</th></tr></thead><tbody>
<tr><td>Backend suite</td><td>455 pass · 3 fail · 1 xfail</td><td>455 pass · 3 fail · 1 xfail</td><td>Same planner contract drift.</td></tr>
<tr><td>Standard SSE/client errors</td><td>{prev['event_error_count']} + {prev['client_error_count']}</td><td><b>{std['event_error_count']} + {std['client_error_count']}</b></td><td>Strong clean-run recovery.</td></tr>
<tr><td>Successful model turns</td><td>{prev['successful_model_turns']}</td><td>{std['successful_model_turns']}</td><td>All non-deterministic standard turns returned.</td></tr>
<tr><td>Median / P95 / max latency</td><td>{prev['model_latency_median_s']:.1f}s / {prev['model_latency_p95_s']:.1f}s / n/a</td><td>{std['model_latency_median_s']:.1f}s / <b>{std['model_latency_p95_s']:.1f}s</b> / <b>{std['model_latency_max_s']:.1f}s</b></td><td>Median improves; long-tail worsens from runaway output.</td></tr>
<tr><td>Output token events</td><td>not highlighted</td><td>median {std['output_tokens_median']:.0f} · P95 {std['output_tokens_p95']:.0f} · max {std['output_tokens_max']}</td><td>S03 hit the 1,200-token ceiling.</td></tr>
<tr><td>Session quality</td><td>3 Pass / 5 Partial / 4 Fail</td><td>3 Pass / 5 Partial / 4 Fail</td><td>Transport improved; semantic quality did not.</td></tr>
<tr><td>AAD/NICE final chunks</td><td>0</td><td><b>0</b></td><td>No authority-retrieval improvement.</td></tr>
</tbody></table></div></section>

<section id="gates"><h2>Regression & Build Gates</h2><div class="grid"><div class="card"><h3>Backend</h3><p><b>455 passed · 3 failed · 1 xfailed</b><br>38.50s. Same three planner expectations.</p></div><div class="card"><h3>Frontend</h3><p><b>Lint pass · build pass</b><br>Next 15.5.20 · 4 pages · 112 kB first load.</p></div><div class="card"><h3>SQLite</h3><p><b>8 focused tests pass</b><br>Live multi-turn persistence also works.</p></div><div class="card"><h3>Normalizer</h3><p><b>1,000 samples</b><br>Every reported metric unchanged from the prior rerun.</p></div><div class="card"><h3>Installed model</h3><p><b>Contract verified</b><br>Repo Modelfile markers exist in installed tag.</p></div><div class="card"><h3>Raw baseline</h3><p><b>5/5 completed</b><br>Median {raw_median:.1f}s · 0 API errors.</p></div></div></section>

<section id="fixes"><h2>Reported-Issue Verification Matrix</h2><p class="intro">“Fixed core” means the originally reported defect is removed at its core path; residual limitations are stated explicitly.</p><div class="filters" data-target="fix-table"><button class="active" data-filter="all">All</button><button data-filter="fixed-core">Fixed core</button><button data-filter="partial">Partial</button><button data-filter="not-fixed">Not fixed</button></div><div class="table-wrap"><table id="fix-table"><thead><tr><th>ID</th><th>Issue</th><th>Status</th><th>Current evidence</th></tr></thead><tbody>{fix_rows}</tbody></table></div></section>

<section id="sessions"><h2>Standard S01–S12</h2><p class="intro">Same prompts as the prior audit. All 31 turns are present in the final JSON.</p><div class="filters" data-target="session-table"><button class="active" data-filter="all">All</button><button data-filter="pass">Pass</button><button data-filter="partial">Partial</button><button data-filter="fail">Fail</button></div><div class="table-wrap"><table id="session-table"><thead><tr><th>ID</th><th>Category</th><th>Turns</th><th>Errors</th><th>Chunks</th><th>Finding</th><th>Status</th></tr></thead><tbody>{session_rows}</tbody></table></div><h3>Turn evidence</h3>{detail_cards(LIVE, SUMMARY['session_findings'], list(SUMMARY['session_findings']), 'std')}</section>

<section id="jitter"><h2>Seeded Jitter · {SUMMARY['snapshot']['jitter_seed']}</h2><div class="table-wrap"><table id="jitter-table"><thead><tr><th>ID</th><th>Category</th><th>Turns</th><th>Errors</th><th>Chunks</th><th>Finding</th><th>Status</th></tr></thead><tbody>{jitter_rows}</tbody></table></div>{detail_cards(LIVE, SUMMARY['jitter_findings'], list(SUMMARY['jitter_findings']), 'jit')}</section>

<section id="retry"><h2>Exact Clean Retry R01–R06</h2><p class="intro">Independent sessions using the exact cases from the immediately prior report. 12/12 turns completed with 0 errors.</p><div class="table-wrap"><table id="retry-table"><thead><tr><th>ID</th><th>Category</th><th>Turns</th><th>Errors</th><th>Chunks</th><th>Finding</th><th>Status</th></tr></thead><tbody>{retry_rows}</tbody></table></div>{detail_cards(RETRY, SUMMARY['retry_findings'], list(SUMMARY['retry_findings']), 'retry')}</section>

<section id="raw"><h2>Raw Model vs Full Pipeline</h2><p class="intro">Raw model is not a replacement for RAG, but it remains a semantic control: preprocessing/history/retrieval should not make the result worse.</p><div class="table-wrap"><table><thead><tr><th>ID</th><th>Latency</th><th>Prompt</th><th>Raw response</th></tr></thead><tbody>{raw_rows}</tbody></table></div><div class="two"><div class="callout good"><b>Raw often wins on focus:</b> all five are concise; it avoids S03 prompt leakage and S08's request to add BHA while irritated.</div><div class="callout warn"><b>Raw still needs grounding:</b> it invents exact spacing/timing and cannot cite the KB. The correct direction remains raw-first with pipeline data as bounded hints.</div></div></section>

<section id="normalizer"><h2>Normalizer Delta · n=1,000</h2><div class="table-wrap"><table><thead><tr><th>Field</th><th>Prior rerun</th><th>Final</th><th>Delta</th></tr></thead><tbody>{normalizer_rows}</tbody></table></div><div class="callout warn"><b>No final-round gain:</b> skin_type remains 0.790, red_flags F1 0.217, medications F1 0.432 and sex accuracy 0.345. This is stability, not additional improvement.</div></section>

<section id="retrieval"><h2>Paired VI/EN Retrieval Recheck</h2><div class="table-wrap"><table><thead><tr><th>Probe</th><th>Prior top</th><th>Final top</th><th>Final authority reach</th></tr></thead><tbody>{''.join(retrieval_rows)}</tbody></table></div><div class="two"><div class="callout bad"><b>Moderate-acne VI:</b> NICE ranks 1–3 at ~0.507, below the chat keep floor 0.58, so final context is empty.</div><div class="callout bad"><b>Pregnancy VI:</b> AAD is absent from top 10 in this final probe while English returns AAD/NICE around 0.656–0.665.</div></div></section>

<section id="persistence"><h2>SQLite Session Migration</h2><div class="grid"><div class="card"><h3>Runtime store</h3><p><b>Pass</b>: 8 focused tests; S01–S12 multi-turn history persisted across the live replay/resume.</p></div><div class="card"><h3>Migration fidelity</h3><p><b>Pass</b>: disposable fixture preserves timestamps, context, asked fields, score, turn metadata and chunks.</p></div><div class="card"><h3>Delete safety</h3><p><b>Fail</b>: one malformed file is reported skipped, then <code>--delete</code> deletes it anyway.</p></div></div><div class="callout warn"><b>Repo hygiene:</b> <code>sessions.db</code> is ignored, but <code>sessions.db-wal</code> and <code>sessions.db-shm</code> are not; both are currently staged/modified runtime artifacts.</div></section>

<section id="failures"><h2>New / Newly-Proven Findings</h2><div class="filters" data-target="new-table"><button class="active" data-filter="all">All</button><button data-filter="critical">Critical</button><button data-filter="high">High</button><button data-filter="medium">Medium</button></div><div class="table-wrap"><table id="new-table"><thead><tr><th>Severity</th><th>Finding</th><th>Evidence</th></tr></thead><tbody>{new_rows}</tbody></table></div><div class="callout bad"><b>Most important contradiction:</b> the Modelfile says “không hướng dẫn tự nặn, tự chích”, yet R05/T2 still gives a needle procedure. Prompt policy is not a safety enforcement layer.</div></section>

<section id="scores"><h2>Layer-by-Layer Score</h2><p class="intro">Engineering judgment 0–10, weighted toward user harm, grounding and reproducibility rather than build success alone.</p><div class="table-wrap"><table><thead><tr><th>Layer</th><th>Prior</th><th>Final</th><th>Δ</th><th>Visual</th><th>Reason</th></tr></thead><tbody>{score_rows}</tbody></table></div></section>

<section id="priority"><h2>Priority Order</h2><div class="grid"><div class="card"><h3>P0 · Deterministic safety rewrite</h3><p>Reject/remove actionable self-procedure instructions before streaming or buffer until validated. Expand semantic coverage beyond exact lexical phrases.</p></div><div class="card"><h3>P0 · Bound and cancel generation</h3><p>Pass disconnect state into runtime, close Ollama stream on disconnect, cap every intent—including knowledge—and add concurrency/queue limits.</p></div><div class="card"><h3>P0 · Fix VI authority selection</h3><p>Calibrate reranker/floor and reserve an AAD/NICE slot; use the same paired benchmark as the acceptance gate.</p></div><div class="card"><h3>P1 · Restore local prompt contracts</h3><p>Keep Modelfile as global policy but retain endpoint-local rules against context copying, unsupported source names and repeated answers.</p></div><div class="card"><h3>P1 · Claim-level citation</h3><p>Validate marker range and claim support; never declare compliance from any [N] regex or append blind [1].</p></div><div class="card"><h3>P1 · Harden migration/deploy</h3><p>Quarantine skipped JSONL, ignore WAL/SHM, align planner tests and add model/KB manifests plus startup verification.</p></div></div></section>

<section id="verdict"><h2>Final Verdict</h2><div class="table-wrap"><table><tbody><tr><th>Repo đã fix các lỗi report chưa?</th><td><b>Chưa.</b> 3 fixed core, 1 partial, 8 not fixed.</td></tr><tr><th>Điểm tiến bộ rõ nhất?</th><td>Clean transport, installed single-source SYSTEM alignment, SQLite persistence, oil/pain and negated-query fixes.</td></tr><tr><th>Blocker nguy hiểm nhất?</th><td>Exact sterile-needle prompt still gets actionable puncture instructions; safety invariant fails nondeterministically.</td></tr><tr><th>RAG guideline tốt hơn chưa?</th><td><b>Không.</b> 0 AAD/NICE final chunks in standard and retry; VI/EN calibration gap persists.</td></tr><tr><th>Prompt refactor tốt hơn chưa?</th><td>Architecture cleaner, behavior worse in key turns: S03 prompt leak/runaway output and unsupported guideline attribution.</td></tr><tr><th>Model là bottleneck chính?</th><td><b>Không.</b> Raw model is often more focused. Main bottlenecks are prompt contract, post-safety, final retrieval selection, citation assurance and lifecycle control.</td></tr><tr><th>Maturity?</th><td><b>Strong prototype, not close to production.</b></td></tr></tbody></table></div></section>

<section id="evidence"><h2>Evidence Index</h2><ul class="compact"><li><a href="final_summary.json">final_summary.json</a> · computed metrics + adjudication.</li><li><a href="live_final_audit_evidence.json">live_final_audit_evidence.json</a> · 16 sessions / 39 turns + 5 raw prompts.</li><li><a href="targeted_clean_retry.json">targeted_clean_retry.json</a> · 6 sessions / 12 turns.</li><li><a href="retrieval_recheck.json">retrieval_recheck.json</a> · six paired VI/EN probes.</li><li><a href="normalizer_evidence/report.json">normalizer_evidence/report.json</a> · n=1,000 metrics.</li><li><a href="source_snapshot.json">source_snapshot.json</a> · branch, HEAD, health, staged stat and installed model.</li><li><a href="session_migration_validation.json">session_migration_validation.json</a> · disposable migration result.</li><li><a href="frontend_recovery_stdout.log">frontend_recovery_stdout.log</a>, <a href="frontend_recovery_stderr.log">frontend_recovery_stderr.log</a> · exact dev-server recovery evidence.</li><li><a href="run_final_audit.py">run_final_audit.py</a>, <a href="resume_final_audit.py">resume_final_audit.py</a>, <a href="run_final_targeted_retry.py">run_final_targeted_retry.py</a>, <a href="run_final_retrieval.py">run_final_retrieval.py</a> · reproducible harnesses.</li></ul></section>
<footer>Generated from local source, tests, trace/SSE evidence and installed-model inspection on 2026-07-13. No external assets.</footer>
</main></div><script>document.querySelectorAll('.filters').forEach(g=>{{const t=document.getElementById(g.dataset.target);g.querySelectorAll('button').forEach(b=>b.addEventListener('click',()=>{{g.querySelectorAll('button').forEach(x=>x.classList.remove('active'));b.classList.add('active');const f=b.dataset.filter;t.querySelectorAll('tbody tr').forEach(r=>{{const v=r.dataset.status||r.dataset.severity;r.style.display=(f==='all'||v===f)?'':'none'}})}}))}});</script></body></html>"""

OUT.write_text(HTML, encoding="utf-8")
print(OUT)
print(f"bytes={OUT.stat().st_size}")
