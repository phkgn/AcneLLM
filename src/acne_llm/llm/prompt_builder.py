"""Jinja2 prompt builder với sanitization chống injection."""
from __future__ import annotations
from dataclasses import replace
import re
from jinja2 import Environment, FileSystemLoader, select_autoescape
from ..schemas import UserInput, RetrievalOutput
from ..schemas.kb import infer_source_type
from ..chat.session import (
    HISTORY_WINDOW_TURNS,
    ConversationTurn,
    format_history_block,
)

# Injection markers phổ biến trong chunk text (nếu crawler lấy về trang độc hại)
_INJECTION_MARKERS = (
    "ignore previous", "ignore all previous", "forget prior",
    "override instructions", "system override", "from now on",
    "you are now", "act as", "pretend to be", "disregard",
    "bỏ qua hướng dẫn", "bỏ tất cả", "quên tất cả", "ghi đè",
    "[system]", "[/system]", "[inst]", "[/inst]",
    "<|system|>", "<|user|>", "<|assistant|>",
    "###instruction", "### instruction",
)


def _escape_jinja(value: str) -> str:
    """Neutralise Jinja2 delimiter sequences so user text cannot
    alter template structure or inject instructions at render time.
    """
    return (
        value
        .replace("{{", "{ {")
        .replace("}}", "} }")
        .replace("{%", "{ %")
        .replace("%}", "% }")
        .replace("{#", "{ #")
        .replace("#}", "# }")
    )


def _sanitize_chunk_text(text: str) -> str:
    """Làm sạch text chunk trước khi inject vào prompt.

    1. Bỏ HTML tags thô còn sót từ crawler.
    2. Neutralize injection markers.
    3. Bỏ control characters.
    4. Collapse whitespace.
    """
    if not text:
        return ""
    # Bỏ HTML tags thô
    text = re.sub(r"<[^>]{1,200}>", " ", text)
    # Neutralize injection markers
    lower = text.lower()
    for marker in _INJECTION_MARKERS:
        if marker in lower:
            text = re.sub(re.escape(marker), "[nội dung đã lọc]", text, flags=re.IGNORECASE)
    # Bỏ control characters (ngoài newline, tab)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Collapse whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def sanitize_history_turns(history: list[ConversationTurn]) -> list[ConversationTurn]:
    """Return history copies with prompt-injection markers neutralized per turn."""
    return [
        replace(turn, content=_sanitize_chunk_text(turn.content))
        for turn in history
    ]


def _sanitize_user_description(text: str) -> str:
    """Neutralize injection markers trong user-supplied text trước khi inject vào prompt.

    Khác _sanitize_chunk_text:
    - Không strip HTML (user text không có HTML từ crawler).
    - Không collapse whitespace mạnh (giữ định dạng user gõ).
    - Chỉ: neutralize injection markers + bỏ control chars nguy hiểm.

    Lý do cần riêng: guardrails.pre_check() chạy trên raw text trước preprocess,
    nhưng prompt nhận preprocessed text — có window nhỏ để bypass nếu teencode/
    unicode variant được normalize thành injection phrase sau preprocess.
    """
    if not text:
        return ""
    # Bỏ control characters (ngoài newline, tab)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Neutralize injection markers (case-insensitive)
    lower = text.lower()
    for marker in _INJECTION_MARKERS:
        if marker in lower:
            text = re.sub(re.escape(marker), "[nội dung đã lọc]", text, flags=re.IGNORECASE)
            lower = text.lower()  # re-check sau mỗi substitution
    return text


class PromptBuilder:
    """Render user prompt. Khối nào KHÔNG có luật tương ứng trong Modelfile
    SYSTEM thì không gửi.

    SYSTEM tuyên bố đúng 4 loại dữ kiện và thứ hạng của chúng:
        tin nhắn hiện tại > dữ kiện an toàn đã xác nhận
        > ngữ cảnh gần nhất > tài liệu tham khảo
    Template phát đúng 4 khối đó, xếp ngược thứ hạng (cao nhất xuống cuối).

    ponytail: known_facts (nhãn regex suy đoán) và route_guidance bị bỏ — SYSTEM
    không có luật xử lý chúng nên model tự đoán. Thêm lại khi đo được là thiếu
    chúng làm giảm chất lượng, không phải vì "có thì hơn".
    """

    # Giới hạn ký tự tối đa cho mỗi chunk trong context block
    _MAX_CHARS_PER_CHUNK: int = 800

    def __init__(self, templates_dir: str = "config/prompts"):
        self.env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape([]),
            trim_blocks=True, lstrip_blocks=True,
        )

    # Badge hiển thị trong prompt để LLM biết nguồn nào authoritative
    _SOURCE_BADGES: dict[str, str] = {
        "nice_guideline":    "[NICE Guideline]",
        "aad_guideline":     "[AAD Guideline]",
        "jid_paper":         "[JID Paper]",
        "pubmed_review":     "[PubMed Review]",
        "clinical_textbook": "[Textbook]",
        # Tầng thấp PHẢI có nhãn. Trước đây chúng nhận "" nên khi cả 5 chunk đều là
        # trang tin phổ thông — trường hợp thường gặp, xem log rerank — generator
        # thấy 5 nguồn không nhãn, ngang hàng nhau, và không có cơ sở nào để xếp
        # hạng bằng chứng. Nó xử lý "uống ít nước" ngang với "tuyến bã nhờn hoạt
        # động mạnh" rồi kết luận "các nguồn chưa thống nhất". Nhãn không ép chunk
        # nào vào câu trả lời, chỉ thôi giấu thứ bậc đi.
        "vi_medical_site":   "[Trang tin sức khỏe]",
        "forum_post":        "[Diễn đàn — độ tin cậy thấp]",
        "blog":              "[Blog — độ tin cậy thấp]",
    }

    def _context_block(
        self,
        retrieval: RetrievalOutput | None,
        max_chars: int = 6000,
    ) -> str:
        if not retrieval or not retrieval.chunks:
            return "(không có ngữ cảnh từ tri thức phù hợp.)"
        blocks: list[str] = []
        used_chars = 0
        total_chunks = len(retrieval.chunks)
        for i, c in enumerate(retrieval.chunks, 1):
            meta = c.metadata or {}
            title = meta.get("title", "?") or "?"
            source = meta.get("source", "?") or "?"
            source_type = meta.get("source_type") or infer_source_type(
                source_name=str(source),
                domain=str(meta.get("domain") or ""),
                url=str(meta.get("url") or ""),
                tags=meta.get("tags") or [],
                categories=meta.get("categories") or [],
            )
            badge = self._SOURCE_BADGES.get(source_type, "")
            badge_str = f" {badge}" if badge else ""
            header = f"Nguồn {i} —{badge_str} {title} | {source}\n"
            # Sanitize chunk text trước khi inject vào prompt
            text = _sanitize_chunk_text(c.text)
            remaining = max_chars - used_chars
            if remaining <= 0:
                break
            header_len = len(header)
            sep_len = 5  # "\n---\n"
            # Giới hạn kép: budget tổng và budget mỗi chunk
            remaining_chunks = max(1, total_chunks - i + 1)
            dynamic_chunk_budget = max(
                self._MAX_CHARS_PER_CHUNK,
                (remaining - header_len - sep_len) // remaining_chunks,
            )
            text_budget = min(remaining - header_len - sep_len, dynamic_chunk_budget)
            if text_budget <= 0:
                break
            if len(text) > text_budget:
                text = self._truncate_at_sentence(text, text_budget)
            block = header + text
            blocks.append(block)
            used_chars += len(block) + sep_len
        return "\n---\n".join(blocks) if blocks else "(không có ngữ cảnh từ tri thức phù hợp.)"

    @staticmethod
    def _truncate_at_sentence(text: str, budget: int) -> str:
        if len(text) <= budget:
            return text
        snippet = text[:budget].strip()
        sentence_cut = max(snippet.rfind("."), snippet.rfind("!"), snippet.rfind("?"), snippet.rfind("。"))
        if sentence_cut >= max(80, int(budget * 0.55)):
            snippet = snippet[:sentence_cut + 1].strip()
        else:
            snippet = snippet.rsplit(" ", 1)[0].strip()
        return snippet + "..."

    def build(
        self,
        user: UserInput,
        retrieval: RetrievalOutput | None,
        template: str = "stream_user.j2",
        max_context_chars: int = 6000,
        history: list[ConversationTurn] | None = None,
        prompt_note: str | None = None,
        confirmed_profile: dict | None = None,
    ) -> tuple[str, str]:
        # Modelfile SYSTEM là nguồn sự thật DUY NHẤT cho hành vi model
        # (use_modelfile_system=True → backend bỏ system message). Repo không gửi
        # system prompt; user template chỉ mang dữ liệu + format contract theo endpoint.
        sys_p = ""
        has_kb = retrieval is not None and bool(retrieval.chunks)
        safe_description = _escape_jinja(_sanitize_user_description(user.description))
        if template == "reject_user.j2":
            # Soft OOS reject is intentionally data-minimal: no clinical fields,
            # history, or retrieved chunks may enter this prompt.
            user_p = self.env.get_template(template).render(
                description=safe_description,
            )
            return sys_p, user_p
        safe_context = _escape_jinja(self._context_block(
            retrieval,
            max_chars=max_context_chars,
        ))
        safe_history = _escape_jinja(format_history_block(
            sanitize_history_turns(history or []),
            max_turns=HISTORY_WINDOW_TURNS,
        ))
        profile = confirmed_profile or {}
        safety_facts: list[str] = []
        if profile.get("is_pregnant"):
            safety_facts.append("đang mang thai")
        if profile.get("is_breastfeeding"):
            safety_facts.append("đang cho con bú")
        if profile.get("allergies"):
            safety_facts.append("dị ứng: " + ", ".join(profile["allergies"]))
        if profile.get("medications"):
            safety_facts.append("thuốc đã xác nhận: " + ", ".join(profile["medications"]))
        safe_confirmed_safety = _escape_jinja("; ".join(safety_facts))
        # Completeness hint: hướng dẫn LLM hỏi thêm thay vì gate cứng
        safe_prompt_note = _escape_jinja(prompt_note or "")

        user_p = self.env.get_template(template).render(
            description=safe_description,
            retrieved_context=safe_context,
            history_block=safe_history,
            prompt_note=safe_prompt_note,
            has_retrieved_context=has_kb,
            confirmed_safety_facts=safe_confirmed_safety,
        )
        return sys_p, user_p
