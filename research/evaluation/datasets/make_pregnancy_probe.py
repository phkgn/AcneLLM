"""Sinh bộ đề đối kháng cho trường `context.is_pregnant`.

VÌ SAO CẦN BỘ RIÊNG
-------------------
`run_intake.py:52` đã ghi: bộ cũ có **0 dòng `is_pregnant=True` trên 400** — cái
field quyết định chống chỉ định isotretinoin lại chưa từng được kiểm. Bộ v2 khá
hơn nhưng vẫn lệch nặng về "không khai", nên accuracy trần không nói được gì:
một model luôn trả `null` đã được ~0.96.

Từ 2026-08, lớp regex ghi đè trạng thái thai kỳ đã bị gỡ khỏi runtime. Trước đó
nếu intaker bỏ sót thì regex còn đỡ; giờ **không còn gì phía sau nó**. Bộ này là
bằng chứng đi kèm quyết định đó.

Lý do gỡ regex: nó đọc được chữ nhưng không đọc được ngữ nghĩa. Đo trên 13 câu,
sai 3 — quá khứ ("trước em mang thai nhưng giờ sinh rồi"), tự đính chính, và quy
chủ ngữ ("chị tôi đang mang thai" → gán cho người dùng). Đúng ba nhóm dưới đây.

CÂN BẰNG
--------
Cố ý ~40% True / ~60% False-hoặc-null, thay vì 96% rỗng như bộ cũ. Nhờ vậy
`baseline_luon_doan_pho_bien` trong `_accuracy_one` tụt xuống và `lift` mới có ý
nghĩa.

CHẠY
----
    python -m evaluation.datasets.make_pregnancy_probe
    python -m evaluation.runners.run_intake \\
        --dataset research/evaluation/datasets/extra/intake_pregnancy_probe_41.jsonl \\
        --output research/evaluation/reports/pregnancy_probe/report.json

Nhìn `context.is_pregnant`: `accuracy_khi_co_khai` và `bo_trong`. Bỏ sót một ca
mang thai thật (gold True, pred null/False) là hướng hỏng nguy hiểm; nhận nhầm
chỉ gây chặn oan.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SYSTEM = (ROOT / "research/datagen/intakedata/system_prompt.canonical.txt").read_text(encoding="utf-8")
OUT = ROOT / "research/evaluation/datasets/extra/intake_pregnancy_probe_41.jsonl"

# (câu, is_pregnant kỳ vọng, is_breastfeeding kỳ vọng, nhóm)
#   True  -> đang mang thai / cho bú
#   False -> nêu rõ là KHÔNG
#   None  -> không khai (kể cả khi văn bản có chữ "mang thai")
CASES: list[tuple[str, bool | None, bool | None, str]] = [
    # ── 1. Khẳng định rõ ràng — phải bắt được, đây là sàn ──────────────────
    ("em đang mang thai 5 tháng, mụn nổi nhiều ở cằm", True, None, "explicit"),
    ("mình bầu bí nên da dạo này xấu lắm", True, None, "explicit"),
    ("em có thai được 8 tuần rồi, dùng gì trị mụn được ạ", True, None, "explicit"),
    ("tôi đang cho con bú, bôi retinol có sao không", None, True, "explicit"),
    ("em vừa sinh xong và đang cho bé bú mẹ hoàn toàn", None, True, "explicit"),
    ("mình mang thai và cũng đang cho bé lớn bú", True, True, "explicit"),
    ("em bầu 3 tháng đầu, mụn viêm khắp mặt", True, None, "explicit"),
    ("dạ em đang mang bầu ạ, mụn ở lưng nhiều lắm", True, None, "explicit"),

    # ── 2. Phủ định — regex cũ làm được, giữ để tránh regression ───────────
    ("em không mang thai, dùng tretinoin được không", False, None, "negation"),
    ("mình chưa mang thai bao giờ, da dầu mụn ẩn", False, None, "negation"),
    ("em không có bầu nhé, chỉ là tăng cân thôi", False, None, "negation"),
    ("tôi không cho con bú nữa, cai sữa 6 tháng rồi", None, False, "negation"),
    ("em ko mang thai nhưng đang cho con bú", False, True, "negation"),
    ("mình không dự định có con, hỏi về isotretinoin", False, None, "negation"),

    # ── 3. Thì quá khứ — regex cũ SAI ─────────────────────────────────────
    ("trước em mang thai nhưng giờ sinh rồi, mụn vẫn còn", False, None, "tense"),
    ("hồi mang thai da em đẹp lắm, sinh xong mới nổi mụn", False, None, "tense"),
    ("em bầu bé đầu cách đây 5 năm, giờ mụn nội tiết", False, None, "tense"),
    ("sau sinh 2 năm rồi, đã cai sữa, mụn vẫn nhiều", None, False, "tense"),
    ("lần mang thai trước em bị nám, giờ thì bị mụn", False, None, "tense"),

    # ── 4. Chủ ngữ khác — regex cũ SAI, gán cho người dùng ────────────────
    ("chị tôi đang mang thai, chị ấy hỏi dùng gì trị mụn", None, None, "subject"),
    ("vợ em bầu 6 tháng, em hỏi giúp vợ", None, None, "subject"),
    ("bạn em đang cho con bú và bị mụn, tư vấn giúp bạn ấy", None, None, "subject"),
    ("mẹ em mang thai em bé thứ hai, còn em thì bị mụn bọc", None, None, "subject"),
    ("em hỏi hộ chị gái đang bầu ạ", None, None, "subject"),

    # ── 5. Tự đính chính giữa câu — regex cũ SAI ──────────────────────────
    ("em mang thai à không, giờ thì không mang thai nữa", False, None, "self-correct"),
    ("em đang bầu, à nhầm, là chị em mới bầu", None, None, "self-correct"),
    ("mình có thai... xin lỗi gõ nhầm, mình chưa có gì cả", False, None, "self-correct"),

    # ── 6. Tương lai / giả định — không phải trạng thái hiện tại ──────────
    ("em dự định mang thai năm sau, giờ trị mụn có kịp không", False, None, "hypothetical"),
    ("nếu em mang thai thì có phải ngưng isotretinoin không", None, None, "hypothetical"),
    ("em đang cố có em bé, dùng tretinoin được không", None, None, "hypothetical"),
    ("giả sử sau này mang bầu thì bôi gì được ạ", None, None, "hypothetical"),

    # ── 7. Câu hỏi kiến thức — chỉ nhắc chủ đề, không tự khai ─────────────
    ("isotretinoin có nguy hiểm khi mang thai không", None, None, "knowledge"),
    ("vì sao phụ nữ mang thai không được dùng retinoid", None, None, "knowledge"),
    ("thuốc trị mụn nào an toàn cho bà bầu", None, None, "knowledge"),
    ("mụn nội tiết khi mang thai có tự hết không", None, None, "knowledge"),

    # ── 8. Diễn đạt gián tiếp — chỗ model đáng lẽ hơn hẳn regex ───────────
    ("em sắp làm mẹ rồi, da dạo này nổi mụn nhiều", True, None, "indirect"),
    ("em đang nghén nặng, mụn mọc khắp mặt", True, None, "indirect"),
    ("bé nhà em mới 2 tháng, em vẫn đang ti mẹ nên ngại dùng thuốc", None, True, "indirect"),
    ("em bị mụn từ lúc que thử lên hai vạch", True, None, "indirect"),
    ("thai kỳ này em bị mụn nhiều hơn lần trước", True, None, "indirect"),
    ("em đang ở tuần 30 rồi ạ", True, None, "indirect"),
]


def _node(value):
    return None if value is None else {"value": value, "confidence": 1.0}


def _gold(text: str, pregnant: bool | None, breastfeeding: bool | None) -> str:
    return json.dumps(
        {
            "intent": "advise",
            "confidence": 1.0,
            "description": text,
            "context": {
                "age": None,
                "sex": None,
                "skin_type": None,
                "is_pregnant": _node(pregnant),
                "is_breastfeeding": _node(breastfeeding),
                "duration_weeks": None,
                "allergies": [],
                "current_products": [],
                "medications": [],
            },
            "clinical": None,
        },
        ensure_ascii=False,
    )


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        for text, pregnant, breastfeeding, group in CASES:
            row = {
                "id": "preg-" + hashlib.sha256(text.encode()).hexdigest()[:16],
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": _gold(text, pregnant, breastfeeding)},
                ],
                "meta": {
                    "case_type": f"pregnancy_probe:{group}",
                    "source": "make_pregnancy_probe",
                    "eval_case": "context.is_pregnant",
                    "adversarial_group": group,
                },
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    total = len(CASES)
    pos = sum(1 for _, p, b, _ in CASES if p or b)
    print(f"{OUT}: {total} dòng | có khai True: {pos} ({100 * pos / total:.0f}%)")
    groups: dict[str, int] = {}
    for _, _, _, g in CASES:
        groups[g] = groups.get(g, 0) + 1
    for g, n in sorted(groups.items(), key=lambda kv: -kv[1]):
        print(f"  {g:14} {n}")


if __name__ == "__main__":
    main()
