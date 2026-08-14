# Spec — Data finetune cho model Unified Intake (Qwen 2.5 3B Q4)

> Định nghĩa dataset finetune cho **một model duy nhất** thay hai LLM path hiện tại
> (`llm_extractor.py` + `llm_router.py`). Model làm **extract + intent route trong 1 call**,
> xuất **1 JSON constrained**. Lớp rule-based (`normalizer.py`, `extraction_confidence.py`,
> `intent_router.py`, `semantic_router.py`) **KHÔNG xóa** — chỉ còn vai trò fallback khi model
> lỗi hoàn toàn (đường cùng) và safety substrate always-on.

---

## 0. TL;DR

- **Model học đúng 1 task**: đọc 1 turn tiếng Việt → 1 JSON `{intent, confidence, description, context, clinical}`.
- **Dataset**: ~4.000 record train + ~500 eval gold gán tay. Format chat SFT (`messages`).
- **Constrained decoding bắt buộc** (JSON schema) → lỗi format ≈ 0; data lo phần ngữ nghĩa.
- **Parity train == serve**: wire key + enum + node `{value, confidence}` copy nguyên từ `schemas/core.py` + `llm_extractor.py`.
- Rule-based chỉ kích hoạt khi model fail (JSON hỏng sau retry, hoặc `ExtractorFallback`/`RouterFallback`).

---

## 1. Model làm gì (định nghĩa task)

**Input**: turn hiện tại đã preprocess + tối đa 3 turn gần nhất (cho follow-up).

**Output**: đúng 1 JSON object, root gồm:

| Field root | Kiểu | Nguồn (module cũ) | Ghi chú |
|---|---|---|---|
| `intent` | enum: `advise` \| `knowledge` \| `clarify` \| `reject` | llm_router | phần route |
| `confidence` | float [0,1] | llm_router | độ tự tin của intent |
| `description` | string 1–4000 | llm_extractor | nguyên văn turn |
| `context` | object | llm_extractor | UserContext, mỗi field là node `{value, confidence}` |
| `clinical` | object \| `null` | llm_extractor | AcneClinicalInput; `null` nếu không có tín hiệu lâm sàng |

Đây là gộp output của 2 module cũ vào 1 root object → 1 call. Query rewrite **không** thuộc model (giữ rule-based `retrieval_query.py`).

---

## 2. Wire contract (BẮT BUỘC khớp serve)

Key và enum lấy nguyên từ code — **không tự chế, không dịch, không đổi hoa/thường**.

### 2.1 `context` (các key parser đọc)
```
age               : int 0–120 | null
sex               : "male" | "female" | "other" | null
skin_type         : "dry"|"oily"|"combination"|"sensitive"|"normal"|"unknown" | null
is_pregnant       : bool (mặc định false)
is_breastfeeding  : bool (mặc định false)
duration_weeks    : int >=0 | null   (năm×52, tháng×4, ngày→round(n/7))
allergies         : [string]
current_products  : [string]   (canonical, xem 4.6)
medications       : [string]
```

### 2.2 `clinical` (các key parser đọc)
```
lesion_types        : [ enum _LESION ]
inflammation_level  : enum _INFLAMMATION
lesion_distribution : [ enum _DISTRIBUTION ]
```
Không có tín hiệu lâm sàng nào → `clinical: null` (KHÔNG để object rỗng).

### 2.3 Enum sets (copy từ `schemas/core.py` / `llm_extractor.py`)
```
_LESION        = comedone, whitehead, blackhead, closed_comedone, papule,
                 pustule, nodule, cyst, scar,
                 post_inflammatory_hyperpigmentation, other
_SKIN          = dry, oily, combination, sensitive, normal, unknown
_SEX           = male, female, other
_INFLAMMATION  = none, mild, moderate, severe, unknown
_DISTRIBUTION  = forehead, cheeks, chin, jawline, nose, around_mouth,
                 back, chest, shoulders, neck, t_zone, other
intent         = advise, knowledge, clarify, reject
```

### 2.4 Dạng node có confidence
Mỗi scalar field là `{"value": <val>, "confidence": <0..1>}`. Mỗi phần tử list là `{"value": <val>, "confidence": <0..1>}`. Parser (`_scalar_node`/`_list_nodes`) chấp cả flat lẫn node, **nhưng train dùng dạng node** để model học calibration.

---

## 3. Format record (chat SFT)

```json
{
  "messages": [
    {"role": "system", "content": "<intake system prompt — ép JSON, liệt kê enum>"},
    {"role": "user", "content": "<turn tiếng Việt (+ tối đa 3 turn history nếu follow-up)>"},
    {"role": "assistant", "content": "<JSON hợp nhất, minified>"}
  ],
  "meta": {"case_type": "advise_selfreport_rich", "source": "deepseek|golden|handwritten", "judged": true}
}
```
- System prompt cố định trên toàn dataset = đúng system dùng lúc serve (parity).
- Assistant content minified, không markdown fence, ký tự đầu `{` cuối `}`.
- `meta` không đưa vào prompt train, chỉ để thống kê/gate.

### Ví dụ record (ADVISE, rich)
```json
{"messages":[
  {"role":"system","content":"Bạn là bộ intake cho hệ tư vấn da mụn. Đọc tin nhắn người dùng, trả về DUY NHẤT một JSON: intent + trích xuất field lâm sàng theo schema. Chỉ in JSON."},
  {"role":"user","content":"Em nữ 22 tuổi da dầu, bị mụn mủ với mụn đỏ ở hai bên má và quai hàm khoảng 2 tháng nay. Em đang bôi BHA nhưng chưa đỡ."},
  {"role":"assistant","content":"{\"intent\":\"advise\",\"confidence\":0.95,\"description\":\"Em nữ 22 tuổi da dầu, bị mụn mủ với mụn đỏ ở hai bên má và quai hàm khoảng 2 tháng nay. Em đang bôi BHA nhưng chưa đỡ.\",\"context\":{\"age\":{\"value\":22,\"confidence\":0.98},\"sex\":{\"value\":\"female\",\"confidence\":0.97},\"skin_type\":{\"value\":\"oily\",\"confidence\":0.9},\"is_pregnant\":{\"value\":false,\"confidence\":0.99},\"current_products\":[{\"value\":\"salicylic acid\",\"confidence\":0.85}],\"medications\":[],\"allergies\":[],\"duration_weeks\":{\"value\":8,\"confidence\":0.75}},\"clinical\":{\"lesion_types\":[{\"value\":\"pustule\",\"confidence\":0.9},{\"value\":\"papule\",\"confidence\":0.85}],\"lesion_distribution\":[{\"value\":\"cheeks\",\"confidence\":0.88},{\"value\":\"jawline\",\"confidence\":0.85}],\"inflammation_level\":{\"value\":\"moderate\",\"confidence\":0.7}}}"}
],"meta":{"case_type":"advise_selfreport_rich","source":"handwritten","judged":true}}
```

---

## 4. Hành vi bắt buộc (global invariants — dạy xuyên suốt mọi case)

Đây là phần quan trọng nhất: quyết định chất lượng hơn số lượng.

**4.1 Chỉ trích cái user THỰC SỰ tự khai.** Câu hỏi kiến thức chung, hỏi về sản phẩm, hay chất đã ngưng dùng → KHÔNG trích. `intent=knowledge` thì `context={}`, `clinical=null`.

**4.2 Negation / đã-ngưng-dùng.** "không dùng BHA nữa", "đã ngừng tretinoin" → KHÔNG đưa vào `current_products`/`medications`. Chỉ trích chất đang/đã dùng có tín hiệu (đang bôi/uống, bác sĩ kê, kèm tần suất/thời gian).

**4.3 Quy đổi duration.** năm×52, tháng×4, ngày→round(n/7). "2 tháng" → `duration_weeks.value = 8`.

**4.4 Empty → null/[].** Không có tín hiệu: scalar → bỏ field hoặc `null`; list → `[]`; toàn bộ lâm sàng trống → `clinical=null`. KHÔNG bịa field từ câu xã giao.

**4.5 Enum đúng tuyệt đối.** Chỉ dùng giá trị trong tập. Không tự chế ("very_bad"), không dịch ("mụn viêm" phải map về enum, không để tiếng Việt).

**4.6 Canonical hóa alias.** BHA→salicylic acid, BPO→benzoyl peroxide, Differin→adapalene… (khớp `retrieval_query.py`). Áp cho `current_products`/`canonical_ingredients`.

**4.7 Confidence calibration** (xem mục 5).

**4.8 Safety-first cho field nhạy cảm.** Nếu tín hiệu thuốc/thai kỳ **mơ hồ** → để field mơ hồ với conf thấp, KHÔNG đoán chắc. (Hard block deterministic vẫn chạy độc lập ở substrate; data không được "chữa" cho substrate, chỉ không làm nhiễu.)

**4.9 Robust nhiễu đầu vào.** Tiếng Việt không dấu, mix VI/EN, teencode nhẹ, thiếu dấu câu → vẫn trích đúng.

---

## 5. Chính sách gán confidence

| Tình huống | confidence |
|---|---|
| User nêu tường minh, không mơ hồ ("nữ 22 tuổi") | 0.9–1.0 |
| Suy luận hợp lý nhưng gián tiếp ("da bóng dầu vùng T" → combination) | 0.6–0.85 |
| Mơ hồ / phải đoán ("chắc tầm 20 mấy") | 0.3–0.55 |
| Không đủ tín hiệu | field bỏ / `null` (không phải conf=0) |

`intent.confidence`: cao (>0.9) cho câu rõ ràng; thấp (0.5–0.7) cho câu ranh giới advise/knowledge/clarify — dạy model "biết mình không chắc" để downstream ưu tiên `clarify`.

---

## 6. Taxonomy case + quantity (train ~4.000)

Mỗi case type có **định nghĩa hành vi output** riêng. Số lượng phản ánh traffic thật (không cân bằng cứng).

### Nhóm ADVISE — user tự khai, extraction nặng (2.000 · 50%)

| case_type | SL | Hành vi output đúng |
|---|---:|---|
| `advise_selfreport_simple` | 500 | 1–2 field rõ, conf cao, `clinical` có thể null nếu chỉ context |
| `advise_selfreport_rich` | 450 | nhiều enum + list đồng thời, đủ context+clinical |
| `advise_negation_stopped` | 350 | chất đã ngưng KHÔNG vào list; chỉ trích chất đang dùng |
| `advise_duration_convert` | 200 | `duration_weeks` quy đổi đúng |
| `advise_noaccent` | 250 | input không dấu → trích đúng, enum chuẩn |
| `advise_mixed_vi_en` | 100 | tên hoạt chất EN trong câu VI → canonical |
| `advise_ambiguous_lowconf` | 150 | field mơ hồ → conf thấp, không bịa chắc |

### Nhóm KNOWLEDGE — hỏi kiến thức, KHÔNG trích (800 · 20%)

| case_type | SL | Hành vi output đúng |
|---|---:|---|
| `knowledge_product_trap` | 300 | hỏi "X có tốt không" → `context={}`, `clinical=null`, KHÔNG nhét X vào products |
| `knowledge_general` | 300 | kiến thức chung → intent knowledge, rỗng |
| `knowledge_ingredient_compare` | 200 | so sánh hoạt chất → không canonical vào products |

### Nhóm CLARIFY — mơ hồ / follow-up (500 · 12.5%)

| case_type | SL | Hành vi output đúng |
|---|---:|---|
| `clarify_vague` | 300 | thiếu thông tin → intent clarify, trích cái ít ỏi có được |
| `clarify_followup_multiturn` | 200 | dùng 3 turn history để hiểu turn ngắn ("vậy dùng sáng hay tối?") |

### Nhóm REJECT — adversarial / unsafe (500 · 12.5%)

| case_type | SL | Hành vi output đúng |
|---|---:|---|
| `reject_jailbreak_meta` | 150 | DAN/meta/"bỏ luật" → intent reject, `context={}`, `clinical=null` |
| `reject_ood` | 200 | ngoài chủ đề mụn → reject |
| `reject_unsafe_rx` | 150 | đòi kê đơn/liều cao → reject (không tự trích như đơn hợp lệ) |

### Nhóm GLUE — xã giao (200 · 5%)

| case_type | SL | Hành vi output đúng |
|---|---:|---|
| `glue_greeting_thanks` | 200 | chào/cảm ơn/lan man → thường clarify hoặc advise nhẹ, fields RỖNG (không bịa) |

**Tổng train: 4.000.**

### Phân bố intent thu được (cross-check)
advise ~50% · knowledge ~20% · clarify ~12% · reject ~12% · glue → clarify/advise ~5%.

---

## 7. Eval gold (gán tay, ~500 — KHÔNG judge-only)

| Bộ | SL | Nguồn |
|---|---:|---|
| Intent test | 260 | giữ nguyên `data/intent_classify.test.jsonl` |
| Extraction gold | 250 | build mới, nhồi đậm negation + duration + knowledge-trap + no-accent |

Metric đo: intent accuracy (per-class F1, chú ý reject/clarify), field exact-match theo enum, list precision/recall, confidence calibration (ECE/bin), tỉ lệ enum-invalid (kỳ vọng ≈0 nhờ constrained), tỉ lệ fallback bị kích hoạt.

---

## 8. Quan hệ với fallback (data dạy gì / substrate lo gì)

- **Data dạy model**: extract + route "happy path" chất lượng cao, kể cả case khó ở mục 6.
- **Substrate deterministic (không dạy qua data, chạy song song)**: hard block thuốc/thai kỳ/genital, safety terms, parse an toàn always-on. Data **không** được cố thay thế các block này.
- **Rule fallback (đường cùng)**: chỉ chạy khi model fail (JSON hỏng sau retry ≤2, hoặc contract raise). Không có record data riêng cho fallback — nó dùng chính `intent_router.py`/`normalizer.py`.
- **Xử lý lỗi runtime** (không thuộc data nhưng liên quan contract): enum ngoài tập / conf < ngưỡng → field `null` + append `dropped_fields{field, raw, reason}`; nếu field bị drop là field an toàn → ép `intent=clarify`.

---

## 9. Quy trình sinh (tái dùng `datagen/` sẵn có)

1. **Relabel + gộp**: chuyển `data/golden_extraction_gen.jsonl` (flat) → format node nested-có-confidence, gắn thêm `intent`. Tái dùng phần lớn 985 record cho nhóm advise/knowledge.
2. **Top-up case thiếu**: sinh mới (deepseek/golden) cho negation (350), knowledge_product_trap (300), reject (500), no-accent (250), duration (200) — dùng generator sẵn có, ép constrained schema.
3. **Judge filter**: gate grounded/enum-valid/contract như `datagen/gates.py`.
4. **Dedup** theo id (writer append-only, resume).
5. **Split**: train/val = 90/10 trong 4.000; test = eval gold mục 7 (tách hoàn toàn, không rò).

---

## 10. Quality gates (fail = loại record)

- JSON parse OK + khớp constrained schema.
- Mọi enum ∈ tập hợp lệ (0 hallucination).
- `intent` ∈ 4 giá trị; `confidence` ∈ [0,1].
- `clinical` = null HOẶC object hợp lệ (không object rỗng).
- Không trùng id; không rò eval sang train.
- Cân bằng: mỗi case_type đạt ≥90% quota; mỗi intent lớp ≥ ngưỡng tối thiểu (reject/clarify không dưới 10%).
- Negation set: 0 record để lộ entity đã ngưng vào list (kiểm tự động bằng cue phủ định).

---

## 11. Mốc số lượng (tóm tắt)

| Hạng mục | Số lượng |
|---|---:|
| Train | 4.000 |
| Val | ~450 (trong 90/10) |
| Eval gold (test) | ~500 |
| Epoch | 2–3 |
| LoRA rank | 16–32 |
| Ngưỡng "đủ" tối thiểu | ~3.000 nếu coverage tốt |
| Trần hữu ích | ~8.000 (trên đó lợi ích giảm dần, rủi ro overfit format) |
