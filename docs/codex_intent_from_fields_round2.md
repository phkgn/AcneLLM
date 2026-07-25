# Codex Handoff — Vòng 2: định tuyến advise/knowledge từ field extract (bỏ intent của model)

> **Vai trò của bạn (Codex):** hiện thực đúng plan này, **tự chạy model thật + runtime thật**,
> quan sát hành vi, sửa nếu sai, chạy lại test, rồi báo cáo. Không refactor ngoài phạm vi.
> Không đụng các cổng guardrail/scope/refuse/complaint/medication.

---

## 0. Bối cảnh (kết quả vòng 1)

Path `acne-extractor:1.5b` đã live (`EXTRACTOR_MODE=llm`, default). Contract JSON 100% ổn,
nhưng **intent do model quyết rất kém**: primary-intent acc 0.256 (rule: 0.716),
query-subject 0.46 (rule: 0.71). Lỗi hệ thống: model biến ca tư vấn cá nhân
(`advise+self`) thành `knowledge+non_self`.

**Nguyên nhân gốc (đã điều tra):** định nghĩa advise/knowledge trong đầu model **lệch**
với định nghĩa vận hành của repo. Repo định nghĩa hai route bằng *tín hiệu field + đại từ*
trong `route_intent._rule_decision`, không phải bằng "câu có dấu hỏi hay không". Vì vậy
**không tin intent của model** — để `route_intent` (đang đạt 0.716) quyết trên field mà model trích.

---

## 1. ĐỊNH NGHĨA CHUẨN advise vs knowledge (bám code repo, dùng làm chân lý)

Nguồn: `src/acne_llm/chat/intent_router.py::_rule_decision`. Diễn giải chính xác:

**`advise`** = có một **ca mụn cụ thể cần tư vấn**, xác định khi CÓ ÍT NHẤT MỘT trong:
- **Personal pronoun về da/mụn của một người cụ thể**: "tôi/mình/em/cháu/con ... bị mụn", "da tôi", "mặt em" (`has_personal_terms`). Chủ thể có thể là bản thân hoặc người thân.
- **Case-signal lâm sàng trích từ CHÍNH message hiện tại** (`has_case_signal` = `_clinical_has_case_signal(current_clinical)`): message nêu loại mụn/vị trí/mức viêm/thời gian/thuốc-sản phẩm đang dùng của một ca thật.
- **Implicit personal**: có case-terms ("bị mụn", "nổi mụn") **kèm** câu hỏi xin cách xử lý ("nên dùng gì", "phải làm sao") → `_implicit_personal`.

**`knowledge`** = câu hỏi **kiến thức chung, KHÔNG gắn ca cụ thể**, xác định khi:
- Hỏi xếp hạng/giải thích ("top 5 nguyên nhân", "liệt kê", "giải thích") mà **không** có personal pronoun → knowledge kể cả khi câu chứa "bị mụn".
- Hỏi về sản phẩm/thực phẩm/cơ chế ("BHA là gì", "ăn socola có nổi mụn không", "tại sao bị mụn") mà **không** có ca cá nhân + case-signal.
- So sánh/đánh giá tổng quát ("A với B khác nhau thế nào", "da dầu dễ bị mụn hơn da khô không") mà **không** có personal pronoun.
- Câu có từ hỏi/dấu "?" nhưng **không** có case-signal.

**Tie-break cuối:** `advise if has_case_signal else knowledge`.

**Điểm mấu chốt (repo khác model):**
1. `has_case_signal` chỉ tính từ **clinical của message hiện tại** (pre-fold), KHÔNG từ user đã fold history — nếu không, mọi turn sau đều thành advise.
2. Câu có dấu "?" hoặc "nên dùng gì" **KHÔNG** tự động là knowledge — nếu có personal pronoun/case-signal thì vẫn advise. (Đây đúng chỗ model sai nhất.)
3. `knowledge` **luôn** đi với `query_subject=non_self`; `advise` có thể self hoặc non_self (hỏi giùm con/bạn).
4. `query_subject` (self/non_self) suy từ **đại từ/ngữ cảnh trong text** (`_subject_signals`), KHÔNG từ việc có field hay không ("con em 2 tuổi bị mụn" → có age+lesion nhưng non_self).

---

## 2. THIẾT KẾ (bỏ intent model, route bằng field model + confidence gate)

### 2.1 Bỏ `route_override_from_llm`
Trong `intake.py`: khi mode=llm vẫn lấy `base_user` + `_extraction_conf` từ model, **nhưng KHÔNG dùng `extracted.route`** cho routing. Xoá/ngừng gán `route_override_from_llm`, để dòng ~581 gọi lại:
```python
route_decision = route_intent(
    clean_text, base_user_for_routing, history,
    settings=getattr(c, "settings", None),
    current_clinical=current_clinical_gated,   # xem 2.2
)
```
`_to_route_decision` trong `llm_extractor.py` có thể giữ lại (để debug/trace) nhưng **không được đưa vào luồng routing**. Ghi rõ comment `# model intent is advisory only, routing decided by route_intent`.

### 2.2 Confidence-gate chống over-extraction (BẮT BUỘC)
Model đang over-extract (skin_type precision 0.30). Nếu `route_intent` đọc `base_user.clinical` thô → `has_case_signal=True` bừa → ép advise sai. Giải pháp: dựng một **clinical đã gate confidence** để truyền vào routing:
- Ngưỡng: `settings.extract_min_field_conf` (mặc định 0.60), có thể đặt riêng `route_case_signal_min_conf` nếu cần.
- Chỉ giữ trong `current_clinical_gated` các giá trị lesion/distribution/inflammation... có `FieldResult.confidence >= ngưỡng` (đọc từ `_extraction_conf`).
- Dùng `ListFieldResult.confident_values(thr)` / `FieldResult.is_confident(thr)` sẵn có.
- `current_clinical_gated` chỉ dùng cho **routing** (quyết advise/knowledge). `base_user` đầy đủ vẫn chảy xuống guardrails/retrieval như cũ (over-extract ở đó là vấn đề riêng, xử lý bằng prompt sau).

> Lưu ý: `route_intent` lấy `current_clinical` (không phải user đã fold). Trong path model,
> `base_user.clinical` chính là clinical của message hiện tại → gate nó rồi truyền vào.

### 2.3 Subject giữ nguyên
`query_subject` do `_subject_signals` trong `route_intent` lo (text-based). KHÔNG lấy từ field. Không sửa phần này.

---

## 3. Ảnh hưởng runtime cần biết khi test (những gì đổi theo intent)

Khi quan sát runtime thật, đây là các điểm advise vs knowledge tạo ra hành vi khác nhau (để biết mình sửa đúng chưa):
- **Template prompt** (`orchestrator.py` ~182): `knowledge` → `knowledge_user.j2`; `advise` → `stream_user.j2`. Misroute = sai hẳn prompt.
- **intake.py**: `advise + self` mới build clinical plan (analytics), lưu `snapshot`, và chạy `check_completeness`. `knowledge` bỏ hết → không hỏi bổ sung, không nhớ hồ sơ.
- **session.py** (~322): `build_confirmed_profile` bỏ qua khi `knowledge`.
- **runtime.py** (~214): `knowledge` → `num_predict=-1` (không cap output).
- Retrieval vẫn chạy cho cả hai (chỉ tắt ở clarify/reject).

---

## 4. GIAO THỨC TEST THẬT (bắt buộc chạy, không chỉ đọc code)

### 4.1 Build lại model từ Modelfile hiện tại
```
ollama create acne-extractor:1.5b -f model/Modelfile.extractor
```
(Modelfile đã được cập nhật; phải rebuild để chắc chắn model phản ánh prompt mới.)

### 4.2 Chạy 3 test case qua RUNTIME THẬT (`run_intake`, mode=llm)
Viết một script tạm `scripts/probe_intent_runtime.py` (hoặc pytest) gọi `run_intake` với `EXTRACTOR_MODE=llm`, in ra: `route_decision.primary_intent`, `query_subject`, `reason_code`, `route_flags`, `effective_mode`, template được chọn (gọi tiếp orchestrator nếu cần), và `completeness`. Ba case:

| Case | clean_text | Kỳ vọng |
|---|---|---|
| A | "em 22 tuổi da dầu bị mụn viêm 2 bên má gần 2 tháng, benzoyl peroxide có nên dùng không" | `advise` + `self` (có personal + case-signal; dấu hỏi KHÔNG được lật sang knowledge) |
| B | "benzoyl peroxide với tretinoin khác nhau thế nào" | `knowledge` + `non_self` |
| C | "con em 2 tuổi bị nổi mụn sữa ở má phải làm sao" | `advise` + `non_self` (ca người thân) |

Đây là 3 mode lỗi chính từ eval vòng 1: A và C là chỗ model hay lật thành knowledge/non_self; B là knowledge thật.

### 4.3 Đọc watch/log thật
Bật log ở mức INFO, đọc dòng `[sid] ROUTE: intent=... subject=... reason=...` và `[sid] EXTRACTOR=llm ok`, xác nhận:
- Routing đến từ `route_intent` (reason_code kiểu `personal_acne_case`/`general_knowledge_or_product_query`/...), KHÔNG phải `llm_extractor`.
- `current_clinical_gated` lọc đúng (case B không được có lesion/distribution confidence cao giả).

---

## 5. QUYẾT ĐỊNH SỬA TIẾP → FIX → TEST LẦN CUỐI → BÁO CÁO

1. Chạy 4.2 lần 1. Đối chiếu kết quả với cột "Kỳ vọng".
2. **Nếu sai trong runtime thật** (ví dụ case A vẫn ra knowledge, hoặc gate không chặn over-extract ở case B):
   - Chẩn đoán: do routing đọc field chưa gate? do `has_personal_terms` không bắt "em/con"? do `current_clinical` truyền sai (đang truyền bản đã fold)? do model vẫn nhả case-signal cho case B?
   - Sửa đúng nguyên nhân (ưu tiên: điểm truyền `current_clinical_gated`, ngưỡng gate, hoặc bổ sung personal-term nếu thiếu). KHÔNG vá bằng cách nhét lại intent của model.
3. Chạy lại 4.2 **một lần cuối** sau khi sửa.
4. Chạy `pytest -q` (không được vỡ test cũ) + eval intent nhanh trên `data/golden_extraction_gen.jsonl`: đo `primary_intent_accuracy`, `query_subject_accuracy`, `joint` cho pipeline mới (route_intent trên field model). So với baseline vòng 1 (llm 0.256 / rule 0.716). Mục tiêu: **≥ rule** hoặc rất sát.
5. Ghi báo cáo `reports/intent_from_fields_round2_<date>.md`: 3 case (trước/sau sửa), nguyên nhân lỗi nếu có, số eval mới vs vòng 1, và kết luận.

---

## 6. File dự kiến đụng
| File | Hành động |
|---|---|
| `src/acne_llm/chat/intake.py` | Bỏ dùng `route_override_from_llm` cho routing; dựng `current_clinical_gated` từ `_extraction_conf`; gọi `route_intent(...)` |
| `src/acne_llm/chat/llm_extractor.py` | Giữ `_to_route_decision` (advisory/debug); thêm helper gate clinical nếu hợp lý |
| `src/acne_llm/config.py` | (tuỳ chọn) `route_case_signal_min_conf` nếu cần ngưỡng riêng |
| `scripts/probe_intent_runtime.py` | TẠO — probe 3 case qua run_intake thật |
| `scripts/eval_extraction.py` | dùng lại, đảm bảo đo intent trên pipeline mới |
| `tests/test_llm_extractor.py` / `tests/test_intent_router*.py` | thêm test: model over-extract confidence thấp KHÔNG ép advise; case A/B/C route đúng |
| `reports/intent_from_fields_round2_<date>.md` | TẠO — báo cáo cuối |

## 7. Ràng buộc tuyệt đối
- KHÔNG dùng `intent` của model cho routing thật (chỉ advisory/debug).
- KHÔNG để routing đọc clinical đã fold history; chỉ dùng clinical message hiện tại đã **gate confidence**.
- KHÔNG sửa `_subject_signals` logic self/non_self trừ khi test chứng minh nó thiếu personal-term ("em/con/cháu").
- KHÔNG đụng cổng guardrail/scope/complaint/medication/override; thứ tự giữ nguyên.
- Phải CHẠY model + runtime thật (mục 4), không kết luận chỉ bằng đọc code.
- Mọi lỗi model → fallback rule như cũ (giữ nguyên cơ chế vòng 1).
