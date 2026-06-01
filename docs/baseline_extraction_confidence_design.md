# Thiết kế: Baseline extraction phủ rộng + ổn định, có confidence, không cần nhồi từ điển

> Mục tiêu: các task rule-based (`normalizer.py`, `intent_router.py`, `completeness.py`) **cover được hầu hết case và ổn định** mà **không phải thêm cả từ điển tiếng Việt** vào, đồng thời mỗi field có **confidence** để khi thấp thì hệ thống **xử lý an toàn (graceful degrade)** thay vì đoán bừa.
>
> Quyết định phạm vi (đã chốt với bạn):
> - **Fallback chỉ dùng fuzzy + chuẩn hoá**, KHÔNG thêm LLM call vào baseline. (Có 1 mục "LLM hook" để mở sau, mặc định OFF — vì bật LLM sẽ làm baseline mất tính rẻ/reproducible.)
> - Triển khai theo hướng **"bọc không phá vỡ"**: giữ nguyên regex/extractor cũ làm tầng pattern, thêm fuzzy + confidence ở tầng trên. `normalize_chat_message()` và schema `UserInput` KHÔNG đổi.

---

## ✅ TRẠNG THÁI TRIỂN KHAI (đã code)

Đã implement xong baseline (12/13 task). Các file:

| File | Vai trò | Trạng thái |
|---|---|---|
| `src/acne_llm/schemas/extraction.py` | `FieldResult`, `ListFieldResult` (value + confidence + method) | mới |
| `src/acne_llm/utils/fuzzy_match.py` | fuzzy `best_match`/`find_in_text` (rapidfuzz, `fuzz.ratio` + length-gate) | mới |
| `src/acne_llm/chat/extraction_confidence.py` | `extract_with_confidence()` — bọc extractor cũ + fuzzy + tính confidence per field | mới |
| `src/acne_llm/chat/normalizer.py` | **không đổi** (regex cũ giữ nguyên = tầng pattern) | giữ |
| `src/acne_llm/chat/completeness.py` | nhận `confidence=` optional; field conf < ngưỡng → coi như thiếu → hỏi lại | sửa |
| `src/acne_llm/chat/intent_router.py` | `route_intent` ép `clarify` khi `confidence < route_min_confidence` | sửa |
| `src/acne_llm/chat/intake.py` | tính `extract_with_confidence` rồi truyền vào `check_completeness` | sửa |
| `src/acne_llm/config.py` + `.env*` | ngưỡng: `extract_fuzzy_accept/review`, `extract_min_field_conf`, `route_min_confidence`, `extract_llm_fallback=false` | sửa |
| `data/golden_extraction.jsonl` | golden set 15 câu có nhãn + khoảng confidence | mới |
| `scripts/tune_extraction_thresholds.py` | đo accuracy/recall/confidence-band trên golden set | mới |
| `tests/test_extraction_fieldresult.py`, `test_extraction_confidence.py`, `test_confidence_behavior.py` | test hạ tầng + tầng confidence + hành vi mới | mới |

**Kết quả test:** vùng thay đổi 191 passed + 1 xfailed; toàn suite 369 passed (16 fail còn lại nằm ngoài vùng sửa: test cũ lệch code gốc + thiếu deps môi trường).

**Kết quả golden set (heuristic khởi điểm):** products recall 1.00 (fuzzy bắt cả sai chính tả "salicilic"→salicylic), skin_type accuracy 0.56 (regex cũ miss vài câu không dấu — đúng vùng nhánh embedding #13 sẽ vá), inflammation 0.50 (mẫu ít).

**Còn lại:** chạy `scripts/eval_rag.py --skip-gen` trên máy thật (cần ollama+embedding, sandbox không có) để xác nhận RAG eval không tụt; nhánh embedding-KNN (#13) để sau.

---

---

## 1. Vấn đề hiện tại (đọc từ code)

`src/acne_llm/chat/normalizer.py` (~1505 dòng) đang gánh toàn bộ extraction theo kiểu **liệt kê tay**:

- `_PRODUCT_TERMS`, `_MEDICATION_TERMS`: list literal hàng trăm chuỗi (BHA, retinol, "kem trộn", brand names...).
- `_SKIN_TYPES`, `_SEX_TERMS`, `_DISTRIBUTION_TERMS`, lesion/red_flag/...: regex viết tay khổng lồ, mỗi class một khối `(?:...|...|...)`.
- Mỗi biến thể tiếng Việt (có dấu / không dấu / teencode) phải tự liệt kê: `dầu|dau`, `nhờn|nhon`, `tôi|toi|mình|minh`...

Hệ quả:
1. **Phủ kém ở đuôi (long tail).** Câu lạ, sai chính tả, brand mới → miss. Cách duy nhất hiện tại là *thêm chuỗi vào từ điển* → từ điển phình vô hạn, khó bảo trì.
2. **Không biết mình chắc đến đâu.** Hàm trả `value | None`. Không có tín hiệu "match yếu" để pipeline biết nên dùng hay nên hỏi lại. Match sai và match đúng trông giống nhau.
3. **Brittle.** Regex dài dễ vỡ, sửa một nhánh dễ làm hỏng nhánh khác; thêm biến thể dấu/không dấu nhân đôi mọi alternation.

Câu hỏi của bạn quy về 3 yêu cầu: **(a) phủ rộng mà không nhồi từ điển, (b) mỗi task có confidence, (c) conf thấp thì degrade an toàn.**

---

## 2. Nguyên tắc thiết kế

Thay vì "từ điển càng to càng phủ", chuyển sang **chuẩn hoá đầu vào mạnh + lexicon nhỏ gọn (canonical) + so khớp mờ (fuzzy) + scoring**. Bốn ý tưởng cốt lõi:

### 2.1. Tách "lexicon nhỏ" khỏi "biến thể"
Không liệt kê mọi biến thể. Chỉ giữ **dạng canonical** của mỗi khái niệm; các biến thể (dấu/không dấu, teencode, viết tắt) do **tầng chuẩn hoá** lo, không phải do từ điển lo.

```
Trước:  "dầu", "dau", "nhờn", "nhon", "tiết dầu", "tiet dau", ...  (n biến thể)
Sau:    canonical = "dau nhon"  +  normalize(input) đã bỏ dấu/teencode  →  1 entry
```

→ Từ điển co lại nhiều lần. Thêm khái niệm mới = thêm 1 dòng canonical, không phải 8 dòng biến thể.

### 2.2. Một pipeline chuẩn hoá dùng chung (đã có sẵn một phần)
Repo đã có `preprocess.prepare_user_text()` sinh `clean_text`, `clean_text_no_accent`, `teencode_replaced`. Tận dụng triệt để: **mọi matcher chạy trên text đã bỏ dấu + đã gỡ teencode**, nên lexicon chỉ cần viết một dạng (không dấu, thường). Điều này xoá bỏ phần lớn cặp `x|x_không_dấu` trong regex hiện tại.

### 2.3. Fuzzy match thay cho liệt kê biến thể chính tả
Với các field dạng **danh mục đóng, từ vựng kỹ thuật** (sản phẩm, thuốc, hoạt chất, brand) — đây là nơi từ điển phình to nhất — dùng **fuzzy matching** trên token/n-gram:

- Token hoá input → so từng token/cụm với lexicon canonical bằng khoảng cách chỉnh sửa (Levenshtein/Jaro-Winkler) hoặc token-set ratio.
- "retinol" vs "rentinol", "differin" vs "diferin", "salicylic" vs "salicilic" → vẫn khớp, **không cần thêm entry**.
- Ngưỡng tỉ lệ khớp → trở thành **confidence** luôn (xem §3).

Đây chính là cơ chế giúp "cover hầu hết case mà không add cả từ điển": bạn chỉ duy trì ~1 canonical/khái niệm, fuzzy lo phần đuôi.

### 2.4. Mỗi extraction trả về kết quả CÓ confidence
Đổi chữ ký: thay vì `-> Value | None`, trả `FieldResult(value, confidence, method, evidence)`. Đây là thay đổi nền tảng cho toàn bộ yêu cầu (b) và (c).

---

## 3. Mô hình dữ liệu: `FieldResult`

```python
# schemas/extraction.py  (đề xuất file mới)
from dataclasses import dataclass, field
from typing import Generic, TypeVar, Literal

T = TypeVar("T")
Method = Literal["exact", "fuzzy", "pattern", "fallback", "none"]

@dataclass(frozen=True)
class FieldResult(Generic[T]):
    value: T | None              # giá trị chuẩn hoá (None nếu không trích được)
    confidence: float            # 0.0–1.0
    method: Method               # cách trích được — để audit/debug
    evidence: str = ""           # span gốc đã khớp (truy vết)

    @property
    def is_confident(self) -> bool:
        return self.value is not None and self.confidence >= 0.0  # ngưỡng do config
```

**Cách gán confidence (không cần ML, thuần quy tắc):**

| Method | Ý nghĩa | Confidence gợi ý |
|---|---|---|
| `exact` | khớp đúng canonical sau chuẩn hoá | `0.95–1.0` |
| `pattern` | khớp regex có ngữ cảnh (vd "da tôi rất dầu") | `0.8–0.95` |
| `fuzzy` | khớp mờ, lấy theo tỉ lệ similarity | `= similarity` (vd 0.86) |
| `fallback` | suy luận yếu (vd "có mụn không rõ loại" → mild) | `0.4–0.6` |
| `none` | không trích được | `0.0` |

Điểm hay: confidence của `fuzzy` **chính là** tỉ lệ khớp chuỗi → không phải bịa số.

---

## 4. Kiến trúc matcher 3 tầng (per field)

Mỗi field chạy lần lượt, **dừng ở tầng đầu tiên đủ chắc**:

```
              ┌─────────────────────────────────────────────┐
  input  ───► │ Tầng 0 — Normalize chung                    │
              │   bỏ dấu, lower, gỡ teencode, collapse ws    │
              └───────────────┬─────────────────────────────┘
                              ▼
              ┌─────────────────────────────────────────────┐
              │ Tầng 1 — EXACT/PATTERN                       │
              │   so canonical lexicon + regex ngữ cảnh      │
              │   hit → FieldResult(conf 0.8–1.0) → STOP     │
              └───────────────┬─────────────────────────────┘
                              ▼ (miss)
              ┌─────────────────────────────────────────────┐
              │ Tầng 2 — FUZZY                               │
              │   token-set / Levenshtein vs canonical       │
              │   sim ≥ τ_accept → conf = sim → STOP         │
              │   τ_review ≤ sim < τ_accept → giữ nhưng       │
              │       đánh dấu low-confidence                 │
              └───────────────┬─────────────────────────────┘
                              ▼ (vẫn dưới ngưỡng)
              ┌─────────────────────────────────────────────┐
              │ Tầng 3 — FALLBACK an toàn (KHÔNG LLM)        │
              │   • field bắt buộc → để None + đánh dấu      │
              │     "cần hỏi lại" (đẩy sang completeness)    │
              │   • field suy luận được → giá trị thận trọng │
              │     conf thấp (vd severity → mild)           │
              └─────────────────────────────────────────────┘
```

Lưu ý: **Tầng 3 ở baseline KHÔNG gọi LLM.** "Tự suy luận" được hiện thực bằng *quy tắc fallback bảo thủ* + *đẩy việc hỏi lại sang `completeness`/`clarify`*. Đây là cách degrade an toàn rẻ và reproducible. (Muốn LLM thì xem §7.)

---

## 5. Áp cho từng task

### 5.1. `normalizer.py` — các field

| Field | Loại | Chiến lược chính | Ghi chú giảm từ điển |
|---|---|---|---|
| products / ingredients / medications | danh mục đóng, kỹ thuật | **Fuzzy** trên canonical list | Bỏ mọi biến thể chính tả/dấu khỏi list → chỉ giữ canonical. Đây là nơi cắt từ điển nhiều nhất. |
| skin_type | phân loại nhỏ (5 lớp) | Pattern ngắn trên text đã bỏ dấu | Gộp `x\|x_no_accent`. Regex ngắn lại ~1/2. |
| sex | phân loại (2 lớp) | Pattern | Như trên |
| distribution | phân loại vị trí | Pattern / từ khoá canonical | Như trên |
| lesions | phân loại tổn thương | Từ khoá canonical + fuzzy | |
| severity / inflammation | suy luận | Quy tắc + fallback bảo thủ | Tầng 3: không rõ → mild, conf thấp |
| age / duration_weeks / count / concentration | số | Regex số (đã ổn) | Giữ nguyên, gán conf cao khi parse được |
| red_flags / allergies | an toàn | Pattern — **ưu tiên recall** | Field an toàn: hạ ngưỡng accept để không bỏ sót |

**Chữ ký mới (đề xuất):**
```python
def extract_skin_type(text_norm: str) -> FieldResult[SkinType]: ...
def extract_products(text_norm: str) -> list[FieldResult[str]]: ...
# normalize_chat_message vẫn trả UserInput như cũ, nhưng nội bộ giữ
# bản đồ field -> FieldResult để audit & để completeness đọc confidence.
```

### 5.2. `intent_router.py`
`RouteDecision` đã có `confidence` — chuẩn hoá lại cho nhất quán:
- Mỗi tín hiệu intent (advise/knowledge/clarify/reject) tính điểm; intent thắng + margin so với á quân → confidence.
- `confidence < τ_route` → mặc định **`clarify`** thay vì đoán bừa advise/knowledge. Đây là degrade an toàn cho routing.

### 5.3. `completeness.py`
Đây là nơi confidence "phát huy tác dụng" mà không cần LLM:
- Một field coi là **đã có** chỉ khi `FieldResult.confidence ≥ τ_field`.
- Field bắt buộc mà conf < ngưỡng → đưa vào danh sách "cần làm rõ" → route `clarify` → hỏi lại đúng field đó.
- → Hệ thống "biết mình không chắc" và **hỏi lại** thay vì trả lời sai. Chính là hành vi "ổn định với toàn bộ case".

---

## 6. Config ngưỡng (đưa hết ra ngoài, không hardcode)

Thêm vào `config/settings.py` (pydantic-settings, đọc từ `.env`) — đáp ứng ý "thêm conf cho các task":

```ini
# .env  — ngưỡng confidence per tầng / per nhóm field
EXTRACT_FUZZY_ACCEPT=0.86        # sim ≥ → nhận, method=fuzzy
EXTRACT_FUZZY_REVIEW=0.72        # sim trong [review, accept) → giữ, low-conf
EXTRACT_MIN_FIELD_CONF=0.60      # completeness coi field "đã có" khi ≥ ngưỡng
EXTRACT_SAFETY_ACCEPT=0.78       # red_flags/allergies hạ ngưỡng (ưu tiên recall)
ROUTE_MIN_CONFIDENCE=0.55        # dưới ngưỡng → clarify
EXTRACT_LLM_FALLBACK=false       # baseline = false (xem §7)
```

Lợi ích: tinh chỉnh độ phủ/độ chính xác bằng cách đổi `.env`, không sửa code; A/B được; có `.env.baseline` riêng để khoá cấu hình baseline reproducible.

---

## 7. (Tùy chọn, mặc định TẮT) Hook LLM khi conf thấp

Bạn đã chọn **không** dùng LLM cho baseline. Mục này chỉ để mở đường sau này, đặt sau cờ `EXTRACT_LLM_FALLBACK=false`:

- Nếu sau Tầng 2 vẫn `review < sim < accept` **và** field bắt buộc → có thể gọi micro-LLM (`qwen2.5:0.5b` đã có) extract JSON 1 field.
- Phải đặt sau cờ để baseline vẫn rẻ/reproducible; eval baseline luôn chạy với cờ = false.
- Khi bật: kết quả LLM gán `method="llm"`, confidence trần (vd 0.7) để vẫn ưu tiên rule khi rule chắc hơn.

> Khuyến nghị: chỉ bật cờ này ở nhánh thử nghiệm, **không** trong baseline, để con số eval baseline không phụ thuộc tính ngẫu nhiên của LLM.

---

## 8. Bản đồ thay đổi (khi bạn quyết định code)

| Hạng mục | File | Tính chất |
|---|---|---|
| `FieldResult` + lexicon canonical | `schemas/extraction.py` (mới), `chat/_terms.py` | nền tảng |
| Tầng normalize dùng chung | tận dụng `chat/preprocess.py` | có sẵn |
| Fuzzy matcher | util mới `utils/fuzzy_match.py` (rapidfuzz) | thêm dep `rapidfuzz` |
| Đổi extractor sang trả `FieldResult` | `chat/normalizer.py` | refactor lớn nhưng cơ học |
| Đọc confidence | `chat/completeness.py`, `chat/intent_router.py` | nhỏ |
| Ngưỡng | `config/settings.py`, `.env*` | nhỏ |
| Test | `tests/` — golden set có nhãn + conf kỳ vọng | bắt buộc |

**Thứ tự an toàn để triển khai (gợi ý):**
1. Thêm `FieldResult` + viết test golden cho 1 field (đề xuất `skin_type` hoặc `products`).
2. Refactor đúng field đó sang 3 tầng + fuzzy, đối chiếu test cũ không vỡ.
3. Nhân rộng từng field, mỗi field 1 PR nhỏ.
4. Sau cùng nối confidence vào `completeness`/`intent_router` + đưa ngưỡng ra `.env`.

---

## 9. Tóm tắt trả lời câu hỏi của bạn

- **Phủ hầu hết case mà không nhồi từ điển?** → Chuẩn hoá mạnh (bỏ dấu + teencode dùng chung) để xoá biến thể, giữ lexicon **canonical nhỏ**, và **fuzzy match** lo phần đuôi (sai chính tả, brand lạ). Thêm khái niệm = 1 dòng canonical, không phải hàng chục biến thể.
- **Thêm confidence cho mỗi task?** → Mọi extractor trả `FieldResult(value, confidence, method)`; confidence suy ra từ method + tỉ lệ fuzzy; ngưỡng để ngoài `.env`.
- **Conf thấp thì tự xử lý ổn định?** → Degrade an toàn **không cần LLM**: field bắt buộc thiếu/yếu → `completeness` đánh dấu → route `clarify` hỏi lại đúng field; routing yếu → mặc định `clarify`; field suy luận được → giá trị bảo thủ conf thấp. (LLM fallback để sẵn sau cờ `EXTRACT_LLM_FALLBACK`, mặc định tắt.)
