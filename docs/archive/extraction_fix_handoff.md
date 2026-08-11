# Handoff: Sửa chất lượng rule-based extractor (AcneLLM)

> Tài liệu này dành cho một AI agent khác (hoặc dev) tiếp nhận và implement.
> Mọi số liệu dưới đây đã được **chạy thật trên 985 câu** của `data/golden_extraction_gen.jsonl`,
> không phải ước lượng. File code cần sửa: `src/acne_llm/chat/normalizer.py`.

---

## 0. Bối cảnh & nguyên tắc

- Pipeline extract thông tin lâm sàng (mụn) từ câu tiếng Việt = **rule regex** trong `normalizer.py`, bọc confidence ở `extraction_confidence.py`.
- Eval: `python scripts/eval_extraction.py --golden data/golden_extraction_gen.jsonl`
- Golden được sinh bằng LLM (gen/DeepSeek), gán nhãn theo **ngữ nghĩa suy luận + canonical tiếng Anh**.
  → Coi semantics của golden là **target chính thức**. Việc cần làm là kéo rule về đúng target, KHÔNG phủ nhận golden.

**Nguyên tắc khi sửa:**
1. KHÔNG phá `normalize_chat_message()` và schema `UserInput` (extraction_confidence.py bọc quanh, không được vỡ API).
2. Mỗi task: sửa → chạy lại eval → so số trước/sau → chỉ giữ nếu field mục tiêu tăng VÀ không field nào tụt đáng kể.
3. Setup môi trường eval cần: `pip install pydantic rank_bm25 rapidfuzz --break-system-packages`.

## Baseline hiện tại (985 câu)

```
Scalar (accuracy)
  skin_type        0.871   sex 0.804   age 0.968   duration_weeks 0.935
  is_pregnant      0.809   is_breastfeeding 0.825
  inflammation     0.501   ← YẾU (gold_has 398)
List (micro P/R/F1)
  lesions          P0.671 R0.686 F10.678
  distribution     P0.961 R0.842 F10.898  ✓
  products         P0.220 R0.593 F10.321  ← YẾU (fp 407)
  medications      P0.296 R0.889 F10.444  (n nhỏ, để cuối)
  allergies        P0.425 R0.676 F10.522  (n nhỏ)
  scarring_signs   P0.789 R0.946 F10.861  ✓
  hormonal_factors P0.768 R0.673 F10.717  ✓
  treatment_goals  P0.473 R0.241 F10.320  ← YẾU (fn 610)
  red_flags        P0.495 R0.580 F10.535  ← YẾU
```

---

## TASK 1 — inflammation (ROI ★★★★★, làm ĐẦU TIÊN)

**Mục tiêu:** acc 0.501 → ~0.85. Hàm: `_extract_inflammation()` (normalizer.py ~dòng 1404).

### Bằng chứng (confusion matrix, eval-normalized none/unknown→None)
```
gold\pred    None   mild  moder  severe
 None         233    259    69     26     ← 587 câu gold=None, SAI 354
 mild           0     21    60      5     ← mild rò sang moderate (60)
 moderate       3      7    94     39
 severe         4      2    18    145
```

### Ba lỗi cần sửa
1. **Over-fire trên None/unknown (354 ca — lỗi lớn nhất).** Rule suy inflammation từ từ vựng có trong câu hỏi *kiến thức* (vd "phân biệt mụn viêm và không viêm"). 
   - **Fix:** Thêm gate ngôi-thứ-nhất. Chỉ chạy inference khi câu mô tả tình trạng bản thân ("da tôi/em/mình bị…", "tôi đang bị…"). Nếu là câu hỏi kiến thức chung (không có chủ thể ngôi-1 + có dấu hiệu hỏi định nghĩa "là gì/phân biệt/khác nhau") → trả `unknown`/`None`.
2. **Không có path "none".** Cột `none` toàn 0. Gold gán `none` cho mụn không viêm (đầu đen/đầu trắng/comedone, "không sưng không đau").
   - **Fix:** Thêm nhánh trả `"none"` khi chỉ có comedonal lesion / cụm "không viêm, không sưng, không đau" và không có tín hiệu viêm.
3. **mild rò sang moderate (60 ca).** `_moderate_signal` quá tham — "có viêm"/"mụn đỏ sưng" fire cả khi câu thực ra mild.
   - **Fix:** Siết `_moderate_signal`; ưu tiên `_has_mild_signal` (đã có) trước khi suy moderate từ lesion type. Kiểm tra thứ tự if hiện tại.

### Verify
Chạy lại eval, kỳ vọng inflammation ≥ 0.82 và scalar tổng tăng rõ. Dùng script `tools/diag_extract.py` (mục cuối) để in lại confusion matrix sau khi sửa.

---

## TASK 2 — products (ROI ★★★★★, rẻ nhất)

**Mục tiêu:** P 0.220 → ~0.5. Hàm: `_extract_products()` + `_PRODUCT_TERMS` (normalizer.py ~1212).

### Bằng chứng
```
Top FP: kem(56) retinol(39) salicylic(30) bha(29) sua rua mat(20) kem duong(20)
        kem chong nang(15) tinh nghe(13) vitamin c(13) tretinoin(12) serum(11)
Top FN: cleanser(23) moisturizer(18) BHA(16) sunscreen(13)
```

### Hai lỗi (lỗi a là chính)
**(a) Lệch canonical VN↔EN — gây ĐỒNG THỜI fp lẫn fn.** Gold dùng nhãn tiếng Anh; rule sinh raw tiếng Việt. CÙNG khái niệm, khác chuỗi:
   - `sua rua mat` (20 fp) ↔ `cleanser` (23 fn) = cùng một thứ
   - `kem duong`/`duong am` (36 fp) ↔ `moisturizer` (18 fn)
   - `kem chong nang` (15 fp) ↔ `sunscreen` (13 fn)
   - `salicylic`/`bha` ↔ `BHA`
   - **Fix:** Build map canonical hoá output về label-space của gold (tiếng Anh):
     ```
     sua rua mat / sữa rửa mặt → cleanser
     kem duong / duong am / kem dưỡng / dưỡng ẩm → moisturizer
     kem chong nang / kem chống nắng / spf → sunscreen
     salicylic / salicylic acid / bha → BHA
     aha / glycolic → AHA
     vitamin c → vitamin C
     retinol/tretinoin/retinoid → giữ nguyên (gold có dùng các nhãn này? kiểm tra trước)
     ```
   - **QUAN TRỌNG:** Trước khi map, đếm label-space thật của gold:
     `python -c "import json,collections; c=collections.Counter(); [c.update(json.loads(l).get('products',[])) for l in open('data/golden_extraction_gen.jsonl',encoding='utf-8')]; print(c.most_common(40))"`
     Map đúng theo nhãn gold thực tế, đừng đoán.

**(b) Over-extract trên câu hỏi.** retinol/benzoyl peroxide/tretinoin/vitamin c fire khi sản phẩm chỉ được *hỏi/nhắc* chứ không *dùng*. `_has_product_use_context` còn rò.
   - **Fix:** Sau khi xong (a), xem fp còn lại; siết usage-gate cho nhóm hoạt chất (chỉ tính khi có "đang/đã/mới dùng/bôi").

### Verify
Eval lại, kỳ vọng products P ≥ 0.45, F1 ≥ 0.45. Theo dõi fp giảm mạnh (407 → ~200).

---

## TASK 3 — treatment_goals (ROI ★★★★☆)

**Mục tiêu:** R 0.241 → ~0.55. Hàm: `_extract_treatment_goals()` + `_TREATMENT_GOAL_TERMS` (~692, ~1365).

### Bằng chứng
```
FN by label: clear_acne(264) reduce_inflammation(90) see_doctor(64)
             product_recommendation(55) treat_scar(49) fade_hyperpigmentation(33)
             build_routine(23) prevent_acne(20) reduce_oiliness(8) hydration(4)
FP by label: clear_acne(58) product_recommendation(52) hydration(32) see_doctor(30) build_routine(22)
```

### Hai lỗi
**(a) Gold có label rule KHÔNG sinh ra (miss 100%):** `see_doctor`(64), `product_recommendation`(55), `build_routine`(23), `prevent_acne`(20). `_TREATMENT_GOAL_TERMS` thiếu hẳn các nhãn này.
   - **Fix:** Thêm các label:
     - `see_doctor`: derive từ red_flags nặng/inflammation=severe, hoặc cụm "có nên đi khám/bác sĩ".
     - `product_recommendation`: cụm "nên chọn/dùng sản phẩm gì", "tư vấn sản phẩm".
     - `build_routine`: "xây dựng routine/quy trình chăm sóc", "các bước skincare".
     - `prevent_acne`: "phòng ngừa/ngăn mụn", "tránh bị mụn".

**(b) clear_acne 264 FN = gold suy từ intent.** Vd: *"tôi bị mụn trùng cả mặt... bạn tư vấn được không"* → gold=clear_acne dù không có cụm "trị mụn".
   - **Fix:** Mặc định gán `clear_acne` khi user mô tả đang bị mụn + tìm cách xử lý (intent = seek-treatment), không đòi phrase tường minh "trị mụn".
   - **Cảnh báo:** đừng quá tay làm FP clear_acne tăng vọt. Gate bằng: có mô tả ngôi-1 bị mụn + câu hỏi xin lời khuyên.

### Verify
Eval lại, kỳ vọng treatment_goals R ≥ 0.50, F1 ≥ 0.45. Kiểm tra P không tụt dưới 0.40.

---

## TASK 4 — red_flags (ROI ★★★☆☆)

**Mục tiêu:** F1 0.535 → ~0.65. `_RED_FLAG_TERMS` + `_extract_red_flags()` (~837, ~1348).

### Bằng chứng
```
FP: skin_irritation(73) purulent_lesions(53) chronic(49) widespread(39) scarring_risk(28)
FN: painful_lesions(101!) treatment_failure(32) purulent_lesions(22) widespread(22)
```

### Lỗi
- **painful_lesions 101 FN:** pattern đòi intensifier ("đau nhiều/rất đau"); gold gắn cờ với "đau" trơn. → Nới: "đau" đơn thuần trong ngữ cảnh mụn cũng tính.
- **skin_irritation(73)/chronic(49)/widespread(39) FP:** từ rộng ("kích ứng/lâu rồi/khắp") fire trên câu giáo dục. → Siết về ngữ cảnh ngôi-1 mô tả triệu chứng thật.

### Verify
Eval lại, kỳ vọng red_flags F1 ≥ 0.62, fp giảm, painful_lesions fn giảm mạnh.

---

## TASK 5 — Quyết định kiến trúc (làm song song, rẻ)

Ghi chính thức vào doc dự án: **semantics của golden (canonical EN + suy-luận intent) là target.** Mọi task trên đều kéo rule về target này. Không cần chuyển sang LLM extract cho treatment_goals — các tín hiệu đều suy được bằng rule.

medications / allergies: **để cuối**, n quá nhỏ (gold 27, 71), tối ưu dễ overfit. Mở rộng test set trước khi tin metric.

---

## Script diagnostic dùng lại (tools/diag_extract.py)

Lưu file này để in confusion matrix + top fp/fn bất cứ lúc nào:

```python
import json, sys, collections
sys.path.insert(0, "src")
from acne_llm.chat.extraction_confidence import extract_with_confidence

rows = [json.loads(l) for l in open("data/golden_extraction_gen.jsonl", encoding="utf-8") if l.strip()]
def ninf(v): return None if v in (None,"none","unknown") else v
cm = collections.Counter()
fp = collections.defaultdict(collections.Counter); fn = collections.defaultdict(collections.Counter)
for r in rows:
    t = r.get("text","")
    if not t: continue
    ec = extract_with_confidence(t)
    cm[(str(ninf(r.get("inflammation"))), str(ninf(ec.inflammation.value)))] += 1
    for f, pv in [("products",ec.products),("treatment_goals",ec.treatment_goals),
                  ("red_flags",ec.red_flags)]:
        g=set(r.get(f,[]) or []); p=set(pv.values)
        for x in p-g: fp[f][x]+=1
        for x in g-p: fn[f][x]+=1
nl=["None","mild","moderate","severe"]
print("INFLAMMATION  gold\\pred", nl)
for g in nl: print(f"{g:>9}", [cm.get((g,p),0) for p in nl])
for f in ["products","treatment_goals","red_flags"]:
    print(f"\n{f} FP:", fp[f].most_common(15))
    print(f"{f} FN:", fn[f].most_common(15))
```
Chạy: `python tools/diag_extract.py`

## Thứ tự thực hiện
1 (inflammation) → 2 (products) → 3 (treatment_goals) → 4 (red_flags). Sau mỗi task: eval + so số. Commit riêng từng task để dễ revert.
