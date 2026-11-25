"""Config v2 — kế thừa `roledata.Config`, chỉ đổi quota, path và nguồn template.

Quota mới dịch ~340 bản ghi từ nhóm vai/giọng (R1, R3, R4, R5, R6, R7, B2) sang
nhóm mang nội dung (B1, B3, B4, B5, K1, R2, R10). Căn cứ: run_full_v3_2 cho thấy
generator KHÔNG phải nút thắt an toàn (đổi generator sửa 0/8 ca từ chối) nhưng
LÀ nút thắt độ phủ (`missing_content` 2.24/3, `incorrect_content` chỉ 0.30/3).

Band độ dài nằm ở `taxonomy.yaml`, neo theo chính eval: chia arm generator-mạnh
theo độ dài trên nhóm câu tư vấn thì bậc nhảy nằm giữa ~900 và ~1.300 ký tự
(answer_quality 2.89 -> 3.63, missing 2.11 -> 1.26); trên ~1.700 không được thêm
gì mà `incorrect_content` bò lên 0.16 -> 0.32.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..roledata.config import Config as ConfigV1

MODULE_ROOT = Path(__file__).resolve().parent
ROLEDATA_V1_ROOT = MODULE_ROOT.parent / "roledata"
PROJECT_ROOT = MODULE_ROOT.parents[2]
FULL_TARGET = 3_500

# Anchor v4. Bản cũ (model/legacy, sha 722281f0) là bản Ollama đang phục vụ và là
# bản v2 đã sinh 2.763 mẫu; nó bị thay vì GENERATOR_ROOT_CAUSE.md chỉ ra chính nó
# gây ba trong bốn lỗi ngốn ngân sách câu trả lời (28% mở bằng câu đồng cảm, 22%
# đóng bằng disclaimer, 29% kết bằng câu hỏi ngược) và không có một chữ nào về độ
# dài hay cấu trúc — 0/145 câu trả lời có gạch đầu dòng. Lý do từng thay đổi ghi
# trong header của model/generator/Modelfile.
_PROMPTS_V4 = PROJECT_ROOT / "model" / "generator" / "prompts"
DEFAULT_ANCHOR_PATH = PROJECT_ROOT / "model" / "generator" / "Modelfile"
DEFAULT_CANONICAL_PATH = _PROMPTS_V4 / "system_prompt.v4.a.txt"
EXPECTED_ANCHOR_SHA256 = "5421f2079acafe303f635ebca33bb5204ab5efde5a0f1324ad10a1cdf73fb5b5"

# Ba biến thể MÃ HOÁ CÙNG MỘT BỘ LUẬT, khác cách hành văn và thứ tự mục.
#
# Vì sao cần: toàn bộ 48.705 dòng SFT cũ có ĐÚNG 1 system prompt, và cả 2.763 mẫu
# v2 cũng vậy (đã kiểm: 1 sha duy nhất). Model học được *chuỗi ký tự* chứ không
# học *luật*, nên lúc phục vụ bằng một prompt khác thì nó lạc — đúng nguyên nhân
# A1 trong GENERATOR_ROOT_CAUSE.md. Rải ba biến thể lúc train là cách mua lại
# quyền sửa system prompt sau khi đã finetune.
#
# A luôn là bản đem đi PHỤC VỤ; B và C chỉ tồn tại trong data train.
ANCHOR_VARIANT_PATHS: tuple[Path, ...] = (
    DEFAULT_CANONICAL_PATH,
    _PROMPTS_V4 / "system_prompt.v4.b.txt",
    _PROMPTS_V4 / "system_prompt.v4.c.txt",
)

# Ưu tiên nguồn cho case B*/K1, xếp từ tin cậy nhất. Tầng guideline chỉ có 776
# chunk dùng được nhưng B*+K1 cần 1.320 mẫu, nên lấy hết tầng guideline trước rồi
# mới bù xuống — "ưu tiên", không phải "chỉ". Bù để tránh một chunk phải gánh
# nhiều mẫu, vì trùng nguồn kéo theo trùng câu chữ và gate `phrase_frequency` loại.
KNOWLEDGE_SOURCE_PRIORITY: tuple[str, ...] = (
    "nice_guideline",
    "aad_guideline",
    "clinical_textbook",
    "pubmed_review",
    "en_medical_site",
    "vi_medical_site",
)

# Quota vòng 2. Đổi lớn nhất: nhóm cần tài liệu (B*/K1) từ 1.570 xuống 660.
#
# Căn cứ là ba số trong run_full_v3_2/ASSESSMENT.md, không phải cảm tính:
#   RRR − RNR = 0.000  — tắt hẳn RAG không làm câu trả lời tệ đi ở bất kỳ mặt nào;
#   RRO − RNO = −0.16  — NGAY CẢ `gpt-5.6-terra`, model không hề có train/serve
#                        mismatch, cũng không khá hơn khi được đưa tài liệu;
#   ROR − RRR = +0.25  — bơm thẳng chunk vàng vào thì context_sufficiency nhảy
#                        3.20 → 4.47 nhưng answer_quality chỉ nhích, groundedness
#                        còn TỤT −0.45.
# Ba số đó nói vấn đề nằm ở NỘI DUNG KB, không nằm ở chỗ model biết đọc tài liệu
# hay không. Bỏ 45% ngân sách sinh data để dạy một kỹ năng có payoff chưa đo được
# là đắt. 660 mẫu vẫn đủ giữ hành vi bám nguồn và hành vi từ chối khi nguồn thiếu.
#
# Phần dôi ra (910 mẫu) dồn hết sang nhóm KHÔNG cần tài liệu, nơi `missing_content`
# 2.24/3 là thứ đo được và sửa được. Nhóm vai/ranh giới (R1, R6, R7, R8) giữ
# nguyên: eval cho thấy đổi generator sửa 0/8 ca từ chối, tức nó đã bão hoà —
# thêm data ở đó không mua thêm gì, mà bớt thì mất cái đang chạy tốt.
#
# Mọi con số phải chia hết cho 10: `planned_input_style` rải augmentation theo
# ordinal % 10 ∈ {3,6,9}, lệch bội số 10 thì tỉ lệ 30% không ra đúng.
CASE_TYPE_TARGETS: dict[str, int] = {
    # --- nhóm vai/ranh giới: giữ nguyên, đã bão hoà ---
    "R7_conversation_glue": 120,
    "R8_meta_jailbreak": 150,
    "R1_identity": 150,
    "R6_role_boundary": 220,
    # --- nhóm cần tài liệu: 1.570 -> 660 ---
    "K1_knowledge_anchor": 250,   # 620
    "B1_grounded_role": 180,      # 470
    "B2_missing_answer": 90,      # 170
    "B3_irrelevant_chunk": 60,    # 150
    "B4_conflicting_docs": 40,    # 80
    "B5_depth_anchor": 40,        # 80  -> 20 cặp
    # --- nhóm suy luận, không cần tài liệu: +910 ---
    "R2_depth_adaptation": 620,   # 350
    "R10_special_population": 410,  # 190
    "R3_nonjudgment": 340,        # 200
    "R5_natural_clarification": 330,  # 170
    "R4_measured_empathy": 260,   # 180 — tăng vừa phải: yield cũ chỉ 8%, không
                                  # gian ca "buồn vì mụn" hẹp, đẩy cao chỉ đốt tiền
    "R9_multiturn": 240,          # 200
}

if sum(CASE_TYPE_TARGETS.values()) != FULL_TARGET:  # pragma: no cover - import invariant
    raise RuntimeError("CASE_TYPE_TARGETS v2 phải cộng đúng FULL_TARGET")


def compute_budget(total: int) -> dict[str, int]:
    """Chia `total` theo tỉ lệ quota v2 bằng largest remainder (deterministic).

    Cùng thuật toán v1 nhưng đọc bảng quota v2; v1 khoá bảng ở module-level nên
    không truyền vào được. 15 dòng lặp lại rẻ hơn là mở seam trong v1.
    """
    if total < 0:
        raise ValueError("total must be non-negative")
    if total == 0:
        return {case: 0 for case in CASE_TYPE_TARGETS}

    exact = {case: total * target / FULL_TARGET for case, target in CASE_TYPE_TARGETS.items()}
    budget = {case: int(value) for case, value in exact.items()}
    remaining = total - sum(budget.values())
    order = {case: index for index, case in enumerate(CASE_TYPE_TARGETS)}
    ranked = sorted(CASE_TYPE_TARGETS, key=lambda case: (-(exact[case] - budget[case]), order[case]))
    for case in ranked[:remaining]:
        budget[case] += 1
    return budget


# Provider mặc định của v2. v1 mặc định OpenAI + gpt-4o-mini và đã sinh toàn bộ
# 3.465 mẫu bằng nó — đó là trần chất lượng của dataset cũ. Đổi sang DeepSeek:
# rẻ hơn cho job này ($2.19 vs $2.92 trên 11,8M token vào / 1,93M ra), mạnh hơn
# ở tiếng Việt, và concurrency 2.500 thay vì phải xếp hàng.
DEFAULT_PROVIDER = "deepseek"

# Giá mặc định theo provider (USD / 1M token), tháng 8/2026. Env vẫn ghi đè được.
PROVIDER_DEFAULTS: dict[str, dict[str, object]] = {
    "deepseek": {
        "key_env": "DEEPSEEK_API_KEY",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "model_env": "DEEPSEEK_MODEL",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "input_price": 0.14,
        "output_price": 0.28,
    },
    "openai": {
        "key_env": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_BASE_URL",
        "model_env": "OPENAI_MODEL",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "input_price": 0.15,
        "output_price": 0.60,
    },
}


def _v1_default(field_name: str):
    """Giá trị mặc định của một field trong Config v1.

    KHÔNG đọc bằng `ConfigV1.<field>`: v1 là `dataclass(slots=True)` nên thuộc tính
    class là slot descriptor, không phải default — so sánh với nó luôn False và
    mọi override ở đây sẽ chết im lặng.
    """
    return ConfigV1.__dataclass_fields__[field_name].default


@dataclass(slots=True)
class Config(ConfigV1):
    """Config v1 với module_root/output trỏ vào roledatav2.

    `prompt_path()` là seam mới: template nào có trong `roledatav2/prompts` thì
    dùng bản v2, không có thì rơi về `roledata/prompts`. Nhờ vậy chỉ phải viết
    lại template thực sự đổi hành vi, phần còn lại dùng chung với v1.
    """

    provider: str = DEFAULT_PROVIDER

    def __post_init__(self) -> None:
        # Chụp lại TRƯỚC khi v1.__post_init__ điền từ env, để phân biệt "caller
        # truyền thẳng vào" với "lấy mặc định" — cái đầu phải thắng bảng provider.
        explicit = (self.api_key, self.base_url, self.model)
        self.module_root = MODULE_ROOT
        # Gọi tường minh thay vì super(): dataclass(slots=True) tạo lại class nên
        # super() không tham số trong thân class con không trỏ đúng chỗ.
        ConfigV1.__post_init__(self)
        # Giọng không đổi giữa v1 và v2 -> dùng chung style guide.
        self.style_guide_path = ROLEDATA_V1_ROOT / "style_guide.md"
        # v1 mặc định trỏ `model/Modelfile` + `model/system_prompt.canonical.txt`,
        # nhưng hai file đó đã bị dời vào `model/legacy/` (v1 test_anchor đang đỏ
        # vì lý do này). Bản legacy chính là system prompt mà Ollama đang phục vụ
        # trong run_full_v3_2 — sha 722281f002ce584e — nên train và serve khớp nhau.
        if self.anchor_path == self.project_root / "model" / "Modelfile":
            self.anchor_path = DEFAULT_ANCHOR_PATH
        if self.canonical_path == self.project_root / "model" / "system_prompt.canonical.txt":
            self.canonical_path = DEFAULT_CANONICAL_PATH
        # `LLMData/` và `evaluation/` đã bị dời vào `research/` ở đợt dọn thư mục
        # (commit 7376dff, root 20 -> 10) nhưng mặc định của v1 vẫn trỏ vào root.
        #
        # `knowledge_source_dir` sai thì `validate()` báo và dừng — thấy ngay.
        # `evaluation_datasets_dir` sai thì KHÔNG ai báo: `_contamination_stats`
        # lặng lẽ trả về 0 câu eval, tức cổng chống trùng dữ liệu train/eval TẮT
        # mà log vẫn in "Contamination index ready". Đó mới là cái nguy hiểm.
        if self.knowledge_source_dir == self.project_root / "LLMData" / "chunk_qa":
            self.knowledge_source_dir = MODULE_ROOT.parents[1] / "LLMData" / "chunk_qa"
        if self.evaluation_datasets_dir == self.project_root / "evaluation" / "datasets":
            self.evaluation_datasets_dir = MODULE_ROOT.parents[1] / "evaluation" / "datasets"
        # v1 để 1.200 token ra vì target của nó chỉ ~400 ký tự. v2 nhắm 1.100-1.600
        # ký tự tiếng Việt + câu hỏi + 3 points + cú pháp JSON; tiếng Việt lại tốn
        # token hơn tiếng Anh. 1.200 sẽ CẮT GIỮA CHỪNG -> JSON hỏng -> reject vòng
        # lặp. Đây đúng là kiểu hỏng đã thấy khi thử kimi-k3-free.
        if self.max_output_tokens == _v1_default("max_output_tokens"):
            self.max_output_tokens = 3_000
        if self.request_timeout_s == _v1_default("request_timeout_s"):
            self.request_timeout_s = 180.0
        # Trần lặp cụm phải TỈ LỆ với kích thước tập, không phải hằng số.
        #
        # v1 để 8 lần trên toàn corpus. Đo trên 186 mẫu vừa sinh, các 14-gram
        # chạm trần đều là NỘI DUNG BẮT BUỘC:
        #   8x "thông tin này chỉ mang tính tham khảo không thay thế chẩn đoán y"
        #   8x "đi khám bác sĩ da liễu để được đánh giá và điều trị phù"
        # Anchor BẮT phải có disclaimer và câu khuyên đi khám, nên gate đang phạt
        # đúng hành vi nó muốn dạy. Ngoại suy tuyến tính: ở 3.500 mẫu những cụm
        # này cần xuất hiện ~150 lần, mà trần là 8 -> `phrase_frequency` quay lại
        # thành lý do loại áp đảo, đúng như vòng 1 (4.851/7.650 = 63%).
        #
        # Trần theo tỉ lệ (5% số mẫu) vẫn chặn được cụm thân bài lặp thật sự —
        # một khuôn câu tư vấn dùng cho 20% dataset vẫn bị bắt — nhưng không phạt
        # câu bắt buộc. `ponytail:` nếu sau này cần phân biệt tinh hơn thì miễn
        # trừ theo danh sách cụm bắt buộc, đắt hơn và chưa chứng minh là cần.
        if self.phrase_max_occurrences == _v1_default("phrase_max_occurrences"):
            self.phrase_max_occurrences = max(8, FULL_TARGET // 20)
        self._apply_provider(*explicit)

    def _apply_provider(
        self,
        explicit_api_key: str | None,
        explicit_base_url: str | None,
        explicit_model: str | None,
    ) -> None:
        """Chọn provider. MẶC ĐỊNH `deepseek` + `deepseek-v4-flash`.

        Đổi mặc định so với v1 (OpenAI + gpt-4o-mini) vì hai lý do đo được:
        v1 sinh toàn bộ 3.465 mẫu bằng `gpt-4o-mini` và đó là trần chất lượng của
        dataset; còn `deepseek-v4-flash` rẻ hơn cho job này ($2.19 so với $2.92
        cho 11,8M token vào / 1,93M ra) mà mạnh hơn rõ ở tiếng Việt.

        KHÔNG ghi đè `OPENAI_*`: `.env` của repo dùng `OPENAI_API_KEY` cho judge
        provider `openai` (`evaluation/judges/clients.py`). Nhét khoá DeepSeek vào
        đó là hỏng nó. Khoá DeepSeek đã có sẵn ở `DEEPSEEK_API_KEY` — 8 module
        khác trong repo đang đọc đúng tên đó.

        Quay lại OpenAI: đặt `ROLEDATA_PROVIDER=openai` trong `.env`.
        """
        values = dict(self._env_values or {})
        name = str(values.get("ROLEDATA_PROVIDER", DEFAULT_PROVIDER)).strip().lower()
        if name not in PROVIDER_DEFAULTS:
            raise ValueError(
                f"ROLEDATA_PROVIDER={name!r} không hợp lệ; chọn {sorted(PROVIDER_DEFAULTS)}"
            )
        spec = PROVIDER_DEFAULTS[name]
        self.provider = name

        # Constructor arg thắng env (test và caller tin cậy truyền thẳng vào).
        if explicit_api_key is None:
            # KHÔNG `or self.api_key`: v1.__post_init__ vừa nhét OPENAI_API_KEY vào
            # đó, nên fallback sẽ lặng lẽ gửi khoá OpenAI tới endpoint DeepSeek.
            # Thiếu khoá thì để None và `validate()` báo — im lặng ở đây tệ hơn.
            self.api_key = values.get(str(spec["key_env"]))
        if explicit_base_url is None:
            self.base_url = values.get(str(spec["base_url_env"])) or str(spec["base_url"])
        if explicit_model is None:
            self.model = values.get(str(spec["model_env"])) or str(spec["model"])
        # Giá: env riêng thắng, không có thì lấy bảng giá của provider.
        if not values.get("OPENAI_INPUT_PRICE_PER_MILLION"):
            self.input_price_per_million = float(spec["input_price"])
        if not values.get("OPENAI_OUTPUT_PRICE_PER_MILLION"):
            self.output_price_per_million = float(spec["output_price"])

    def validate(self) -> list[str]:
        """Như v1, nhưng báo ĐÚNG TÊN biến env của provider đang chọn.

        v1 luôn nói "OPENAI_API_KEY is missing" — với provider deepseek thì lời
        khuyên đó dẫn người ta đi sửa nhầm biến.
        """
        # Gọi tường minh: `dataclass(slots=True)` tạo lại class nên `super()`
        # không tham số trong thân class con raise TypeError. Cùng bẫy với
        # __post_init__ ở trên.
        problems = ConfigV1.validate(self)
        key_env = str(PROVIDER_DEFAULTS[self.provider]["key_env"])
        return [
            f"Thiếu {key_env} (provider={self.provider}); đặt trong .env hoặc environment."
            if "OPENAI_API_KEY is missing" in problem
            else problem
            for problem in problems
        ]

    @property
    def skeleton_path(self) -> Path:
        """Sườn do phase 1 sinh: lời người dùng + ý mong đợi, chưa có câu trả lời.

        Đây là artifact ĐƯỢC ĐÔNG LẠNH giữa hai phase. Giá trị của nó không chỉ là
        tách chi phí: cùng một bộ sườn đem sinh câu trả lời bằng hai teacher khác
        nhau thì so sánh được theo cặp, vì đề bài giống hệt.
        """
        return self.output_dir / "skeletons.jsonl"

    @property
    def skeleton_smoke_path(self) -> Path:
        return self.output_dir / "skeletons.smoke.jsonl"

    @property
    def prompts_dirs(self) -> tuple[Path, Path]:
        """(ưu tiên v2, dự phòng v1)."""
        return (MODULE_ROOT / "prompts", ROLEDATA_V1_ROOT / "prompts")

    def prompt_path(self, case_id: str) -> Path:
        for directory in self.prompts_dirs:
            candidate = directory / f"{case_id}.j2"
            if candidate.is_file():
                return candidate
        raise FileNotFoundError(
            f"Không tìm thấy template {case_id}.j2 trong "
            f"{[str(directory) for directory in self.prompts_dirs]}"
        )
