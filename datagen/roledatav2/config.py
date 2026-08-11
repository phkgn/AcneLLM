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
PROJECT_ROOT = MODULE_ROOT.parents[1]
FULL_TARGET = 3_500

# Anchor đang được Ollama phục vụ (xác nhận bằng sha256 trong trace của run_full_v3_2).
DEFAULT_ANCHOR_PATH = PROJECT_ROOT / "model" / "legacy" / "Modelfile"
DEFAULT_CANONICAL_PATH = PROJECT_ROOT / "model" / "legacy" / "system_prompt.canonical.txt"
EXPECTED_ANCHOR_SHA256 = "722281f002ce584e2c75994ee66e422e691fea453e4cab74ecb1a285b8749c64"

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

CASE_TYPE_TARGETS: dict[str, int] = {
    # --- nhóm ngắn: hành vi vai/ranh giới, KHÔNG nới độ dài ---
    "R7_conversation_glue": 120,
    "R8_meta_jailbreak": 150,
    "R1_identity": 150,
    "R6_role_boundary": 220,
    "B2_missing_answer": 170,
    "R5_natural_clarification": 170,
    # --- nhóm trung ---
    "R9_multiturn": 200,
    "R4_measured_empathy": 180,
    "R3_nonjudgment": 200,
    # --- nhóm dài: mang nội dung, mục tiêu 1.100-1.600 ---
    "B3_irrelevant_chunk": 150,
    "B5_depth_anchor": 80,
    "B4_conflicting_docs": 80,
    "R10_special_population": 190,
    "R2_depth_adaptation": 350,
    "B1_grounded_role": 470,
    "K1_knowledge_anchor": 620,
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
        # v1 để 1.200 token ra vì target của nó chỉ ~400 ký tự. v2 nhắm 1.100-1.600
        # ký tự tiếng Việt + câu hỏi + 3 points + cú pháp JSON; tiếng Việt lại tốn
        # token hơn tiếng Anh. 1.200 sẽ CẮT GIỮA CHỪNG -> JSON hỏng -> reject vòng
        # lặp. Đây đúng là kiểu hỏng đã thấy khi thử kimi-k3-free.
        if self.max_output_tokens == _v1_default("max_output_tokens"):
            self.max_output_tokens = 3_000
        if self.request_timeout_s == _v1_default("request_timeout_s"):
            self.request_timeout_s = 180.0
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

        KHÔNG ghi đè `OPENAI_*`: `.env` của repo dùng `OPENAI_API_KEY` cho
        `ablation/frontier.py` và judge provider `openai`
        (`evaluation/judges/clients.py`). Nhét khoá DeepSeek vào đó là hỏng cả
        hai. Khoá DeepSeek đã có sẵn ở `DEEPSEEK_API_KEY` — 8 module khác trong
        repo đang đọc đúng tên đó.

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
