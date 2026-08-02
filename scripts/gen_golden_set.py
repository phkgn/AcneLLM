#!/usr/bin/env python3
"""Sinh golden set tiếng Việt SIÊU ĐA DẠNG bằng DeepSeek cho eval extraction.

Mỗi variant LLM tự sinh câu + ĐÍNH NHÃN luôn (tất cả fields trong ExtractionConfidence),
vì LLM biết nó đang sinh ca gì → nhãn đáng tin hơn nhiều so với sinh câu rồi tự đoán nhãn.

Đa dạng được KIỂM SOÁT: mỗi lô chỉ định trước phong cách (teencode / trang trọng
/ sai chính tả / cụt / dài dòng / không dấu), intent, độ khó, có/không phủ định,
có/không câu hỏi. LLM viết câu khớp các thuộc tính đó.

Chỉ TIẾNG VIỆT. Không phụ thuộc lib ngoài (urllib thuần, giống eval_rag.py).

Usage:
    python scripts/gen_golden_set.py --n 1000 --out data/golden_extraction_gen.jsonl
    # cần DEEPSEEK_API_KEY trong .env hoặc env
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ── Canonical values (PHẢI khớp Literal trong schemas/core.py + clinical.py) ──
# VÀ extraction_confidence.py - ExtractionConfidence dataclass

SKIN_TYPES = ["dry", "oily", "combination", "sensitive", "normal"]
SEX = ["male", "female", "other"]
# "comedone" là variant tiếng Anh của "closed_comedone"
LESIONS = ["comedone", "whitehead", "blackhead", "closed_comedone", "papule",
           "pustule", "nodule", "cyst", "scar",
           "post_inflammatory_hyperpigmentation"]
DISTRIBUTIONS = ["forehead", "cheeks", "chin", "jawline", "nose", "around_mouth",
                 "back", "chest", "shoulders", "neck", "t_zone"]
INFLAMMATION = ["none", "mild", "moderate", "severe", "unknown"]

# Products/Medications - tiếng Anh thường gặp trong skincare
PRODUCTS = ["retinol", "retinoid", "niacinamide", "salicylic acid", "BHA", "AHA",
            "glycolic acid", "lactic acid", "benzoyl peroxide", "adapalene", "tretinoin",
            "azelaic acid", "vitamin c", "hyaluronic acid", "ceramide", "centella",
            "tea tree", "sulfur", "zinc", "clindamycin", "cleanser", "moisturizer",
            "sunscreen", "spf", "toner", "essence", "serum"]

MEDICATIONS = ["isotretinoin", "doxycycline", "minocycline", "spironolactone",
               "thuốc tránh thai", "prednisone", "corticosteroid",
               "antihistamine", "metformin"]

# Allergies - PHẢI có context kích ứng mới được gán
ALLERGIES = ["retinol", "retinoid", "tretinoin", "adapalene", "salicylic_acid",
             "benzoyl_peroxide", "niacinamide", "bha_irritation", "aha_irritation",
             "tea_tree", "clindamycin", "doxycycline", "penicillin", "fragrance",
             "preservative", "sunscreen_chemical", "aloe_vera", "centella"]

# Hormonal factors
HORMONAL_FACTORS = ["menstrual_cycle", "pcos", "stress", "diet", "pregnancy",
                    "postpartum", "puberty"]

# Treatment goals
TREATMENT_GOALS = ["clear_acne", "treat_scar", "fade_hyperpigmentation",
                   "reduce_oiliness", "hydration", "reduce_inflammation",
                   "prevent_acne", "build_routine", "product_recommendation", "see_doctor"]

# Red flags
RED_FLAGS = ["widespread", "painful_lesions", "purulent_lesions", "scarring_risk",
            "infection_signs", "skin_irritation", "treatment_failure",
            "no_prior_treatment", "chronic", "self_treatment_risk"]

# Scarring signs (free text trong EC)
SCARRING_SIGNS = ["sẹo mụn", "thâm sau mụn"]

INTENTS = ["advise", "knowledge", "clarify", "reject"]
SUBJECTS = ["self", "other", "general"]

# ── Trục đa dạng (kiểm soát để phủ rộng) ────────────────────────────────────
STYLES = [
    "teencode nhiều (ko, dc, k, vs, bj, mn, e, sp)",
    "viết trang trọng đầy đủ dấu câu",
    "KHÔNG dấu hoàn toàn",
    "sai chính tả vài chỗ (gõ nhanh, thiếu/thừa chữ)",
    "rất cụt, dưới 6 từ",
    "dài dòng lan man kể nhiều thứ",
    "viết hoa lung tung, nhiều dấu !!! ???",
    "trộn tiếng Anh tên sản phẩm/hoạt chất",
    "giọng lo lắng, cảm xúc",
    "giọng bình thản, kể sự việc",
]
DIFFICULTY = [
    "rõ ràng, dễ trích",
    "mơ hồ, thiếu thông tin",
    "có phủ định (vd 'không phải da dầu', 'mụn không đau')",
    "là câu hỏi kiến thức chung (không kể ca cá nhân)",
    "hỏi giúp người khác (em gái, con, bạn)",
    "ngoài phạm vi (không liên quan mụn / vùng nhạy cảm)",
    "có dấu hiệu nặng (máu, sốt, đau nhiều, lan rộng)",
    "nhiều vùng + nhiều loại mụn cùng lúc",
]

PROMPT_TMPL = """Bạn là người tạo dữ liệu test cho chatbot tư vấn DA MỤN tiếng Việt.
Sinh {batch} câu tin nhắn NGƯỜI DÙNG khác nhau, BẰNG TIẾNG VIỆT, theo yêu cầu:

- Phong cách: {style}
- Độ khó/tình huống: {difficulty}
- Mỗi câu là một người dùng KHÁC NHAU, nội dung KHÁC NHAU rõ rệt.

Với MỖI câu, trả về kèm NHÃN ĐÚNG (ground truth) dựa trên chính nội dung bạn viết.
Chỉ dùng các giá trị canonical sau (để trống/[] nếu câu không đề cập):

CÁC TRƯỜNG NHÃN (đầy đủ theo ExtractionConfidence):
- skin_type: một trong {skin} hoặc null
- sex: một trong {sex} hoặc null
- age: số tuổi (vd 25) hoặc null
- duration_weeks: số tuần bị mụn (vd 12) hoặc null
- is_pregnant: true/false/null
- is_breastfeeding: true/false/null
- inflammation: một trong {infl} hoặc null
- lesions: tập con của {lesions}
- distribution: tập con của {dist}
- products: tập con của {products} - CHỈ gán nếu CÓ HÀNH ĐỘNG ĐANG DÙNG
- medications: tập con của {medications} - CHỈ gán nếu CÓ HÀNH ĐỘNG ĐANG UỐNG/BÔI THUỐC
- allergies: tập con của {allergies} - CHỈ gán nếu CÓ NGỮ CẢNH DỊ ỨNG/KÍCH ỨNG
- scarring_signs: tập con của {scarring} - CHỈ gán nếu ĐỀ CẬP SẸO/THÂM
- hormonal_factors: tập con của {hormonal} - CHỈ gán nếu ĐỀ CẬP YẾU TỐ NỘI TIẾT
- treatment_goals: tập con của {goals} - CHỈ gán nếu ĐỀ CẬP MONG MUỐN ĐIỀU TRỊ
- red_flags: tập con của {redflags} - CHỈ gán nếu CÓ DẤU HIỆU NẶNG/NGUY HIỂM
- intent: một trong {intents}
- query_subject: một trong {subjects}
- reliable: true/false

QUY TẮC GÁN NHÃN (tuân thủ NGHIÊM NGẶT):

1. intent — phân biệt rõ:
   - "advise": người dùng KỂ tình trạng mụn CỦA MÌNH hoặc CỦA NGƯỜI CỤ THỂ rồi xin tư vấn.
   - "knowledge": hỏi kiến thức CHUNG, KHÔNG kể ca cá nhân nào.
   - "reject": HOÀN TOÀN ngoài da liễu mụn.
   - "clarify": có ý định tư vấn nhưng thông tin quá ít/mơ hồ.

2. CẤM BỊA NHÃN:
   - products: CHỈ gán nếu user NÓI ĐANG DÙNG (đang bôi, đang xài, có dùng...). Hỏi "nên dùng gì" KHÔNG phải product.
   - medications: CHỈ gán nếu user NÓI ĐANG UỐNG/ĐƯỢC BÁC SĨ KÊ. Hỏi "uống thuốc gì" KHÔNG phải medication.
   - allergies: CHỈ gán nếu CÓ NGỮ CẢNH kích ứng ("dị ứng với X", "X làm da bị rát", "không hợp với X"). ĐANG DÙNG X ≠ DỊ ỨNG X.
   - scarring_signs: CHỈ gán nếu ĐỀ CẬP SẸO/THÂM/SẴN CÓ.
   - hormonal_factors: CHỈ gán nếu ĐỀ CẬP kinh nguyệt/PCOS/stress/diet/puberty/pregnancy/postpartum.
   - treatment_goals: CHỈ gán nếu NÓI MUỐN điều trị gì đó.
   - red_flags: CHỈ gán nếu CÓ dấu hiệu nặng thật sự (lan rộng, đau nhiều, có mủ, sốt, sẹo, dai dẳng, tự điều trị thất bại).

3. inflammation — GÁN CHẶT:
   - "none": CHỈ khi câu hỏi kiến thức HOẶC chỉ có mụn không viêm (đầu đen/đầu trắng) mà KHÔNG có dấu hiệu viêm.
   - "unknown": khi không đề cập inflammation và câu không đủ để suy.
   - "mild": có mụn đỏ nhẹ, ít, không sưng to.
   - "moderate": mụn viêm + sưng hoặc có mủ, nhiều.
   - "severe": sưng to + đau nhiều, mụn bọc, lan rộng, chảy máu, sốt.

4. reliable:
   - intent="reject" → LUÔN false.
   - true CHỈ khi thông tin đủ rõ (có loại mụn + vị trí HOẶC mức độ).

5. VIẾT TIẾNG VIỆT TỰ NHIÊN. KHÔNG chèn tên nhãn tiếng Anh vào câu "text".

Trả về JSON array, KHÔNG markdown fence.
Định dạng mỗi phần tử:
{{"text":"...","skin_type":null,"sex":null,"age":null,"duration_weeks":null,"is_pregnant":null,"is_breastfeeding":null,"inflammation":null,"lesions":[],"distribution":[],"products":[],"medications":[],"allergies":[],"scarring_signs":[],"hormonal_factors":[],"treatment_goals":[],"red_flags":[],"intent":"advise","query_subject":"self","reliable":true}}
"""


def _env_val(key: str) -> str:
    """Đọc một biến từ .env (fallback os.environ)."""
    env = ROOT / ".env"
    val = ""
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(key + "="):
                val = line.split("=", 1)[1].strip().strip("\"'")
    return os.environ.get(key, val)


def _read_credentials(provider: str):
    """Trả (api_key, base_url, model) theo provider: 'deepseek' hoặc 'openai'."""
    if provider == "openai":
        api_key = _env_val("OPENAI_API_KEY")
        base_url = _env_val("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        model = _env_val("OPENAI_GEN_MODEL") or "gpt-4.1-mini"
        return api_key, base_url, model
    api_key = _env_val("DEEPSEEK_API_KEY")
    base_url = _env_val("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
    model = _env_val("DEEPSEEK_MODEL") or "deepseek-chat"
    return api_key, base_url, model


def _call(prompt: str, api_key: str, base_url: str, model: str,
          timeout: int = 90, temperature: float = 1.0, max_tokens: int = 8000) -> str | None:
    payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]
    except Exception as exc:
        print(f"  [API error] {exc}", file=sys.stderr)
        return None


def _extract_json_array(raw: str):
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if "```" in s[3:] else s
        s = s.lstrip("json").strip()
    a = s.find("[")
    if a == -1:
        return None
    b = s.rfind("]")
    if b != -1:
        try:
            return json.loads(s[a:b + 1])
        except Exception:
            pass
    # Cứu vớt JSON cụt: quét từng object {...} một.
    items, depth, start = [], 0, None
    for i, ch in enumerate(s[a:], start=a):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    items.append(json.loads(s[start:i + 1]))
                except Exception:
                    pass
                start = None
    return items or None


def _clean(item: dict) -> dict | None:
    """Validate + chuẩn hoá luật nhãn. Trả item đã sửa, hoặc None nếu hỏng nặng."""
    if not isinstance(item, dict):
        return None
    t = item.get("text")
    if not isinstance(t, str) or len(t.strip()) < 3:
        return None

    # Validate skin_type
    if item.get("skin_type") not in (SKIN_TYPES + [None]):
        item["skin_type"] = None
    # Validate sex
    if item.get("sex") not in (SEX + [None]):
        item["sex"] = None
    # Validate inflammation
    if item.get("inflammation") not in (INFLAMMATION + [None]):
        item["inflammation"] = None
    # Validate intent
    if item.get("intent") not in INTENTS:
        item["intent"] = "advise"
    # Validate query_subject
    if item.get("query_subject") not in SUBJECTS:
        item["query_subject"] = "self"

    # Lọc giá trị canonical lạ
    item["lesions"] = [x for x in (item.get("lesions") or []) if x in LESIONS]
    item["distribution"] = [x for x in (item.get("distribution") or []) if x in DISTRIBUTIONS]
    item["products"] = [x for x in (item.get("products") or []) if x in PRODUCTS]
    item["medications"] = [x for x in (item.get("medications") or []) if x in MEDICATIONS]
    item["allergies"] = [x for x in (item.get("allergies") or []) if x in ALLERGIES]
    item["hormonal_factors"] = [x for x in (item.get("hormonal_factors") or []) if x in HORMONAL_FACTORS]
    item["treatment_goals"] = [x for x in (item.get("treatment_goals") or []) if x in TREATMENT_GOALS]
    item["red_flags"] = [x for x in (item.get("red_flags") or []) if x in RED_FLAGS]
    item["scarring_signs"] = [x for x in (item.get("scarring_signs") or []) if x in SCARRING_SIGNS]

    # Validate age/duration_weeks
    age = item.get("age")
    if age is not None:
        try:
            age = int(age)
            if not (0 < age <= 120):
                age = None
        except (ValueError, TypeError):
            age = None
    item["age"] = age

    duration = item.get("duration_weeks")
    if duration is not None:
        try:
            duration = int(duration)
            if duration < 0:
                duration = None
        except (ValueError, TypeError):
            duration = None
    item["duration_weeks"] = duration

    # Ensure boolean fields
    for field in ["is_pregnant", "is_breastfeeding", "reliable"]:
        val = item.get(field)
        if val is not None and not isinstance(val, bool):
            item[field] = None

    # Luật hậu kiểm
    if item["intent"] == "reject":
        item["reliable"] = False
        item["query_subject"] = "general"
        item["lesions"] = []
        item["distribution"] = []
        item["skin_type"] = None
        item["inflammation"] = None
        item["products"] = []
        item["medications"] = []
        item["allergies"] = []
        item["scarring_signs"] = []
        item["hormonal_factors"] = []
        item["treatment_goals"] = []
        item["red_flags"] = []

    return item


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000, help="số variant mục tiêu")
    ap.add_argument("--batch", type=int, default=10, help="số câu mỗi request LLM")
    ap.add_argument("--out", default="data/golden_extraction_gen.jsonl")
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--sleep", type=float, default=0.5, help="nghỉ giữa request (rate limit)")
    ap.add_argument("--provider", choices=["deepseek", "openai"], default="deepseek",
                    help="LLM sinh nhãn: deepseek (rẻ) hoặc openai (nhãn nhất quán hơn)")
    ap.add_argument("--model", default="", help="ép model cụ thể (override mặc định của provider)")
    args = ap.parse_args()

    api_key, base_url, model = _read_credentials(args.provider)
    if args.model:
        model = args.model
    if not api_key:
        key_name = "OPENAI_API_KEY" if args.provider == "openai" else "DEEPSEEK_API_KEY"
        print(f"ERROR: {key_name} không có trong .env hoặc env", file=sys.stderr)
        sys.exit(1)
    print(f"  provider={args.provider} model={model} base={base_url}", file=sys.stderr)

    out_path = (ROOT / args.out) if not os.path.isabs(args.out) else Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    seen_texts: set[str] = set()
    written = 0
    n_batches = (args.n + args.batch - 1) // args.batch

    with open(out_path, "w", encoding="utf-8") as fh:
        for i in range(n_batches):
            style = random.choice(STYLES)
            diff = random.choice(DIFFICULTY)
            prompt = PROMPT_TMPL.format(
                batch=args.batch, style=style, difficulty=diff,
                skin=SKIN_TYPES, sex=SEX, lesions=LESIONS, dist=DISTRIBUTIONS,
                infl=INFLAMMATION, products=PRODUCTS, medications=MEDICATIONS,
                allergies=ALLERGIES, hormonal=HORMONAL_FACTORS, goals=TREATMENT_GOALS,
                redflags=RED_FLAGS, scarring=SCARRING_SIGNS,
                intents=INTENTS, subjects=SUBJECTS,
                style_id=STYLES.index(style), diff_id=DIFFICULTY.index(diff),
            )
            raw = _call(prompt, api_key, base_url, model, temperature=args.temperature)
            arr = _extract_json_array(raw)
            if not arr:
                print(f"  [batch {i+1}/{n_batches}] parse fail, skip", file=sys.stderr)
                time.sleep(args.sleep)
                continue

            kept = 0
            for item in arr:
                item = _clean(item)
                if item is None:
                    continue
                key = item["text"].strip().lower()
                if key in seen_texts:
                    continue
                seen_texts.add(key)
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
                fh.flush()
                written += 1
                kept += 1
                if written >= args.n:
                    break
            print(f"  [batch {i+1}/{n_batches}] style='{style[:20]}' diff='{diff[:20]}' "
                  f"kept={kept} total={written}", file=sys.stderr)
            if written >= args.n:
                break
            time.sleep(args.sleep)

    print(f"\nDONE: {written} variant unique → {out_path}")


if __name__ == "__main__":
    main()
