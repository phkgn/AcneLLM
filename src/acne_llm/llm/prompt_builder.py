"""Jinja2 prompt builder với sanitization chống injection."""
from __future__ import annotations
from dataclasses import replace
import re
from jinja2 import Environment, FileSystemLoader, select_autoescape
from ..schemas import UserInput, RetrievalOutput, VisionOutput
from ..schemas.clinical import ClinicalQueryPlan
from ..schemas.kb import infer_source_type
from ..chat.session import ConversationTurn, format_history_block

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


def _route_guidance(route_metadata: dict | None) -> str:
    """Trả về hướng dẫn ngắn gọn từ route flags — không expose metadata nội bộ.

    Thay vì dump toàn bộ route_metadata vào prompt (tốn ~400 token),
    chỉ trích những guidance thực sự hữu ích cho model.
    """
    if not route_metadata:
        return ""
    flags = route_metadata.get("route_flags") or []
    query_subject = route_metadata.get("query_subject", "self")
    guidance: list[str] = []
    if query_subject == "non_self":
        guidance.append("Không xem nội dung này là hồ sơ cá nhân của user.")
    if "crisis_signal" in flags:
        guidance.append("Ưu tiên phản hồi an toàn, khuyến khích tìm hỗ trợ khẩn cấp.")
    if "multi_condition" in flags:
        guidance.append("Tránh khẳng định chắc khi có bệnh da không thuần acne; cân nhắc khuyên khám.")
    if "product_safety_check" in flags:
        guidance.append("Tập trung kiểm tra hoạt chất/sản phẩm và rủi ro kích ứng.")
    if "urgency_red_flag" in flags:
        guidance.append("Nhắc dấu hiệu cần khám sớm.")
    if "mixed_genital_scope" in flags:
        guidance.append(
            "Tin nhắn có cả vùng da trong phạm vi và vùng sinh dục/hậu môn; "
            "chỉ tư vấn phần mặt/lưng/ngực/vai/cổ, từ chối ngắn phần vùng kín."
        )
    return " ".join(guidance) if guidance else ""


class PromptBuilder:
    # Giới hạn ký tự tối đa cho mỗi chunk trong context block
    _MAX_CHARS_PER_CHUNK: int = 800

    def __init__(self, templates_dir: str = "config/prompts"):
        self.env = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape([]),
            trim_blocks=True, lstrip_blocks=True,
        )

    def _vision_summary(self, v: VisionOutput | None) -> str:
        if not v:
            return "không có dữ liệu hình ảnh"
        parts = [f"mức độ ước tính: {v.severity_estimate}"]
        if v.lesion_counts:
            vi_counts = [
                f"{self._vi(self._LESION_VI, k)}={v2}"
                for k, v2 in v.lesion_counts.items()
            ]
            parts.append("đếm tổn thương: " + ", ".join(vi_counts))
        if v.skin_regions:
            vi_regions = [self._vi(self._LOCATION_VI, r) for r in v.skin_regions]
            parts.append("vùng: " + ", ".join(vi_regions))
        if v.notes:
            parts.append(f"ghi chú: {v.notes}")
        return "; ".join(parts)

    # Badge hiển thị trong prompt để LLM biết nguồn nào authoritative
    _SOURCE_BADGES: dict[str, str] = {
        "nice_guideline":    "[NICE Guideline]",
        "aad_guideline":     "[AAD Guideline]",
        "jid_paper":         "[JID Paper]",
        "pubmed_review":     "[PubMed Review]",
        "clinical_textbook": "[Textbook]",
    }

    def _context_block(self, retrieval: RetrievalOutput | None, max_chars: int = 6000) -> str:
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
            header = (
                f"[Nguon {i}]{badge_str} {title} | {source}\n"
                f"chunk_ref={c.chunk_id}\n"
            )
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

    # Mapping thuật ngữ EN → tên Việt để truyền vào prompt
    _LESION_VI: dict[str, str] = {
        "blackhead":      "mụn đầu đen",
        "whitehead":      "mụn đầu trắng",
        "comedone":       "mụn nhân/mụn cám",
        "closed_comedone":"mụn đầu trắng/mụn ẩn",
        "papule":         "mụn viêm đỏ (sẩn viêm)",
        "pustule":        "mụn mủ",
        "nodule":         "mụn bọc cứng",
        "cyst":           "mụn nang",
        "scar":           "sẹo mụn",
        "post_inflammatory_hyperpigmentation": "thâm sau mụn (PIH)",
        "other":          "tổn thương khác",
    }
    _LOCATION_VI: dict[str, str] = {
        "forehead":     "trán",
        "cheeks":       "má",
        "chin":         "cằm",
        "jawline":      "quai hàm",
        "nose":         "mũi",
        "around_mouth": "quanh miệng",
        "back":         "lưng",
        "chest":        "ngực",
        "shoulders":    "vai",
        "neck":         "cổ",
        "t_zone":       "vùng chữ T",
        "other":        "vùng khác",
    }
    _INFLAMMATION_VI: dict[str, str] = {
        "mild":     "nhẹ",
        "moderate": "vừa",
        "severe":   "nặng",
        "unknown":  "chưa rõ",
    }
    _SKIN_TYPE_VI: dict[str, str] = {
        "dry": "da khô",
        "oily": "da dầu",
        "combination": "da hỗn hợp",
        "sensitive": "da nhạy cảm",
        "normal": "da thường",
    }
    _HORMONAL_VI: dict[str, str] = {
        "menstrual_cycle": "theo chu kỳ kinh nguyệt",
        "pcos":            "hội chứng buồng trứng đa nang (PCOS)",
        "stress":          "do stress/căng thẳng",
        "diet":            "do chế độ ăn",
        "pregnancy":       "khi mang thai",
        "postpartum":      "sau sinh/cho con bú",
        "puberty":         "tuổi dậy thì",
    }

    @classmethod
    def _vi(cls, mapping: dict[str, str], key: str) -> str:
        return mapping.get(str(key), str(key))

    def _known_facts_summary(self, user: UserInput) -> str:
        """Tóm tắt ngắn những gì đã biết về user (từ turn này + session fold).

        Dùng để inject rõ vào prompt dưới dạng 'Thông tin đã biết' —
        giúp LLM không hỏi lại những gì đã có.
        """
        ctx = user.context
        cl = user.clinical

        # Tách provenance: 'stated' = user nêu rõ (số/cụm tường minh, khó suy sai);
        # 'inferred' = nhãn lâm sàng do rule/regex suy ra (có thể sai). Không gộp
        # chung để tránh biến fact suy luận thành "đã xác nhận" authoritative.
        stated: list[str] = []
        inferred: list[str] = []

        if ctx.age is not None:
            stated.append(f"tuổi: {ctx.age}")
        if ctx.sex:
            stated.append(f"giới tính: {'nam' if ctx.sex == 'male' else 'nữ' if ctx.sex == 'female' else ctx.sex}")
        if ctx.duration_weeks is not None:
            stated.append(f"thời gian bị: ~{ctx.duration_weeks} tuần")
        if ctx.is_pregnant:
            stated.append("đang mang thai: CÓ")
        if ctx.is_breastfeeding:
            stated.append("đang cho con bú: CÓ")
        if ctx.medications:
            stated.append("thuốc đang dùng: " + ", ".join(ctx.medications))
        if ctx.current_products:
            stated.append("sản phẩm đang dùng: " + ", ".join(ctx.current_products))
        if ctx.allergies:
            stated.append("dị ứng: " + ", ".join(ctx.allergies))

        # loại da + nhãn lâm sàng là suy luận từ pattern → nhóm 'cần xác nhận'.
        if ctx.skin_type:
            inferred.append(f"loại da: {self._vi(self._SKIN_TYPE_VI, ctx.skin_type)}")
        if cl:
            if cl.lesion_types:
                vi_lesions = [self._vi(self._LESION_VI, x) for x in cl.lesion_types]
                inferred.append("loại mụn: " + ", ".join(vi_lesions))
            if cl.lesion_distribution:
                vi_locs = [self._vi(self._LOCATION_VI, x) for x in cl.lesion_distribution]
                inferred.append("vị trí mụn: " + ", ".join(vi_locs))
            if cl.inflammation_level and cl.inflammation_level not in ("unknown", "none"):
                inferred.append("mức viêm: " + self._vi(self._INFLAMMATION_VI, cl.inflammation_level))
            if cl.hormonal_factors:
                vi_horm = [self._vi(self._HORMONAL_VI, x) for x in cl.hormonal_factors]
                inferred.append("yếu tố khởi phát: " + ", ".join(vi_horm))
            if cl.canonical_ingredients:
                inferred.append("hoạt chất chuẩn hóa: " + ", ".join(cl.canonical_ingredients))
            if cl.usage_frequencies:
                inferred.append("tần suất dùng: " + ", ".join(cl.usage_frequencies))
            if cl.concentrations:
                conc = ", ".join(f"{float(x):.8g}" for x in cl.concentrations)
                inferred.append("nồng độ: " + conc)
            if cl.red_flags_input:
                inferred.append("dấu hiệu cần chú ý: " + ", ".join(cl.red_flags_input))
            if cl.treatment_goals:
                inferred.append("mong muốn: " + ", ".join(cl.treatment_goals))

        segments: list[str] = []
        if stated:
            segments.append("[user đã nêu] " + "; ".join(stated))
        if inferred:
            segments.append(
                "[hệ thống suy luận, hãy xác nhận nếu mâu thuẫn với lời user] "
                + "; ".join(inferred)
            )
        return " | ".join(segments)

    def _clinical_summary(self, user: UserInput) -> str:
        c = user.clinical
        if not c:
            return "không có dữ liệu lâm sàng có cấu trúc"
        parts: list[str] = []
        if c.lesion_types:
            vi_lesions = [self._vi(self._LESION_VI, x) for x in c.lesion_types]
            parts.append("loại tổn thương: " + ", ".join(vi_lesions))
        if c.lesion_distribution:
            vi_locs = [self._vi(self._LOCATION_VI, x) for x in c.lesion_distribution]
            parts.append("phân bố: " + ", ".join(vi_locs))
        if c.inflammation_level:
            parts.append("mức độ viêm: " + self._vi(self._INFLAMMATION_VI, c.inflammation_level))
        if c.scarring_signs:
            parts.append("dấu hiệu sẹo/thâm: " + ", ".join(c.scarring_signs))
        if c.medication_history:
            parts.append("tiền sử dùng thuốc: " + ", ".join(c.medication_history))
        if c.hormonal_factors:
            vi_horm = [self._vi(self._HORMONAL_VI, x) for x in c.hormonal_factors]
            parts.append("yếu tố nội tiết/khởi phát: " + ", ".join(vi_horm))
        if c.skincare_products:
            parts.append("sản phẩm chăm sóc da: " + ", ".join(c.skincare_products))
        if c.canonical_ingredients:
            parts.append("hoạt chất chuẩn hóa: " + ", ".join(c.canonical_ingredients))
        if c.usage_frequencies:
            parts.append("tần suất dùng: " + ", ".join(c.usage_frequencies))
        if c.concentrations:
            conc = ", ".join(f"{float(x):.8g}" for x in c.concentrations)
            parts.append("nồng độ: " + conc)
        if c.treatment_goals:
            parts.append("mong muốn điều trị: " + ", ".join(c.treatment_goals))
        if c.red_flags_input:
            parts.append("dấu hiệu cần chú ý: " + ", ".join(c.red_flags_input))
        return "; ".join(parts) if parts else "dữ liệu lâm sàng trống"

    def _clinical_plan_summary(self, plan: ClinicalQueryPlan | None) -> str:
        """Summary ngắn gọn của clinical plan (~1 dòng) thay vì dump JSON đầy đủ.

        model_dump_json() có thể dài 500-800 ký tự, ăn token budget của KB chunks.
        Chỉ giữ các field thực sự cần thiết cho LLM ra quyết định.
        Tên thuật ngữ được dịch sang tiếng Việt để LLM không bắt chước dùng EN.
        """
        if not plan:
            return "chưa có thông tin lâm sàng"
        c = plan.normalized_case
        parts: list[str] = []
        if c.lesion_types:
            vi_lesions = [self._vi(self._LESION_VI, x) for x in c.lesion_types]
            parts.append("loại tổn thương: " + ", ".join(vi_lesions))
        if c.distribution:
            vi_locs = [self._vi(self._LOCATION_VI, x) for x in c.distribution]
            parts.append("vị trí: " + ", ".join(vi_locs))
        if c.inflammation_level and c.inflammation_level != "unknown":
            parts.append("mức viêm: " + self._vi(self._INFLAMMATION_VI, c.inflammation_level))
        if c.scarring_signs:
            parts.append("sẹo/thâm: " + ", ".join(c.scarring_signs))
        if c.hormonal_factors:
            vi_horm = [self._vi(self._HORMONAL_VI, x) for x in c.hormonal_factors]
            parts.append("nội tiết: " + ", ".join(vi_horm))
        if c.canonical_ingredients:
            parts.append("hoạt chất chuẩn hóa: " + ", ".join(c.canonical_ingredients))
        if c.usage_frequencies:
            parts.append("tần suất dùng: " + ", ".join(c.usage_frequencies))
        if c.concentrations:
            conc = ", ".join(f"{float(x):.8g}" for x in c.concentrations)
            parts.append("nồng độ: " + conc)
        if c.red_flags:
            parts.append("dấu hiệu nghiêm trọng: " + ", ".join(c.red_flags))
        if plan.missing_info:
            parts.append("thông tin còn thiếu: " + ", ".join(plan.missing_info))
        return "; ".join(parts) if parts else "không có dữ liệu cấu trúc"

    def build(
        self,
        user: UserInput,
        retrieval: RetrievalOutput | None,
        template: str = "hybrid_user.j2",
        detected_language: str = "unknown",
        query_vi: str = "",
        max_context_chars: int = 6000,
        clinical_plan: ClinicalQueryPlan | None = None,
        history: list[ConversationTurn] | None = None,
        route_metadata: dict | None = None,
        completeness_hint: str | None = None,
        confirmed_profile: dict | None = None,
        require_citations: bool = True,
    ) -> tuple[str, str]:
        # Modelfile SYSTEM là nguồn sự thật DUY NHẤT cho hành vi model
        # (use_modelfile_system=True → backend bỏ system message). Repo không gửi
        # system prompt; user template chỉ mang dữ liệu + format contract theo endpoint.
        sys_p = ""
        has_kb = retrieval is not None and bool(retrieval.chunks)
        safe_description = _escape_jinja(_sanitize_user_description(user.description))
        safe_allergies = _escape_jinja(", ".join(user.context.allergies) or "không")
        safe_medications = _escape_jinja(", ".join(user.context.medications) or "không")
        safe_vision = _escape_jinja(self._vision_summary(user.vision))
        safe_qv = _escape_jinja(query_vi)
        safe_context = _escape_jinja(self._context_block(retrieval, max_chars=max_context_chars))
        safe_history = _escape_jinja(format_history_block(
            sanitize_history_turns(history or []),
            keep_anchor=False,
            max_turns=2,
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
        # Route guidance: chỉ truyền những chỉ dẫn ngữ cảnh ngắn, không dump metadata nội bộ
        safe_route_guidance = _escape_jinja(_route_guidance(route_metadata))
        query_subject = str((route_metadata or {}).get("query_subject") or "self")
        # Completeness hint: hướng dẫn LLM hỏi thêm thay vì gate cứng
        safe_completeness_hint = _escape_jinja(completeness_hint or "")
        safe_known_facts = _escape_jinja(self._known_facts_summary(user))

        user_p = self.env.get_template(template).render(
            description=safe_description,
            age=user.context.age,
            sex=user.context.sex,
            skin_type=user.context.skin_type,
            is_pregnant=user.context.is_pregnant,
            is_breastfeeding=user.context.is_breastfeeding,
            allergies=safe_allergies,
            medications=safe_medications,
            duration_weeks=user.context.duration_weeks,
            vision_summary=safe_vision,
            detected_language=detected_language,
            query_vi=safe_qv,
            known_facts=safe_known_facts,
            normalized_case_plan="",
            retrieved_context=safe_context,
            history_block=safe_history,
            route_metadata=safe_route_guidance,  # backward-compat: templates dùng biến này
            query_subject=query_subject,
            completeness_hint=safe_completeness_hint,
            has_retrieved_context=has_kb,
            confirmed_safety_facts=safe_confirmed_safety,
            require_citations=require_citations,
        )
        return sys_p, user_p
