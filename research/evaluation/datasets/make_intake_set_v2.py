#!/usr/bin/env python3
"""Sinh bộ eval Unified Intake v2 theo quota field và chống trùng dữ liệu.

Script này cố ý đứng riêng khỏi ``make_intake_set.py`` để bộ v1 còn tái lập
được. Nó tái dùng đúng client, prompt builder, record converter, canonical
system prompt và deterministic gates của pipeline ``datagen.intakedata``; phần
khác duy nhất là manifest đặt hàng, chống trùng nguyên văn train/val và cổng
cosine giữa các mẫu eval đã nhận.

Full dataset có 1.500 record:
  * 43 giá trị enum/bool x 30 = 1.290
  * age/duration: 12 khoảng x 10 = 120
  * allergies/current_products/medications: (15 có + 15 không) x 3 = 90

Usage:
    python -m evaluation.datasets.make_intake_set_v2 --dry-run
    python -m evaluation.datasets.make_intake_set_v2 --smoke --yes
    python -m evaluation.datasets.make_intake_set_v2 --yes
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from datagen.intakedata.anchor import anchor_sha256, load_anchor  # noqa: E402
from datagen.intakedata.config import Config, _environment  # noqa: E402
from datagen.intakedata.gates import CorpusGateState, evaluate_record  # noqa: E402
from datagen.intakedata.generator import (  # noqa: E402
    CaseSpec,
    build_gen_prompt,
    synthesize_seed,
    to_record,
    user_turn_hash,
)
from datagen.intakedata.writer import DatasetWriter, iter_jsonl, write_jsonl  # noqa: E402
from evaluation.datasets.make_intake_set import (  # noqa: E402
    DeepSeekGenerator,
    cue_violations,
    dig,
)


TRAIN_PATH = ROOT / "research/datagen/intakedata/output/intake/intake.train.jsonl"
VAL_PATH = ROOT / "research/datagen/intakedata/output/intake/intake.val.jsonl"
OUT_DEFAULT = ROOT / "research/evaluation/datasets/active/intake_eval.v2_1500.jsonl"
SMOKE_OUT_DEFAULT = ROOT / "research/evaluation/datasets/extra/intake_eval.v2_smoke_10.jsonl"
DEFAULT_MODEL = "deepseek-v4-pro"
EMBEDDING_MODEL = "AITeamVN/Vietnamese_Embedding"
MAX_OUTPUT_TOKENS = 8_000
FULL_TOTAL = 1_500


@dataclass(frozen=True)
class Expectation:
    kind: str
    value: Any = None
    minimum: int | None = None
    maximum: int | None = None

    @property
    def label(self) -> str:
        if self.kind == "exact":
            return repr(self.value)
        if self.kind == "range":
            hi = "∞" if self.maximum is None else str(self.maximum)
            return f"[{self.minimum},{hi}]"
        return self.kind


@dataclass(frozen=True)
class Case:
    name: str
    quota: int
    base: str
    path: str
    expectation: Expectation
    behavior: str
    cues: tuple[str, ...] = ()


def exact(value: Any) -> Expectation:
    return Expectation("exact", value=value)


def number_range(minimum: int, maximum: int | None) -> Expectation:
    return Expectation("range", minimum=minimum, maximum=maximum)


NONEMPTY = Expectation("nonempty")
EMPTY = Expectation("empty")


SEX_CUES = {
    "male": ("mình là nam", "em là con trai"),
    "female": ("mình là nữ", "em là con gái"),
    "other": ("giới tính của mình là khác", "mình là người phi nhị nguyên"),
}
SKIN_CUES = {
    "dry": ("da khô",),
    "oily": ("da dầu",),
    "combination": ("da hỗn hợp",),
    "sensitive": ("da nhạy cảm",),
    "normal": ("da thường",),
    "unknown": ("không biết loại da", "chưa rõ da mình thuộc loại nào"),
}
PREGNANT_CUES = {
    True: ("đang mang thai", "thai 14 tuần", "bầu 6 tháng"),
    False: ("không mang thai", "hiện không có bầu"),
}
BREASTFEEDING_CUES = {
    True: ("đang cho con bú", "đang nuôi con bằng sữa mẹ"),
    False: ("không cho con bú", "hiện không nuôi con bằng sữa mẹ"),
}
LESION_CUES = {
    "comedone": ("nhân mụn",),
    "whitehead": ("mụn đầu trắng",),
    "blackhead": ("mụn đầu đen",),
    "closed_comedone": ("mụn ẩn", "nhân kín dưới da"),
    "papule": ("mụn đỏ", "nốt mụn đỏ không có mủ"),
    "pustule": ("mụn mủ",),
    "nodule": ("mụn bọc cứng dưới da",),
    "cyst": ("mụn nang sâu đau",),
    "scar": ("sẹo rỗ do mụn",),
    "post_inflammatory_hyperpigmentation": ("vết thâm sau mụn",),
}
INFLAMMATION_CUES = {
    "none": ("hết mụn rồi chỉ còn vết thâm",),
    "mild": ("mụn đầu đen lác đác ở trán",),
    "moderate": ("mụn đỏ và mụn mủ lan hai má",),
    "severe": ("mụn bọc sâu đau mọc cả ở lưng",),
    "unknown": ("có mụn ở cằm nhưng không rõ dạng hay mức độ",),
}
DISTRIBUTION_CUES = {
    "forehead": ("mụn ở trán",),
    "cheeks": ("mụn ở hai má",),
    "chin": ("mụn ở cằm",),
    "jawline": ("mụn ở quai hàm",),
    "nose": ("mụn ở mũi",),
    "around_mouth": ("mụn quanh miệng",),
    "back": ("mụn ở lưng",),
    "chest": ("mụn ở ngực",),
    "shoulders": ("mụn ở vai",),
    "neck": ("mụn ở cổ",),
    "t_zone": ("mụn ở vùng chữ T",),
}


def _build_cases() -> tuple[Case, ...]:
    cases: list[Case] = [
        Case(
            "intent_advise", 30, "advise_selfreport_simple", "intent", exact("advise"),
            "Người dùng tự kể tình trạng mụn của chính mình và xin lời khuyên.",
        ),
        Case(
            "intent_knowledge_general", 10, "knowledge_general", "intent", exact("knowledge"),
            "Hỏi kiến thức chung về mụn, không tự khai tình trạng cá nhân.",
        ),
        Case(
            "intent_knowledge_product", 10, "knowledge_product_trap", "intent", exact("knowledge"),
            "Hỏi chung về một sản phẩm/hoạt chất, không nói mình đang dùng.",
        ),
        Case(
            "intent_knowledge_compare", 10, "knowledge_ingredient_compare", "intent", exact("knowledge"),
            "So sánh hai hoạt chất ở mức kiến thức, không tự khai đang dùng.",
        ),
        Case(
            "intent_clarify_vague", 10, "clarify_vague", "intent", exact("clarify"),
            "Câu hiện tại quá mơ hồ để tư vấn an toàn.",
        ),
        Case(
            "intent_clarify_followup", 10, "clarify_followup_multiturn", "intent", exact("clarify"),
            "Follow-up ngắn cần lịch sử nhưng hiện tại chưa đủ để đưa lời khuyên mới.",
        ),
        Case(
            "intent_clarify_greeting", 10, "glue_greeting_thanks", "intent", exact("clarify"),
            "Chỉ chào hoặc cảm ơn, không nêu tình trạng mụn.",
        ),
        Case(
            "intent_reject_jailbreak", 10, "reject_jailbreak_meta", "intent", exact("reject"),
            "Yêu cầu bỏ luật, đổi vai hoặc tiết lộ system prompt.",
        ),
        Case(
            "intent_reject_ood", 10, "reject_ood", "intent", exact("reject"),
            "Câu hỏi hoàn toàn ngoài phạm vi da mụn.",
        ),
        Case(
            "intent_reject_rx", 10, "reject_unsafe_rx", "intent", exact("reject"),
            "Đòi kê đơn, liều hoặc phác đồ thuốc để tự dùng.",
        ),
    ]

    for value, cues in SEX_CUES.items():
        cases.append(Case(
            f"sex_{value}", 30, "advise_selfreport_simple", "context.sex", exact(value),
            f"Người dùng nói rõ giới tính; context.sex bắt buộc ánh xạ thành {value!r}.", cues,
        ))
    for value, cues in SKIN_CUES.items():
        cases.append(Case(
            f"skin_{value}", 30, "advise_selfreport_simple", "context.skin_type", exact(value),
            f"Người dùng mô tả loại da; context.skin_type bắt buộc là {value!r}.", cues,
        ))
    for value, cues in PREGNANT_CUES.items():
        cases.append(Case(
            f"pregnant_{str(value).lower()}", 30, "advise_selfreport_simple",
            "context.is_pregnant", exact(value),
            f"Người dùng nói rõ trạng thái thai kỳ; is_pregnant bắt buộc là {value}.", cues,
        ))
    for value, cues in BREASTFEEDING_CUES.items():
        cases.append(Case(
            f"breastfeeding_{str(value).lower()}", 30, "advise_selfreport_simple",
            "context.is_breastfeeding", exact(value),
            f"Người dùng nói rõ trạng thái cho bú; is_breastfeeding bắt buộc là {value}.", cues,
        ))
    for value, cues in LESION_CUES.items():
        cases.append(Case(
            f"lesion_{value}", 30, "advise_selfreport_simple",
            "clinical.lesion_types", exact(value),
            f"Mô tả phải đúng định nghĩa tổn thương {value!r} trong system prompt.", cues,
        ))
    for value, cues in INFLAMMATION_CUES.items():
        cases.append(Case(
            f"inflammation_{value}", 30, "advise_selfreport_simple",
            "clinical.inflammation_level", exact(value),
            f"Mức viêm phải ánh xạ đúng neo IGA thành {value!r}; không tự đếm nốt.", cues,
        ))
    for value, cues in DISTRIBUTION_CUES.items():
        cases.append(Case(
            f"distribution_{value}", 30, "advise_selfreport_simple",
            "clinical.lesion_distribution", exact(value),
            f"Vị trí mụn phải ánh xạ chính xác thành {value!r}.", cues,
        ))

    age_ranges = (
        ("age_0", 0, 0),
        ("age_1_11", 1, 11),
        ("age_12_17", 12, 17),
        ("age_18_24", 18, 24),
        ("age_25_39", 25, 39),
        ("age_40_plus", 40, None),
    )
    duration_ranges = (
        ("duration_0", 0, 0),
        ("duration_1_4", 1, 4),
        ("duration_5_12", 5, 12),
        ("duration_13_26", 13, 26),
        ("duration_27_52", 27, 52),
        ("duration_53_plus", 53, None),
    )
    for name, low, high in age_ranges:
        cases.append(Case(
            name, 10, "advise_selfreport_simple", "context.age", number_range(low, high),
            f"Người dùng nêu tuổi thuộc khoảng {low}..{high if high is not None else '120'}.",
        ))
    for name, low, high in duration_ranges:
        cases.append(Case(
            name, 10, "advise_selfreport_simple", "context.duration_weeks",
            number_range(low, high),
            f"Người dùng nêu thời gian bị mụn quy đổi vào khoảng {low}.."
            f"{high if high is not None else 'không giới hạn'} tuần.",
        ))

    for field in ("allergies", "current_products", "medications"):
        cases.append(Case(
            f"{field}_present", 15, "advise_selfreport_simple", f"context.{field}", NONEMPTY,
            f"Người dùng nêu rõ giá trị đang có của {field}; list này phải khác rỗng.",
        ))
        cases.append(Case(
            f"{field}_negative", 15, "advise_selfreport_simple", f"context.{field}", EMPTY,
            f"Người dùng phủ định hoặc nói đã ngưng; {field} phải là list rỗng.",
        ))
    return tuple(cases)


CASES = _build_cases()
TOTAL = sum(case.quota for case in CASES)
SMOKE_CASE_NAMES = (
    "intent_knowledge_general",
    "intent_clarify_followup",
    "intent_reject_rx",
    "pregnant_true",
    "age_1_11",
    "duration_53_plus",
    "skin_unknown",
    "lesion_cyst",
    "distribution_chest",
    "medications_negative",
)


def current_user_turn(record: Mapping[str, Any]) -> str:
    messages = record.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages[:-1]):
        if isinstance(message, Mapping) and message.get("role") == "user":
            value = message.get("content")
            return value if isinstance(value, str) else ""
    return ""


def satisfies(payload: Mapping[str, Any], case: Case) -> bool:
    value = dig(payload, case.path)
    expected = case.expectation
    if expected.kind == "exact":
        if isinstance(expected.value, bool):
            return value is expected.value
        if isinstance(value, list):
            return expected.value in value
        return value == expected.value
    if expected.kind == "range":
        if isinstance(value, bool) or not isinstance(value, int):
            return False
        return value >= int(expected.minimum or 0) and (
            expected.maximum is None or value <= expected.maximum
        )
    if expected.kind == "nonempty":
        return isinstance(value, list) and bool(value)
    if expected.kind == "empty":
        return isinstance(value, list) and not value
    raise ValueError(f"Unknown expectation kind: {expected.kind}")


def spec_of(case: Case) -> CaseSpec:
    intent = case.expectation.value if case.path == "intent" else "advise"
    return CaseSpec(
        case_type=case.base,
        quota=case.quota,
        style_hint="Người dùng viết tiếng Việt đời thường, tự nhiên, không chép ví dụ.",
        intent_hint=str(intent),
        behavior=case.behavior,
    )


def _choose_number(expectation: Expectation, rng: random.Random, *, upper: int) -> int:
    low = int(expectation.minimum or 0)
    high = expectation.maximum if expectation.maximum is not None else upper
    return rng.randint(low, high)


def _duration_cue(weeks: int) -> str:
    if weeks == 0:
        return "mụn mới nổi hôm nay"
    if weeks % 52 == 0:
        return f"bị mụn {weeks // 52} năm"
    if weeks % 4 == 0 and weeks >= 4:
        return f"bị mụn {weeks // 4} tháng"
    return f"bị mụn {weeks} tuần"


def seed_for_case(case: Case, rng: random.Random) -> dict[str, Any]:
    if case.name == "intent_clarify_followup":
        # Train đã có 180 follow-up dựng từ một bảng stem hữu hạn. Dùng lại bảng
        # đó làm cả 10 smoke candidate vượt cosine 0.75. Vẫn giữ đúng contract
        # history của case cũ, chỉ mở rộng tình huống/cách hỏi để eval độc lập.
        topics = (
            "kem dưỡng ceramide",
            "gel sulfur",
            "sữa rửa mặt dịu nhẹ",
            "kem azelaic acid",
            "gel niacinamide",
            "kem phục hồi không hương liệu",
            "gel benzoyl peroxide",
            "kem dưỡng dạng gel",
            "sữa rửa mặt không tạo bọt",
            "miếng dán mụn hydrocolloid",
        )
        followups = (
            "Dấu hiệu nào mới cho thấy da em thật sự không hợp chứ không chỉ đang làm quen?",
            "Nếu chỉ một bên má khó chịu thì em xử lý riêng bên đó được không?",
            "Em làm ca đêm nên đổi thứ tự routine theo giờ ngủ của em được không?",
            "Lúc đi công tác vài hôm em bỏ qua bước này có ảnh hưởng gì không?",
            "Da em ổn ở nhà nhưng về quê lại rát thì có tính là không hợp không?",
            "Nếu em chỉ dùng cuối tuần thì có còn ý nghĩa không?",
            "Em bôi nhầm thứ tự hôm qua thì hôm nay có cần làm gì khác không?",
            "Lúc phải đeo khẩu trang cả ngày em có nên thay đổi bước này không?",
            "Em không nhớ lần trước cách nhau mấy hôm thì theo dõi kiểu gì?",
            "Nếu vùng cằm hợp mà hai má không hợp thì có thể dùng tách vùng không?",
        )
        return {
            "history_topic": rng.choice(topics),
            "followup": rng.choice(followups),
            "register": rng.choice(("em-bạn", "mình-bạn", "tôi-bạn")),
        }
    if case.path == "intent":
        return synthesize_seed(case.base, rng)

    seed: dict[str, Any] = {
        "register": rng.choice(("em-bạn", "mình-bạn", "tôi-bạn")),
        "include": "lesion",
        "lesion": "papule",
        "required_user_cues": ["mụn đỏ"],
        "eval_target": {"path": case.path, "expect": case.expectation.label},
    }
    path = case.path
    if path == "context.age":
        age = _choose_number(case.expectation, rng, upper=70)
        seed.update(age=age, include="age+lesion")
        seed["required_user_cues"] = [f"{age} tuổi", "mụn đỏ"]
    elif path == "context.duration_weeks":
        weeks = _choose_number(case.expectation, rng, upper=156)
        seed.update(duration_weeks=weeks, include="duration_weeks+lesion")
        seed["required_user_cues"] = [_duration_cue(weeks), "mụn đỏ"]
    elif path == "context.sex":
        cue = rng.choice(case.cues)
        seed.update(sex=case.expectation.value, include="sex+lesion")
        seed["required_user_cues"] = [cue, "mụn đỏ"]
    elif path == "context.skin_type":
        cue = rng.choice(case.cues)
        seed.update(skin_type=case.expectation.value, include="skin_type+lesion")
        seed["required_user_cues"] = [cue, "mụn đỏ"]
    elif path in {"context.is_pregnant", "context.is_breastfeeding"}:
        cue = rng.choice(case.cues)
        key = path.rsplit(".", 1)[-1]
        seed.update({key: case.expectation.value, "include": f"{key}+lesion"})
        seed["required_user_cues"] = [cue, "mụn đỏ"]
    elif path == "clinical.lesion_types":
        cue = rng.choice(case.cues)
        seed.update(lesion=case.expectation.value, include="lesion")
        seed["required_user_cues"] = [cue]
    elif path == "clinical.lesion_distribution":
        cue = rng.choice(case.cues)
        seed.update(distribution=case.expectation.value, include="distribution+lesion")
        seed["required_user_cues"] = [cue, "mụn đỏ"]
    elif path == "clinical.inflammation_level":
        level = str(case.expectation.value)
        cue = rng.choice(case.cues)
        anchors = {
            "none": ("post_inflammatory_hyperpigmentation", "chin"),
            "mild": ("blackhead", "forehead"),
            "moderate": ("pustule", "cheeks"),
            "severe": ("cyst", "back"),
            # Có vị trí để clinical không rỗng, nhưng không gắn loại tổn thương:
            # nếu tự gắn papule thì chính seed đã cung cấp dữ kiện để xếp mức.
            "unknown": (None, "chin"),
        }
        lesion, distribution = anchors[level]
        seed.update(
            distribution=distribution,
            inflammation_level=level,
            include=(
                "lesion+distribution+inflammation_level"
                if lesion is not None
                else "distribution+inflammation_level"
            ),
        )
        if lesion is None:
            seed.pop("lesion", None)
        else:
            seed["lesion"] = lesion
        seed["required_user_cues"] = [cue]
    elif path == "context.allergies":
        if case.expectation.kind == "nonempty":
            allergen = rng.choice(("benzoyl peroxide", "salicylic acid", "hương liệu"))
            seed.update(allergy=allergen, include="allergies+lesion")
            seed["required_user_cues"] = [f"mình dị ứng {allergen}", "mụn đỏ"]
        else:
            seed.update(include="allergies+lesion")
            seed["required_user_cues"] = ["mình không dị ứng salicylic acid", "mụn đỏ"]
    elif path == "context.current_products":
        if case.expectation.kind == "nonempty":
            product = rng.choice(("BHA", "adapalene", "benzoyl peroxide"))
            seed.update(current_product=product, include="current_products+lesion")
            seed["required_user_cues"] = [f"đang bôi {product}", "mụn đỏ"]
        else:
            seed.update(include="current_products+lesion")
            seed["required_user_cues"] = ["đã ngưng bôi BHA", "mụn đỏ"]
    elif path == "context.medications":
        if case.expectation.kind == "nonempty":
            medication = rng.choice(("doxycycline", "isotretinoin", "spironolactone"))
            seed.update(medication=medication, include="medications+lesion")
            seed["required_user_cues"] = [f"đang uống {medication}", "mụn đỏ"]
        else:
            seed.update(include="medications+lesion")
            seed["required_user_cues"] = ["đã ngưng uống doxycycline", "mụn đỏ"]
    else:  # pragma: no cover - manifest exhaustiveness is tested
        raise ValueError(f"No seed builder for {case.name}: {case.path}")
    return seed


def trained_hashes(paths: Sequence[Path]) -> set[str]:
    seen: set[str] = set()
    for path in paths:
        for record in iter_jsonl(path):
            for message in record.get("messages") or ():
                if isinstance(message, Mapping) and message.get("role") == "user":
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        seen.add(user_turn_hash(content))
    return seen


@dataclass
class EvalScore:
    vector: Any
    accepted_max: float


class EvalDeduplicator:
    def __init__(
        self,
        *,
        dedup_threshold: float,
        model_name: str = EMBEDDING_MODEL,
    ) -> None:
        import numpy as np

        src = ROOT / "src"
        if str(src) not in sys.path:
            sys.path.insert(0, str(src))
        from acne_llm.config import settings
        from acne_llm.rag.embedder import Embedder

        self.np = np
        self.dedup_threshold = dedup_threshold
        self.embedder = Embedder(model_name=model_name, device=settings.device, batch_size=64)
        self.accepted_vectors: Any | None = None

    def _normalize(self, vectors: Any) -> Any:
        array = self.np.asarray(vectors, dtype=self.np.float32)
        if array.ndim == 1:
            array = array.reshape(1, -1)
        norms = self.np.linalg.norm(array, axis=1, keepdims=True)
        return array / self.np.clip(norms, 1e-12, None)

    def score(self, query: str) -> EvalScore:
        # embed_passages bật tqdm; gọi nó cho từng câu sẽ spam ba dòng
        # "Batches 0/1, 1/1, 1/1" vào stderr. Raw query path dùng cùng model
        # và cùng normalize nhưng tắt progress bar.
        vector = self._normalize(self.embedder._embed_query_raw(query))[0]
        accepted_max = (
            float((self.accepted_vectors @ vector).max())
            if self.accepted_vectors is not None and len(self.accepted_vectors)
            else 0.0
        )
        return EvalScore(vector, accepted_max)

    def accept(self, vector: Any) -> None:
        row = self.np.asarray(vector, dtype=self.np.float32).reshape(1, -1)
        self.accepted_vectors = (
            row
            if self.accepted_vectors is None
            else self.np.concatenate((self.accepted_vectors, row), axis=0)
        )


@dataclass
class Assessment:
    accepted: bool
    reason: str
    payload: dict[str, Any] | None = None
    scores: EvalScore | None = None
    detail: str = ""


def assess_candidate(
    record: Mapping[str, Any],
    case: Case,
    used_seed: Mapping[str, Any],
    *,
    semantic_filter: Any,
    state: CorpusGateState,
    contaminated: set[str],
    anchor: str,
) -> Assessment:
    try:
        payload = json.loads(str(record["messages"][-1]["content"]))
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        return Assessment(False, "json_invalid", detail=str(exc))
    if not isinstance(payload, dict):
        return Assessment(False, "json_not_object")

    user_turn = current_user_turn(record)
    try:
        scores = semantic_filter.score(user_turn)
    except Exception as exc:  # fail closed: caller stops instead of skipping dedup
        raise RuntimeError(f"Không thể embed ứng viên: {exc}") from exc

    if not satisfies(payload, case):
        return Assessment(False, "quota_value", payload, scores)
    missing = cue_violations(used_seed, user_turn)
    if missing:
        return Assessment(False, "cue_missing", payload, scores, missing[0])
    if user_turn_hash(user_turn) in contaminated:
        return Assessment(False, "exact_train_or_val", payload, scores)
    if state.duplicate_user(user_turn):
        return Assessment(False, "exact_eval", payload, scores)
    result = evaluate_record(dict(record), state, anchor=anchor)
    if not result.passed:
        return Assessment(False, "legacy_gate", payload, scores, ",".join(result.reasons))
    if scores.accepted_max >= semantic_filter.dedup_threshold:
        return Assessment(
            False,
            "eval_cosine",
            payload,
            scores,
            f"{scores.accepted_max:.6f}>={semantic_filter.dedup_threshold:.6f}",
        )
    return Assessment(True, "accepted", payload, scores)


async def _attempt(
    provider: Any,
    case: Case,
    seed: dict[str, Any],
    anchor: str,
) -> tuple[dict[str, Any] | None, dict[str, Any], str | None]:
    try:
        generated = await provider.generate(build_gen_prompt(spec_of(case), seed))
        record = to_record(
            spec_of(case),
            generated,
            anchor,
            source=f"intake_eval_v2:{case.name}",
            seed=seed,
        )
        return record, seed, None
    except Exception as exc:  # provider already performs bounded API retries
        return None, seed, f"provider:{type(exc).__name__}:{str(exc)[:180]}"


def _paths_for(out: Path) -> tuple[Path, Path]:
    partial = out.with_name(f"{out.stem}.partial{out.suffix}")
    audit = out.with_name(f"{out.stem}.audit.jsonl")
    return partial, audit


def _audit_entry(case: str, status: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "case": case,
        "status": status,
        "reason": reason,
        **extra,
    }


def _attempt_offsets(audit_path: Path) -> Counter[str]:
    offsets: Counter[str] = Counter()
    for entry in iter_jsonl(audit_path):
        case = entry.get("case")
        if isinstance(case, str) and entry.get("status") in {"accept", "reject"}:
            offsets[case] += 1
    return offsets


def restore_checkpoint(
    records: list[dict[str, Any]],
    cases: tuple[Case, ...],
    *,
    semantic_filter: Any,
    contaminated: set[str],
    anchor: str,
) -> tuple[CorpusGateState, Counter[str]]:
    by_name = {case.name: case for case in cases}
    state = CorpusGateState(anchor)
    got: Counter[str] = Counter()
    for index, record in enumerate(records, start=1):
        meta = record.get("meta")
        name = meta.get("eval_case") if isinstance(meta, Mapping) else None
        if not isinstance(name, str) or name not in by_name:
            raise ValueError(f"Checkpoint row {index} có eval_case không hợp lệ: {name!r}")
        case = by_name[name]
        if got[name] >= case.quota:
            raise ValueError(f"Checkpoint vượt quota {name}")
        seed = meta.get("seed") if isinstance(meta, Mapping) else {}
        assessment = assess_candidate(
            record,
            case,
            seed if isinstance(seed, Mapping) else {},
            semantic_filter=semantic_filter,
            state=state,
            contaminated=contaminated,
            anchor=anchor,
        )
        if not assessment.accepted or assessment.payload is None or assessment.scores is None:
            raise ValueError(
                f"Checkpoint row {index} không còn hợp lệ: "
                f"{assessment.reason} {assessment.detail}"
            )
        state.accept(record, assessment.payload)
        semantic_filter.accept(assessment.scores.vector)
        got[name] += 1
    return state, got


async def build(
    anchor: str,
    cases: tuple[Case, ...],
    *,
    provider: Any,
    semantic_filter: Any,
    contaminated: set[str],
    out: Path,
    seed: int,
    attempts_factor: int,
    concurrency: int,
    generator_id: str,
) -> tuple[list[dict[str, Any]], Counter[str], Counter[str], bool]:
    partial_path, audit_path = _paths_for(out)
    existing = list(iter_jsonl(partial_path))
    state, got = restore_checkpoint(
        existing,
        cases,
        semantic_filter=semantic_filter,
        contaminated=contaminated,
        anchor=anchor,
    )
    offsets = _attempt_offsets(audit_path)
    rejects: Counter[str] = Counter()

    with DatasetWriter(partial_path, audit_path) as writer:
        for case in cases:
            attempts_left = case.quota * attempts_factor
            while got[case.name] < case.quota and attempts_left > 0:
                missing = case.quota - got[case.name]
                batch = min(concurrency, missing, attempts_left)
                ordinals = [offsets[case.name] + i + 1 for i in range(batch)]
                seeds = [
                    seed_for_case(case, random.Random(f"{seed}:{case.name}:{ordinal}"))
                    for ordinal in ordinals
                ]
                offsets[case.name] += batch
                attempts_left -= batch
                attempts = await asyncio.gather(
                    *(_attempt(provider, case, candidate_seed, anchor) for candidate_seed in seeds)
                )
                for ordinal, (record, used_seed, error) in zip(ordinals, attempts):
                    if got[case.name] >= case.quota:
                        break
                    if error or record is None:
                        reason = error or "provider:unknown"
                        rejects[f"{case.name}:{reason.split(':', 2)[0]}"] += 1
                        writer.audit(_audit_entry(case.name, "reject", reason, ordinal=ordinal))
                        continue
                    assessment = assess_candidate(
                        record,
                        case,
                        used_seed,
                        semantic_filter=semantic_filter,
                        state=state,
                        contaminated=contaminated,
                        anchor=anchor,
                    )
                    if not assessment.accepted or assessment.payload is None or assessment.scores is None:
                        rejects[f"{case.name}:{assessment.reason}"] += 1
                        writer.audit(_audit_entry(
                            case.name,
                            "reject",
                            assessment.reason,
                            ordinal=ordinal,
                            detail=assessment.detail,
                            eval_cosine=(assessment.scores.accepted_max if assessment.scores else None),
                        ))
                        continue

                    meta = record.setdefault("meta", {})
                    meta.update({
                        "eval_case": case.name,
                        "quota_path": case.path,
                        "quota_expectation": case.expectation.label,
                        "generator": generator_id,
                        "embedding_model": EMBEDDING_MODEL,
                        "eval_cosine_max": round(assessment.scores.accepted_max, 6),
                    })
                    if not writer.append(record):
                        rejects[f"{case.name}:duplicate_id"] += 1
                        writer.audit(_audit_entry(case.name, "reject", "duplicate_id", ordinal=ordinal))
                        continue
                    state.accept(record, assessment.payload)
                    semantic_filter.accept(assessment.scores.vector)
                    got[case.name] += 1
                    existing.append(record)
                    writer.audit(_audit_entry(
                        case.name,
                        "accept",
                        "accepted",
                        ordinal=ordinal,
                        record_id=record.get("id"),
                        eval_cosine=round(assessment.scores.accepted_max, 6),
                    ))
                    accepted_user = current_user_turn(record).replace("\n", " ").strip()
                    print(
                        f"    [{len(existing):>4}/{sum(item.quota for item in cases)}] "
                        f"[{case.name}] {accepted_user[:220]}",
                        flush=True,
                    )
            mark = "✓" if got[case.name] == case.quota else "✗"
            print(f"  {mark} {case.name:34}{got[case.name]:>3}/{case.quota}", flush=True)

    complete = all(got[case.name] == case.quota for case in cases)
    records = list(iter_jsonl(partial_path))
    if complete:
        write_jsonl(out, records)
    return records, got, rejects, complete


def build_config(model: str, concurrency: int) -> Config:
    env = _environment(ROOT)
    api_key = env.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("Thiếu DEEPSEEK_API_KEY trong .env hoặc environment")
    return Config(
        api_key=api_key,
        base_url=env.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1",
        model=model,
        concurrency=concurrency,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )


def _selected_cases(smoke: bool) -> tuple[Case, ...]:
    if not smoke:
        return CASES
    by_name = {case.name: case for case in CASES}
    return tuple(replace(by_name[name], quota=1) for name in SMOKE_CASE_NAMES)


def _validate_manifest() -> None:
    assert TOTAL == FULL_TOTAL, (TOTAL, FULL_TOTAL)
    assert len({case.name for case in CASES}) == len(CASES)
    assert "other" not in LESION_CUES and "other" not in DISTRIBUTION_CUES
    fixed = sum(
        case.quota
        for case in CASES
        if case.expectation.kind == "exact"
    )
    opened = TOTAL - fixed
    assert fixed == 1_290, fixed
    assert opened == 210, opened


def main(argv: list[str] | None = None) -> int:
    _validate_manifest()
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="cho phép gọi API có phí")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="10 case đại diện, mỗi case 1 dòng")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--dedup-cosine", type=float, default=0.90)
    parser.add_argument("--attempts-factor", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260807)
    args = parser.parse_args(argv)
    if args.concurrency <= 0 or args.attempts_factor <= 0:
        parser.error("--concurrency và --attempts-factor phải > 0")
    if not 0 <= args.dedup_cosine <= 1:
        parser.error("--dedup-cosine phải nằm trong [0,1]")

    cases = _selected_cases(args.smoke)
    out = args.out or (SMOKE_OUT_DEFAULT if args.smoke else OUT_DEFAULT)
    dry_cfg = Config(api_key="dry-run", model=args.model, max_output_tokens=MAX_OUTPUT_TOKENS)
    anchor = load_anchor(dry_cfg)
    print(f"cases={len(cases)} rows={sum(case.quota for case in cases)}")
    print(f"provider=deepseek model={args.model} max_output_tokens={MAX_OUTPUT_TOKENS}")
    print(f"exact_overlap_guard={TRAIN_PATH},{VAL_PATH}")
    print(f"eval_cosine>={args.dedup_cosine} output={out}")
    print(f"anchor_sha256={anchor_sha256(anchor)}")
    for case in cases:
        print(
            f"  {case.name:34}{case.quota:>3}  {case.path} "
            f"{case.expectation.label}  base={case.base}"
        )
    if args.dry_run:
        return 0
    if not args.yes:
        parser.error("thiếu --yes: lệnh này gọi DeepSeek API và tốn phí")
    for guarded_path in (TRAIN_PATH, VAL_PATH):
        if not guarded_path.is_file():
            raise SystemExit(f"Thiếu dataset cho exact-overlap guard: {guarded_path}")

    print(f"\nNạp {EMBEDDING_MODEL} để dedup nội bộ eval…")
    semantic_filter = EvalDeduplicator(dedup_threshold=args.dedup_cosine)
    contaminated = trained_hashes((TRAIN_PATH, VAL_PATH))
    cfg = build_config(args.model, args.concurrency)
    provider = DeepSeekGenerator(cfg)

    async def run_and_close() -> tuple[
        list[dict[str, Any]], Counter[str], Counter[str], bool
    ]:
        try:
            return await build(
                anchor,
                cases,
                provider=provider,
                semantic_filter=semantic_filter,
                contaminated=contaminated,
                out=out,
                seed=args.seed,
                attempts_factor=args.attempts_factor,
                concurrency=args.concurrency,
                generator_id=f"deepseek:{args.model}",
            )
        finally:
            # AsyncOpenAI/httpx phải được đóng trên đúng event loop đã dùng để
            # gửi request. Tạo asyncio.run() thứ hai gây "Event loop is closed".
            await provider.close()

    records, got, rejects, complete = asyncio.run(run_and_close())

    print(f"\naccepted={len(records)} complete={complete} output={out if complete else _paths_for(out)[0]}")
    if rejects:
        print("rejects:")
        for reason, count in rejects.most_common(12):
            print(f"  {count:>4} {reason}")
    if not complete:
        missing = [f"{case.name}:{got[case.name]}/{case.quota}" for case in cases if got[case.name] < case.quota]
        print("Thiếu quota: " + ", ".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
