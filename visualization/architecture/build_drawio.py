"""Build the source-verified multi-page diagrams.net architecture document.

The generated XML is intentionally uncompressed so it stays diffable and can
be opened directly in https://app.diagrams.net/ for manual refinement/export.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("AcneLLM_Architecture.drawio")

COLORS = {
    "blue": ("#DBEAFE", "#2563EB"),
    "indigo": ("#E0E7FF", "#4F46E5"),
    "purple": ("#F3E8FF", "#9333EA"),
    "orange": ("#FFEDD5", "#EA580C"),
    "green": ("#DCFCE7", "#16A34A"),
    "red": ("#FEE2E2", "#DC2626"),
    "cyan": ("#CFFAFE", "#0891B2"),
    "yellow": ("#FEF3C7", "#D97706"),
    "gray": ("#F8FAFC", "#64748B"),
    "dark": ("#0F172A", "#0F172A"),
}


def _style(kind: str, color: str = "blue", *, dashed: bool = False) -> str:
    fill, stroke = COLORS[color]
    common = (
        "html=1;whiteSpace=wrap;overflow=hidden;shadow=0;"
        "fontFamily=Helvetica;fontSize=14;fontColor=#0F172A;"
    )
    if kind == "lane":
        return (
            common
            + "swimlane;horizontal=1;startSize=38;rounded=1;arcSize=10;"
            + f"fillColor={fill};swimlaneFillColor=#FFFFFF;strokeColor={stroke};"
            + "fontStyle=1;fontSize=17;spacingLeft=12;"
            + ("dashed=1;dashPattern=8 4;" if dashed else "")
        )
    if kind == "decision":
        return (
            common
            + "rhombus;perimeter=rhombusPerimeter;"
            + f"fillColor={fill};strokeColor={stroke};strokeWidth=2;fontStyle=1;"
        )
    if kind == "data":
        return (
            common
            + "shape=cylinder3;boundedLbl=1;backgroundOutline=1;size=12;"
            + f"fillColor={fill};strokeColor={stroke};strokeWidth=2;fontStyle=1;"
        )
    if kind == "actor":
        return (
            common
            + "shape=mxgraph.basic.person;"
            + f"fillColor={fill};strokeColor={stroke};strokeWidth=2;fontStyle=1;"
        )
    if kind == "note":
        return (
            common
            + "shape=note;size=18;align=left;verticalAlign=top;spacing=10;"
            + f"fillColor={fill};strokeColor={stroke};fontSize=12;"
        )
    if kind == "title":
        return (
            common
            + "rounded=0;strokeColor=none;fillColor=none;align=left;"
            + "verticalAlign=middle;fontSize=28;fontStyle=1;fontColor=#0F172A;"
        )
    if kind == "subtitle":
        return (
            common
            + "rounded=0;strokeColor=none;fillColor=none;align=left;"
            + "verticalAlign=middle;fontSize=13;fontColor=#475569;"
        )
    return (
        common
        + "rounded=1;arcSize=14;align=center;verticalAlign=middle;spacing=8;"
        + f"fillColor={fill};strokeColor={stroke};strokeWidth=2;"
        + ("dashed=1;dashPattern=8 4;" if dashed else "")
    )


def _edge_style(color: str = "gray", *, dashed: bool = False) -> str:
    _, stroke = COLORS[color]
    return (
        "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;"
        "html=1;endArrow=block;endFill=1;strokeWidth=2;"
        f"strokeColor={stroke};fontColor=#334155;fontSize=12;labelBackgroundColor=#FFFFFF;"
        + ("dashed=1;dashPattern=8 4;" if dashed else "")
    )


@dataclass
class Page:
    name: str
    title: str
    subtitle: str
    source_note: str
    graph: ET.Element = field(init=False)
    root: ET.Element = field(init=False)
    seq: int = field(default=2, init=False)
    ids: dict[str, str] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.graph = ET.Element(
            "mxGraphModel",
            {
                "dx": "1920",
                "dy": "1080",
                "grid": "1",
                "gridSize": "10",
                "guides": "1",
                "tooltips": "1",
                "connect": "1",
                "arrows": "1",
                "fold": "1",
                "page": "1",
                "pageScale": "1",
                "pageWidth": "1920",
                "pageHeight": "1080",
                "math": "0",
                "shadow": "0",
            },
        )
        self.root = ET.SubElement(self.graph, "root")
        ET.SubElement(self.root, "mxCell", {"id": "0"})
        ET.SubElement(self.root, "mxCell", {"id": "1", "parent": "0"})
        self.vertex("__title", self.title, 42, 24, 1400, 44, kind="title")
        self.vertex("__subtitle", self.subtitle, 44, 68, 1700, 32, kind="subtitle")

    def _id(self, key: str) -> str:
        if key in self.ids:
            return self.ids[key]
        prefix = hashlib.sha1(self.name.encode("utf-8")).hexdigest()[:8]
        value = f"p{prefix}_{self.seq}"
        self.seq += 1
        self.ids[key] = value
        return value

    def vertex(
        self,
        key: str,
        value: str,
        x: int,
        y: int,
        w: int,
        h: int,
        *,
        kind: str = "box",
        color: str = "blue",
        dashed: bool = False,
    ) -> str:
        cell = ET.SubElement(
            self.root,
            "mxCell",
            {
                "id": self._id(key),
                "value": value,
                "style": _style(kind, color, dashed=dashed),
                "vertex": "1",
                "parent": "1",
            },
        )
        ET.SubElement(
            cell,
            "mxGeometry",
            {"x": str(x), "y": str(y), "width": str(w), "height": str(h), "as": "geometry"},
        )
        return cell.attrib["id"]

    def edge(
        self,
        source: str,
        target: str,
        label: str = "",
        *,
        color: str = "gray",
        dashed: bool = False,
    ) -> None:
        cell = ET.SubElement(
            self.root,
            "mxCell",
            {
                "id": self._id(f"edge_{self.seq}"),
                "value": label,
                "style": _edge_style(color, dashed=dashed),
                "edge": "1",
                "parent": "1",
                "source": self.ids[source],
                "target": self.ids[target],
            },
        )
        ET.SubElement(cell, "mxGeometry", {"relative": "1", "as": "geometry"})

    def footer(self) -> None:
        self.vertex("__legend", "Màu:  UI / API   •   Điều phối   •   Model   •   Dữ liệu   •   Safety   •   Offline / Eval", 42, 1000, 1070, 38, color="gray")
        self.vertex("__source", f"SOURCE-VERIFIED\n{self.source_note}", 1132, 966, 742, 72, kind="note", color="yellow")


def page_system_context() -> Page:
    p = Page(
        "01 - System Context",
        "AcneLLM — System Context & Runtime Boundaries",
        "Local-first Vietnamese acne advisory: browser UI → gateway → FastAPI → orchestration → models / knowledge / persistence",
        "docker-compose.yml; frontend/src; src/acne_llm/api/app.py; src/acne_llm/di.py",
    )
    p.vertex("client_lane", "CLIENT", 42, 125, 310, 785, kind="lane", color="blue")
    p.vertex("edge_lane", "EDGE & API", 382, 125, 470, 785, kind="lane", color="indigo")
    p.vertex("core_lane", "APPLICATION CORE", 882, 125, 505, 785, kind="lane", color="purple")
    p.vertex("infra_lane", "MODEL & DATA SERVICES", 1417, 125, 457, 785, kind="lane", color="green")

    p.vertex("user", "Người dùng", 120, 215, 150, 130, kind="actor", color="blue")
    p.vertex("frontend", "Next.js Chat UI\nChatWindow • Zustand\nuseSSE • SourceCard", 78, 420, 235, 135, color="blue")
    p.vertex("admin_client", "Admin / KB explorer\nFeedback & metrics consumer", 78, 645, 235, 105, color="cyan")

    p.vertex("gateway", "Nginx gateway\n:3000 → / and /api", 442, 190, 350, 90, color="indigo")
    p.vertex("middleware", "FastAPI middleware chain\nCORS → request log → API key → rate limit", 442, 335, 350, 115, color="indigo")
    p.vertex("routes", "API routers\n/chat/stream • /ws/chat • /debug/trace\n/kb/* • /health • /metrics • /admin/*", 442, 520, 350, 150, color="indigo")
    p.vertex("observability", "Observability\nMetricsRegistry • logs • health", 442, 755, 350, 85, color="cyan")

    p.vertex("container", "Dependency container\nbuild_container(settings)", 952, 175, 365, 80, color="purple")
    p.vertex("orchestrator", "Chat orchestration\nprepare_chat_turn + stream_chat_sse", 952, 315, 365, 105, color="purple")
    p.vertex("intake", "Intake & routing\npreprocess • guardrails • semantic / LLM route\nfield extraction • history fold", 922, 485, 425, 135, color="red")
    p.vertex("rag", "RAG subsystem\nhybrid retrieve • RRF • rerank\nsource cap • OOD/noise filters", 922, 690, 425, 135, color="orange")

    p.vertex("ollama", "Ollama service :11434\nacne-generator\nacne-intaker", 1487, 175, 317, 135, color="orange")
    p.vertex("kb", "Knowledge indexes\nChromaDB vectors\nBM25 sparse index", 1487, 385, 317, 125, kind="data", color="green")
    p.vertex("sqlite", "Persistent state\nsessions.db • audit.db\nDiskCache", 1487, 585, 317, 125, kind="data", color="green")
    p.vertex("config", "Read-only runtime assets\nconfig/ • prompts/ • model/", 1487, 785, 317, 85, kind="data", color="gray")

    p.edge("user", "frontend", "message")
    p.edge("frontend", "gateway", "HTTP / SSE")
    p.edge("admin_client", "gateway", "REST")
    p.edge("gateway", "middleware", "proxy /api")
    p.edge("middleware", "routes")
    p.edge("routes", "container", "app.state.container", color="indigo")
    p.edge("container", "orchestrator")
    p.edge("orchestrator", "intake")
    p.edge("orchestrator", "rag")
    p.edge("container", "ollama", "generate / stream", color="orange")
    p.edge("rag", "kb", "dense + sparse")
    p.edge("orchestrator", "sqlite", "session + audit")
    p.edge("container", "config", "load on startup", dashed=True)
    p.edge("routes", "observability", "telemetry", dashed=True)
    p.edge("routes", "frontend", "token • source • done", color="blue")
    p.footer()
    return p


def page_chat_flow() -> Page:
    p = Page(
        "02 - Chat SSE Workflow",
        "Online Chat Request — Input to Streamed Output",
        "Production path shared by HTTP SSE, WebSocket, debug trace and non-stream evaluation preparation",
        "frontend/src/hooks/useSSE.ts; src/acne_llm/api/routes/chat.py; src/acne_llm/chat/runtime.py; src/acne_llm/chat/orchestrator.py",
    )
    lanes = [
        ("ui_lane", "FRONTEND", 42, 130, 285, "blue"),
        ("api_lane", "TRANSPORT", 347, 130, 285, "indigo"),
        ("prep_lane", "PREPARE TURN", 652, 130, 360, "purple"),
        ("gen_lane", "GENERATION", 1032, 130, 350, "orange"),
        ("out_lane", "POST-PROCESS & STATE", 1402, 130, 472, "green"),
    ]
    for key, label, x, y, w, color in lanes:
        p.vertex(key, label, x, y, w, 790, kind="lane", color=color)
    p.vertex("input", "MessageInput / ChatWindow\nvalidate non-empty client-side", 72, 205, 225, 90, color="blue")
    p.vertex("fetch", "useSSE.sendMessage\nGET createStreamUrl(...)", 72, 385, 225, 90, color="blue")
    p.vertex("render", "Zustand chatStore\nappend token • source card\nmode / evidence / latency", 72, 690, 225, 145, color="blue")

    p.vertex("gateway", "Nginx → FastAPI", 382, 205, 215, 75, color="indigo")
    p.vertex("limits", "Route validation\nchars ≤ MAX • words ≤ MAX\nmessage required", 382, 355, 215, 110, color="red")
    p.vertex("transport", "StreamingResponse\ntext/event-stream\n(no buffering)", 382, 555, 215, 100, color="indigo")
    p.vertex("ws", "Alternate /ws/chat\nthread → asyncio.Queue\nframe-by-frame", 382, 745, 215, 115, color="cyan", dashed=True)

    p.vertex("prepare", "prepare_chat_turn", 722, 195, 220, 70, color="purple")
    p.vertex("intake", "run_intake\nclean + history + safety + route", 722, 335, 220, 100, color="red")
    p.vertex("decision", "effective mode?", 747, 500, 170, 120, kind="decision", color="yellow")
    p.vertex("retrieval", "hybrid → retrieve_for_chat\notherwise skip", 722, 700, 220, 95, color="orange")
    p.vertex("prompt", "PromptBuilder.build\ntemplate + profile + history + chunks", 1077, 195, 260, 115, color="purple")
    p.vertex("model", "OllamaBackend.stream_text\nacne-generator", 1077, 400, 260, 100, color="orange")
    p.vertex("stream", "Yield token frames\nstrip leaked labels / CJK\npreserve pre-prefix", 1077, 610, 260, 125, color="orange")

    p.vertex("sources", "Emit source frames\nfull chunk text + metadata + score", 1457, 195, 362, 90, color="green")
    p.vertex("safety", "get_safety_suffix\nretinoid • Rx • age • urgent flags\nself-procedure • disclaimer", 1457, 355, 362, 130, color="red")
    p.vertex("persist", "Persist after generation\nsession turn + normalized snapshot\naudit entry + latency / route", 1457, 565, 362, 135, color="green")
    p.vertex("done", "done event\nmode • evidence_quality • latency\nroute metadata • audit_id", 1457, 785, 362, 90, color="cyan")

    p.edge("input", "fetch")
    p.edge("fetch", "gateway")
    p.edge("gateway", "limits")
    p.edge("limits", "transport", "valid")
    p.edge("transport", "prepare")
    p.edge("prepare", "intake")
    p.edge("intake", "decision")
    p.edge("decision", "retrieval", "hybrid", color="orange")
    p.edge("decision", "prompt", "refuse / clarify / llm_only", color="purple")
    p.edge("retrieval", "prompt", "top chunks")
    p.edge("prompt", "model")
    p.edge("model", "stream")
    p.edge("stream", "sources")
    p.edge("sources", "safety")
    p.edge("safety", "persist")
    p.edge("persist", "done")
    p.edge("done", "render", "SSE token/source/done", color="blue")
    p.edge("transport", "ws", "same generator", dashed=True)
    p.edge("ws", "render", "JSON frames", color="cyan", dashed=True)
    p.footer()
    return p


def page_intake() -> Page:
    p = Page(
        "03 - Intake Safety Routing",
        "Intake, Hard Safety and Router-First Control Flow",
        "Rules decide hard safety; router selects intent; extractor enriches fields; history is folded only through confirmed snapshots",
        "src/acne_llm/chat/intake.py; preprocess.py; unified_intake.py; chat/fallback/*; guardrails/*; src/acne_llm/di.py",
    )
    p.vertex("input_lane", "INPUT NORMALIZATION", 42, 130, 350, 790, kind="lane", color="blue")
    p.vertex("safety_lane", "HARD SAFETY", 412, 130, 330, 790, kind="lane", color="red")
    p.vertex("route_lane", "ROUTING & EXTRACTION", 762, 130, 555, 790, kind="lane", color="purple")
    p.vertex("state_lane", "FOLD & EFFECTIVE MODE", 1337, 130, 537, 790, kind="lane", color="green")

    p.vertex("raw", "Raw Vietnamese message\n+ requested mode + session_id", 92, 205, 250, 90, color="blue")
    p.vertex("clean", "prepare_user_text\ntrim • normalized spacing\nno-accent view • teencode map", 92, 385, 250, 115, color="blue")
    p.vertex("history", "SQLite session history\nrecent turns + confirmed snapshots", 92, 650, 250, 110, kind="data", color="green")

    p.vertex("pii_scope", "Guardrail pre-check\nPII detect • hard OOS / genital scope\nunsafe medication request", 457, 210, 240, 135, color="red")
    p.vertex("hard_decision", "hard refusal?", 492, 430, 170, 120, kind="decision", color="red")
    p.vertex("ruling", "AdviseOutput ruling\ncauses + mandatory disclaimer\n(generator still writes prose)", 457, 680, 240, 125, color="red")

    p.vertex("mode", "INTAKE_MODE selector", 832, 190, 210, 70, color="purple")
    p.vertex("unified", "unified\nUnifiedIntake → acne-intaker\none JSON contract: route + fields", 802, 340, 260, 120, color="orange")
    p.vertex("legacy", "legacy fallback\nSemanticRouter / LLMRouter / rules\nLLMExtractor / rule extractor", 1087, 340, 190, 120, color="purple")
    p.vertex("route", "RouteDecision\nprimary_intent + confidence\nroute_flags + reason_code", 802, 565, 225, 120, color="purple")
    p.vertex("extract", "Field results\nvalue + method + confidence\nlow-confidence → prompt hedge", 1052, 565, 225, 120, color="yellow")
    p.vertex("intake_result", "IntakeResult\nroute + fields + confirmed profile + safety terms", 852, 710, 375, 72, color="purple")
    p.vertex("fallback", "Timeout / schema / model failure → deterministic fallback", 852, 815, 375, 48, color="gray", dashed=True)

    p.vertex("fold", "Fold confirmed history\ncurrent snapshot + prior safe facts\nprofile safety terms", 1402, 205, 407, 120, color="green")
    p.vertex("med_check", "Medication & clinical safety re-check\ncurrent + extracted + folded context", 1402, 405, 407, 105, color="red")
    p.vertex("effective", "EffectiveMode", 1510, 590, 190, 120, kind="decision", color="yellow")
    p.vertex("modes", "clarify  |  refuse\nhybrid  |  llm_only", 1442, 790, 327, 70, color="green")

    p.edge("raw", "clean")
    p.edge("history", "clean", "history window", dashed=True)
    p.edge("clean", "pii_scope")
    p.edge("pii_scope", "hard_decision")
    p.edge("hard_decision", "ruling", "yes", color="red")
    p.edge("hard_decision", "mode", "no")
    p.edge("mode", "unified", "unified", color="orange")
    p.edge("mode", "legacy", "legacy")
    p.edge("unified", "route")
    p.edge("unified", "extract")
    p.edge("legacy", "route")
    p.edge("legacy", "extract")
    p.edge("unified", "fallback", dashed=True)
    p.edge("legacy", "fallback", dashed=True)
    p.edge("fallback", "intake_result", "rules", dashed=True)
    p.edge("route", "intake_result")
    p.edge("extract", "intake_result")
    p.edge("intake_result", "fold")
    p.edge("fold", "med_check")
    p.edge("med_check", "effective")
    p.edge("effective", "modes")
    p.footer()
    return p


def page_rag() -> Page:
    p = Page(
        "04 - RAG and KB Lifecycle",
        "Knowledge Base Lifecycle & Hybrid Retrieval",
        "Offline ingestion produces two synchronized indexes; runtime retrieves broadly, reranks, then applies semantic and safety filters",
        "scripts/crawl_all.py; scripts/build_kb.py; src/acne_llm/rag/*; src/acne_llm/chat/_retrieval.py; data/raw/chunks.jsonl",
    )
    p.vertex("offline_lane", "OFFLINE — CRAWL, CLEAN, CHUNK, INDEX", 42, 130, 1832, 370, kind="lane", color="cyan")
    p.vertex("runtime_lane", "ONLINE — QUERY, HYBRID RETRIEVE, RERANK, FILTER", 42, 535, 1832, 390, kind="lane", color="orange")

    p.vertex("sources", "Approved sources\nguidelines • hospitals • PubMed\ntrusted acne pages", 82, 215, 225, 110, color="blue")
    p.vertex("crawl", "Crawler pipeline\ndiscovery → fetch → extract\nnormalize → quality filter → dedup", 347, 205, 275, 130, color="cyan")
    p.vertex("docs", "documents.jsonl\n+ crawl checkpoint", 662, 215, 210, 110, kind="data", color="green")
    p.vertex("chunk", "build_kb step: chunk\nclean_vi_text • topic/language/noise filters\nexact + near-dup • rebuild links", 912, 195, 310, 150, color="cyan")
    p.vertex("chunks", "chunks.jsonl\ncanonical source-of-truth chunks", 1262, 215, 230, 110, kind="data", color="green")
    p.vertex("embed", "Embedder\n→ ChromaStore", 1532, 195, 130, 120, color="orange")
    p.vertex("bm25build", "BM25Index.build", 1692, 195, 140, 120, color="orange")
    p.vertex("chroma", "ChromaDB\nvectors", 1512, 365, 170, 90, kind="data", color="green")
    p.vertex("bm25", "bm25_index.pkl", 1692, 365, 140, 90, kind="data", color="green")

    p.vertex("query", "Normalized query\n+ route_flags + safety_terms\n+ confirmed profile", 82, 625, 250, 120, color="purple")
    p.vertex("hybrid", "HybridRetriever\nDense search + BM25 search", 382, 625, 245, 110, color="orange")
    p.vertex("merge", "RRF / merge retrievals\noptional safety-focused query", 677, 625, 245, 110, color="orange")
    p.vertex("rerank", "Cross-encoder Reranker\nwide pool (top_k × 3)", 972, 625, 230, 100, color="orange")
    p.vertex("filters", "Post-rerank controls\ncap per source → score floor\nacne/boil + body region filter\nnoise removal", 1252, 600, 265, 155, color="red")
    p.vertex("guideline", "ensure_guideline_slot\nreserve trusted guidance when present", 1567, 625, 240, 110, color="green")
    p.vertex("top_chunks", "RetrievalOutput\n≤ configured top_k chunks\nfull metadata + score", 1512, 805, 300, 85, kind="data", color="green")
    p.vertex("rag_none", "No KB / no relevant chunk\n→ retrieval=None → llm_only evidence", 972, 805, 400, 85, color="gray", dashed=True)

    p.edge("sources", "crawl")
    p.edge("crawl", "docs")
    p.edge("docs", "chunk")
    p.edge("chunk", "chunks")
    p.edge("chunks", "embed")
    p.edge("chunks", "bm25build")
    p.edge("embed", "chroma")
    p.edge("bm25build", "bm25")
    p.edge("chroma", "hybrid", dashed=True)
    p.edge("bm25", "hybrid", dashed=True)
    p.edge("query", "hybrid")
    p.edge("hybrid", "merge")
    p.edge("merge", "rerank")
    p.edge("rerank", "filters")
    p.edge("filters", "guideline")
    p.edge("guideline", "top_chunks")
    p.edge("filters", "rag_none", "all below floor", color="red", dashed=True)
    p.footer()
    return p


def page_finetune() -> Page:
    p = Page(
        "05 - Finetune Data Factory",
        "Finetune Data Factory — Intaker vs Generator",
        "Two independent provenance paths: unified-intake records for structured extraction, roledata records for generator behavior and grounded responses",
        "datagen/intakedata/*; datagen/roledata/*; datagen/roledata/output/*; data/raw/chunks.jsonl",
    )
    p.vertex("intaker_lane", "INTAKER DATA — datagen/intakedata", 42, 130, 900, 790, kind="lane", color="indigo")
    p.vertex("generator_lane", "GENERATOR DATA — datagen/roledata", 972, 130, 902, 790, kind="lane", color="purple")

    p.vertex("i_inputs", "Inputs\ntaxonomy.yaml • canonical system prompt\ngolden relabel seeds • eval hashes", 82, 200, 240, 125, color="blue")
    p.vertex("i_seed", "Case scheduler + deterministic seed\nuser turn / history / expected JSON", 367, 200, 250, 110, color="indigo")
    p.vertex("i_api", "OpenAI-compatible generator\nstructured JSON candidate", 662, 200, 235, 100, color="orange")
    p.vertex("i_gate", "Per-record gates\nschema • case/intent contract\nfield validity • hallucination checks", 82, 425, 250, 135, color="red")
    p.vertex("i_writer", "Append-only writer\ndedup / resume + audit rejection log", 382, 425, 235, 115, color="green")
    p.vertex("i_corpus", "Corpus validation\nquota • contamination • duplicates", 662, 425, 235, 115, color="red")
    p.vertex("i_split", "Deterministic 90/10 split\ntrain.jsonl + val.jsonl", 242, 680, 255, 95, kind="data", color="green")
    p.vertex("i_out", "Unified intake finetune set\nassistant_json contract", 562, 680, 255, 95, kind="data", color="green")

    p.vertex("g_inputs", "Inputs\ntaxonomy + Jinja case prompts\ncanonical generator anchor", 1012, 195, 250, 125, color="blue")
    p.vertex("g_kb", "Grounding source\ndata/raw/chunks.jsonl\n+ optional distractor context", 1342, 200, 250, 110, kind="data", color="green")
    p.vertex("g_api", "OpenAI generator\nrole/behavior response candidate", 1012, 345, 280, 105, color="orange")
    p.vertex("g_gate", "Role + safety + corpus gates\nsystem parity • Vietnamese • grounding\nrefusal / clarification / phrase frequency", 1012, 505, 280, 135, color="red")
    p.vertex("g_writer", "roledata.train.jsonl\nappend-only accepted rows\nrejected.audit.jsonl for attempts", 1337, 505, 230, 125, kind="data", color="green")
    p.vertex("g_validate", "Corpus validation\n3,465 accepted / target 3,500\nstatus: incomplete", 1612, 505, 210, 125, color="yellow")
    p.vertex("g_split", "Leakage-safe 85/8/7\ntrain 2,945 • val 277 • holdout 243", 1112, 690, 285, 95, kind="data", color="green")
    p.vertex("g_export", "LLaMA-Factory export\nacnellm_role_lora.jsonl\ndataset card + SHA-256", 1477, 675, 285, 125, kind="data", color="green")

    p.edge("i_inputs", "i_seed")
    p.edge("i_seed", "i_api")
    p.edge("i_api", "i_gate")
    p.edge("i_gate", "i_writer")
    p.edge("i_writer", "i_corpus")
    p.edge("i_corpus", "i_split")
    p.edge("i_split", "i_out")

    p.edge("g_inputs", "g_api", "case prompt")
    p.edge("g_kb", "g_api", "context")
    p.edge("g_api", "g_gate")
    p.edge("g_gate", "g_writer")
    p.edge("g_writer", "g_validate")
    p.edge("g_validate", "g_split")
    p.edge("g_split", "g_export")
    p.footer()
    return p


def page_eval() -> Page:
    p = Page(
        "06 - Evaluation and Ablation",
        "Evaluation Harness — Deterministic Metrics, Judge Scoring and Paired Ablation",
        "Fail-soft orchestration keeps provenance per stage; all arms share immutable question IDs and compare against RRR with paired deltas",
        "evaluation/full_evaluation.py; evaluation/runners/*; evaluation/judges/*; evaluation/metrics/*; evaluation/reports/run_full_v3_2",
    )
    p.vertex("inputs_lane", "INPUTS & PREFLIGHT", 42, 130, 370, 790, kind="lane", color="blue")
    p.vertex("tasks_lane", "EVALUATION TASKS", 432, 130, 620, 790, kind="lane", color="purple")
    p.vertex("judge_lane", "JUDGE & METRICS", 1072, 130, 370, 790, kind="lane", color="orange")
    p.vertex("art_lane", "ARTIFACTS & INTERPRETATION", 1462, 130, 412, 790, kind="lane", color="green")

    p.vertex("datasets", "Datasets\neval_set.v3.jsonl\nintake_eval.v1/v2\npolicy cases", 92, 200, 270, 125, kind="data", color="blue")
    p.vertex("preflight", "Preflight\npaths • KB/model readiness\njudge key + judge-lineage warning", 92, 405, 270, 125, color="red")
    p.vertex("summary_run", "Atomic run summary\nstep start / finish / skip / fail\nresume-friendly output directory", 92, 680, 270, 115, kind="data", color="green")

    p.vertex("t1", "T1 — Intake evaluation\nintent / slot / field metrics\ndeterministic; no judge", 482, 205, 240, 120, color="indigo")
    p.vertex("t2", "T2 — Retrieval evaluation\nreal RAG chunks vs expected evidence\ncontext judge required", 762, 205, 240, 120, color="orange")
    p.vertex("arms", "Ablation arms [intake][RAG][generator]\nRRR baseline • RNR • ROR\nORR • RRO • RNO (+ full lattice)", 482, 430, 520, 130, color="purple")
    p.vertex("shared", "Shared question IDs + checkpoint rows.jsonl\nreal/oracle/no-RAG substitutions only\ncommon prompt and model lineage captured", 482, 690, 520, 125, color="cyan")

    p.vertex("judge", "JudgeClient\nDeepSeek/OpenAI-compatible API\nprompt rubrics + retry + cache", 1127, 200, 260, 130, color="orange")
    p.vertex("score", "Scorecards\nquality faces + binary safety faces\nseparate safety failure count", 1127, 425, 260, 125, color="red")
    p.vertex("paired", "Paired statistics\nper-question delta vs RRR\nconfidence intervals / ranking / cost", 1127, 660, 260, 130, color="orange")

    p.vertex("reports", "run_full_v3_2 artifacts\nintake/report.json\nretrieval/results.json\nablation rows/results/summary", 1517, 195, 302, 155, kind="data", color="green")
    p.vertex("limits", "Interpretation gates\ncompleted vs skipped vs incomplete\njudge lineage • cache provenance\nsynthetic evidence ≠ production proof", 1517, 450, 302, 145, color="yellow")
    p.vertex("visuals", "Visualization & thesis reporting\ncharts • tables • architecture\nsource-linked conclusions", 1517, 700, 302, 110, color="cyan")

    p.edge("datasets", "preflight")
    p.edge("preflight", "summary_run", "initialize")
    p.edge("preflight", "t1")
    p.edge("preflight", "t2")
    p.edge("preflight", "arms")
    p.edge("t1", "reports")
    p.edge("t2", "judge")
    p.edge("arms", "shared")
    p.edge("shared", "judge")
    p.edge("judge", "score")
    p.edge("score", "paired")
    p.edge("paired", "reports")
    p.edge("summary_run", "reports")
    p.edge("reports", "limits")
    p.edge("limits", "visuals")
    p.footer()
    return p


def page_docker() -> Page:
    p = Page(
        "07 - Docker Deployment",
        "Docker Compose Deployment — Startup Order, Network and Persistent State",
        "Gateway is the only published port; Ollama, API and frontend stay on the internal Compose network",
        "docker-compose.yml; docker-compose.gpu.yml; Dockerfile; frontend/Dockerfile; docker/nginx/default.conf.template; docker/ollama-init.sh",
    )
    p.vertex("host_lane", "HOST / USER", 42, 130, 310, 790, kind="lane", color="blue")
    p.vertex("network_lane", "COMPOSE INTERNAL NETWORK", 382, 130, 995, 790, kind="lane", color="indigo")
    p.vertex("storage_lane", "PERSISTENCE & CONFIG", 1407, 130, 467, 790, kind="lane", color="green")

    p.vertex("browser", "Browser\nhttp://localhost:${APP_PORT:-3000}", 92, 230, 210, 105, kind="actor", color="blue")
    p.vertex("gpu", "Optional host GPU\ndocker-compose.gpu.yml\nNVIDIA reservation", 92, 560, 210, 110, color="orange", dashed=True)

    p.vertex("gateway", "gateway\nnginx:1.27-alpine\nPUBLISHED :3000 → :80", 730, 190, 300, 115, color="indigo")
    p.vertex("frontend", "frontend\nNext.js production image\nEXPOSE 3000", 472, 390, 270, 110, color="blue")
    p.vertex("api", "acne-llm\nFastAPI / Uvicorn\nEXPOSE 8000 • non-root user", 1042, 390, 270, 115, color="purple")
    p.vertex("init", "ollama-init (one-shot)\nwait healthy → create/import\nacne-generator + acne-intaker", 472, 625, 300, 120, color="yellow")
    p.vertex("ollama", "ollama\nollama/ollama image\nEXPOSE 11434", 1042, 625, 270, 115, color="orange")
    p.vertex("health", "Startup gates: ollama healthy → init completed → API healthy (KB + BM25) → frontend → gateway", 642, 820, 520, 62, color="red")

    p.vertex("volume", "Named volume\nollama_data\nmodel blobs + manifests", 1472, 205, 337, 110, kind="data", color="green")
    p.vertex("bind_data", "Bind mount ./data → /app/data\nChromaDB • BM25 • sessions.db\naudit.db • caches", 1472, 405, 337, 135, kind="data", color="green")
    p.vertex("bind_ro", "Read-only mounts\n./config → /app/config\n./model → /models\nnginx template + init script", 1472, 635, 337, 135, kind="data", color="gray")

    p.edge("browser", "gateway", "HTTP / SSE")
    p.edge("gateway", "frontend", "/")
    p.edge("gateway", "api", "/api/* + API key header")
    p.edge("api", "ollama", "OLLAMA_URL=http://ollama:11434", color="orange")
    p.edge("init", "ollama", "model create / list", color="orange")
    p.edge("ollama", "volume")
    p.edge("api", "bind_data")
    p.edge("ollama", "bind_ro", "read-only mounts", dashed=True)
    p.edge("gpu", "ollama", "optional device", color="orange", dashed=True)
    p.edge("health", "gateway", "dependency readiness", color="red", dashed=True)
    p.footer()
    return p


def build() -> None:
    pages = [
        page_system_context(),
        page_chat_flow(),
        page_intake(),
        page_rag(),
        page_finetune(),
        page_eval(),
        page_docker(),
    ]
    mxfile = ET.Element(
        "mxfile",
        {
            "host": "app.diagrams.net",
            "modified": "2026-08-09T00:00:00.000Z",
            "agent": "AcneLLM source-verified architecture generator",
            "version": "24.7.17",
            "type": "device",
            "compressed": "false",
        },
    )
    for index, page in enumerate(pages, start=1):
        diagram = ET.SubElement(mxfile, "diagram", {"id": f"acnellm-arch-{index}", "name": page.name})
        diagram.append(page.graph)
    tree = ET.ElementTree(mxfile)
    ET.indent(tree, space="  ")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    tree.write(OUT, encoding="utf-8", xml_declaration=True)
    print(f"Wrote {OUT} ({len(pages)} pages)")


if __name__ == "__main__":
    build()
