# Codex Handoff — Vòng 3: Semantic (embedding) intent router + bỏ subject

> **Vai trò của bạn (Codex):** hiện thực đúng plan này theo 3 giai đoạn (DATA → RUNTIME → EVAL).
> Tự chạy thật (gen, embed, eval, pytest), sửa nếu sai, rồi báo cáo. Không refactor ngoài phạm vi.
> **Tuyệt đối không đụng guardrail cứng** (thai kỳ/cho bú, vùng sinh dục, drug safety) — chúng chạy trước routing và phải giữ nguyên.

---

## 0. Bối cảnh & mục tiêu

Router intent hiện tại là rule-based (`route_intent`), đạt ~0.716 primary-intent accuracy nhưng giòn (phải vá tay các case như "mụn sữa", "con em"). Mục tiêu: **thay router bằng bộ phân loại embedding (kNN) cho 3 lớp in-scope + phát hiện OOS bằng ngưỡng khoảng cách**, đồng thời **bỏ hoàn toàn trục `query_subject`** khỏi runtime và **bỏ `intent` khỏi model extractor**.

**4 route cuối cùng:** `advise`, `knowledge`, `clarify` (3 lớp phân loại) + `reject` (= OOS, sinh ra từ ngưỡng khoảng cách, KHÔNG phải lớp huấn luyện).

**Quyết định đã chốt (không bàn lại):**
- Embedding runtime: **local embedder** (offline, free). OpenAI **chỉ** dùng để gen data.
- OOS: **ngưỡng khoảng cách embedding THAY** `ood_detector`/`ood_centroid.json`. KHÔNG đụng guardrail cứng.
- Subject: **bỏ hẳn** khỏi runtime (không giữ cờ). Memory fold gate theo `advise`.
- Classifier lưỡng lự (2 lớp sát nhau): **ép thành `clarify`**.
- clarify (router) và completeness: **giữ cả hai, phối hợp để chỉ một câu "hỏi lại" bật mỗi lượt**.

---

## GIAI ĐOẠN 1 — DATA (`data/intent_classify.jsonl`)

### 1.1 Nguồn & lọc
- Copy từ `data/golden_extraction_gen.jsonl` (985 dòng).
- **Bỏ toàn bộ case hỏi giùm:** loại dòng có `query_subject == "other"` (136 dòng) → còn 849.
- **Chỉ giữ 2 field mỗi dòng:** `text`, `intent`. Bỏ hết field extraction (skin_type, sex, age, lesions, …), bỏ `query_subject`, bỏ `reliable` (sau khi dùng nó để lọc — xem dưới).
- **Bỏ các dòng `intent == "reject"`** khỏi tập phân loại (reject không phải lớp; xem 1.4). 
- Với 3 lớp còn lại (advise/knowledge/clarify): dùng `reliable` để **ưu tiên** dòng `reliable==true`; giữ dòng `reliable==false` chỉ khi cần đủ số cho clarify.

### 1.2 Mục tiêu phân bố (gần cân bằng)
| Lớp | Đang có (sau lọc other) | Mục tiêu | Cần gen thêm |
|---|--:|--:|--:|
| advise | 516 | ~500 | 0 (giữ/đủ) |
| knowledge | 209 | **500** | +~290 |
| clarify | 39 | **300** | +~260 |

→ Tổng ~1300 dòng, 3 lớp. Ưu tiên **đa dạng cách diễn đạt** hơn là chạy đủ số: teencode, không dấu, sai chính tả, ngắn/dài, trang trọng/suồng sã.

### 1.3 Sinh data (OpenAI)
- Dùng OpenAI API. **Model đề xuất: `gpt-4o-mini`** (chất lượng đủ, rẻ). Budget trần **~$1–1.5** — ước tính thực tế < $0.5, nên cứ thoải mái; nếu cần chất hơn cho clarify có thể dùng `gpt-4o` cho riêng lớp đó.
- Tái dùng ý tưởng/định nghĩa intent trong `scripts/gen_golden_set.py` (định nghĩa advise/knowledge/clarify đã có ở đó — GIỮ đúng định nghĩa này để nhất quán với nhãn cũ).
- Sinh có kiểm soát theo lớp: prompt yêu cầu model tạo câu **đúng một lớp mục tiêu**, đa dạng phong cách.
- Đọc key từ env (`OPENAI_API_KEY`), có tham số `--budget-usd` để dừng khi vượt; log token/cost.

### 1.4 Tập âm OOS để calibrate ngưỡng (KHÔNG phải lớp huấn luyện)
- Gom `subject_oos_eval.jsonl`: (a) 85 dòng `reject` sẵn có trong golden gốc, + (b) gen thêm ~30–50 câu **rõ ràng ngoài phạm vi** (nấu ăn, thời tiết, chính trị, hỏi chuyện phiếm).
- Dùng để **tìm ngưỡng khoảng cách OOS** ở giai đoạn EVAL. Không đưa vào index kNN.

### 1.5 QC (LLM-judge, theo lô) — GIỮ, nhưng đơn giản
- Sau khi gen, chạy một lượt LLM-judge (`gpt-4o-mini`) trên **các mẫu MỚI sinh**, theo lô, để: (1) xác nhận nhãn đúng lớp, (2) loại mẫu vô tình ngoài phạm vi lọt vào 3 lớp in-scope, (3) khử trùng lặp gần đúng.
- **BỎ** phần "duyệt lại riêng nhãn reject" (không cần — reject không còn là lớp).

### 1.6 Split
- Chia **stratified 80/20** mỗi lớp → `intent_classify.train.jsonl` + `intent_classify.test.jsonl`.
- **Chỉ train split được đưa vào index kNN.** Test split để đo, **không index** (tránh leakage).

---

## GIAI ĐOẠN 2 — RUNTIME

### 2.1 Bộ phân loại embedding (module mới, vd `src/acne_llm/chat/semantic_router.py`)
- Dùng **local embedder** của repo (cùng loại đang dùng cho RAG trong `rag/embedder.py`; nếu embedder đó không tối ưu cho câu ngắn tiếng Việt, đề xuất một local model VN nhẹ và ghi rõ lý do — nhưng phải local, offline).
- Startup: embed sẵn `intent_classify.train.jsonl`, lưu cache (`.npy`/`.pkl`) để không embed lại mỗi lần khởi động. Không cần vector DB.
- Runtime mỗi lượt: embed `clean_text` → **kNN** (k~5–15) trên tập train.
  - **OOS trước:** nếu khoảng cách tới láng giềng gần nhất **> ngưỡng OOS** (`τ_oos`, tìm ở EVAL) → trả `reject`.
  - Ngược lại: vote k láng giềng. Nếu **lưỡng lự** (2 lớp đầu sát nhau — chênh vote/`margin` dưới một mức) → trả `clarify`.
  - Còn lại → lớp thắng (advise/knowledge/clarify).
- Trả về `RouteDecision(primary_intent=..., source="semantic", reason_code="semantic_router", confidence=<điểm tương đồng>)`. **KHÔNG có `query_subject`** (xem 2.3).

### 2.2 Thay ood_centroid + tích hợp vào intake
- Trong `intake.py`, thay chỗ gọi `route_intent(...)` bằng `semantic_router.classify(clean_text)`.
- **Thay** cơ chế OOS mềm cũ (`guardrails/ood_detector.py` + `config/ood_centroid.json`) bằng ngưỡng OOS của router: khảo sát nơi `ood_centroid.json`/`ood_detector` đang được gọi, chuyển quyết định OOS mềm sang router. **Guardrail cứng (pre_check, genital scope, medication/pregnancy refusal) GIỮ NGUYÊN vị trí, chạy trước router.**
- Fallback: nếu embedder lỗi/exception → rơi về `route_intent` cũ (giữ code rule làm fallback, đánh dấu legacy trong docstring). Không để lượt chat vỡ.

### 2.3 Bỏ hẳn subject khỏi runtime
Xoá mọi phụ thuộc `query_subject`:
- `intent_router.py`: bỏ `query_subject`/`_query_subject_for_intent`/`_subject_signals` khỏi luồng chính (giữ file làm fallback nếu cần, nhưng RouteDecision không cần subject).
- `intake.py`: thay `is_self_case = query_subject=="self"` → **`is_personal_case = route_decision.primary_intent == "advise"`**. Dùng `is_personal_case` cho gate: `fold_history_facts`, `build_confirmed_profile`, `snapshot`, `check_completeness` (các dòng ~793, 801, 820, 823, 898). Bỏ các nhánh `query_subject=="self"` ở clarify-override (~876, 919) → dùng `is_personal_case`.
- `prompt_builder.py`: bỏ nhánh `query_subject == "non_self"` (dòng ~107). Thay hint "Không xem là hồ sơ cá nhân" bằng điều kiện `primary_intent == "knowledge"` (knowledge = chung).
- `llm_extractor.py`: bỏ `query_subject` khỏi `_QUERY_SUBJECT`, `_OLLAMA_JSON_SCHEMA`, `_validate_contract`, `_to_route_decision` (xem 2.4).
- `runtime.py` / `api/routes/chat.py`: bỏ đọc `query_subject` trong metadata/telemetry.
- Chấp nhận rủi ro ~14% ca "hỏi giùm" làm bẩn hồ sơ (đã quyết) — **không** thêm cờ other.

### 2.4 Bỏ intent khỏi model extractor (Modelfile + code)
- `model/Modelfile.extractor`: **xoá khối `intent`** trong schema JSON output + trong 3 few-shot; **xoá** mục "Ý nghĩa intent", "Thuật toán intent", "KIỂM TRA CUỐI" (toàn bộ phần dạy intent). Model chỉ còn nhả `context` + `clinical`. Rebuild: `ollama create acne-extractor:1.5b -f model/Modelfile.extractor`.
- `llm_extractor.py`: bỏ `"intent"` khỏi `_OLLAMA_JSON_SCHEMA` + `_validate_contract` + `_INTENT_KEYS`; xoá `_to_route_decision`. Extractor chỉ trả `UserInput` + `ExtractionConfidence`.

### 2.5 clarify vs completeness (phối hợp)
- Router quyết route (gồm clarify). completeness vẫn chạy khi `is_personal_case` (advise).
- **Điều phối một câu hỏi lại:** nếu route=clarify → dùng câu hỏi mở của clarify template; nếu route=advise nhưng completeness thấy thiếu → dùng câu hỏi field-specific của completeness. **Không bao giờ hỏi hai câu cùng lượt.** Đảm bảo logic hiện tại không sinh double-ask sau khi đổi gate sang `is_personal_case`.

---

## GIAI ĐOẠN 3 — EVAL & REPORT

### 3.1 Tìm ngưỡng OOS `τ_oos`
- Trên tập âm `subject_oos_eval.jsonl` (OOS) + test split in-scope: quét `τ_oos`, chọn ngưỡng tối ưu. **Mục tiêu ưu tiên: không bỏ sót in-scope** (giữ recall in-scope cao), chấp nhận vài OOS lọt hơn là chặn nhầm câu hợp lệ. Báo cáo đường cong precision/recall theo ngưỡng.

### 3.2 Đo chất lượng
- Trên **test split** (không index): accuracy 3 lớp (advise/knowledge/clarify) + phát hiện OOS. So với baseline rule 0.716 (primary) — mục tiêu **≥ rule hoặc rất sát**; nếu tụt, báo cáo rõ và giữ fallback rule.
- Đo cả latency mỗi lượt (embed + kNN) để chắc chắn chấp nhận được.

### 3.3 Runtime thật (A/B/C) + regression
Chạy qua `run_intake` thật (embedder local), in route + reason + template:
| Case | text | Kỳ vọng |
|---|---|---|
| A | "em 22 tuổi da dầu bị mụn viêm 2 má gần 2 tháng, benzoyl peroxide có nên dùng không" | advise (→ stream template, completeness chạy) |
| B | "benzoyl peroxide với tretinoin khác nhau thế nào" | knowledge |
| C | "da em dạo này tệ quá" | clarify |
| D | "hôm nay trời mưa có nên đi chơi không" | reject (OOS, vượt ngưỡng) |

- Chạy `pytest -q` — không vỡ test cũ; cập nhật/loại test phụ thuộc `query_subject`.
- Nếu runtime sai → chẩn đoán đúng nguyên nhân (ngưỡng OOS? k? margin clarify? embed cache?), sửa, chạy lại A/B/C/D **một lần cuối**.

### 3.4 Report `reports/semantic_router_round3_<date>.md`
Ghi: phân bố data cuối + số gen + cost thực; `τ_oos` chọn + đường cong; accuracy 3 lớp + OOS trên test vs rule 0.716; latency; kết quả A/B/C/D trước/sau sửa; xác nhận subject đã bỏ sạch, Modelfile đã bỏ intent, guardrail cứng còn nguyên.

---

## Ràng buộc tuyệt đối
- KHÔNG đụng guardrail cứng (pre_check, genital scope, medication/pregnancy refusal) — chỉ thay OOS **mềm**.
- KHÔNG để test split lọt vào index kNN (leakage).
- KHÔNG dùng OpenAI ở runtime — chỉ local embedder; OpenAI chỉ để gen data.
- Giữ `route_intent` cũ làm **fallback** khi embedder lỗi; đánh dấu legacy, đừng xoá.
- Mọi lỗi model extractor → fallback rule như các vòng trước (giữ nguyên cơ chế).
- Budget gen ≤ ~$1.5, có cơ chế dừng khi vượt.
