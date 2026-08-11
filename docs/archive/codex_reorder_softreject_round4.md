# Codex Handoff — Vòng 4: Đảo thứ tự router-trước + Soft reject qua 7B

> **Vai trò của bạn (Codex):** hiện thực đúng plan này, tự chạy runtime thật + pytest, test kỹ các case guardrail an toàn, đo latency trước/sau, rồi báo cáo.
> **Tuyệt đối không nới lỏng guardrail cứng.** Đây là refactor đụng thứ tự an toàn — làm cẩn thận.

---

## 0. Bối cảnh & hai mục tiêu

Hiện `run_intake` chạy theo thứ tự **EXTRACT (1.5B, ~3–8s) → guardrail cứng → SEMANTIC ROUTER → refuse/advise/...**. Vì router giờ là **text-based** (`semantic_router.classify(clean_text)`, không dùng field extract), nên chạy extractor *trước* router là phí: reject/clarify không cần field mà vẫn tốn cú 1.5B (log thật: "goku đẹp trai ko" đã extract xong mới reject).

Ngoài ra, `reject` hiện trả về **một chuỗi cứng** ("Mình chỉ hỗ trợ câu hỏi về mụn…") — khô cứng.

**Hai mục tiêu vòng 4:**
- **A. Đảo thứ tự:** router chạy trước; chỉ extract khi advise/knowledge; giữ lưới safety regex sớm trên mọi lượt.
- **B. Soft reject:** để **7B tự sinh câu từ chối mềm** — thừa nhận ngắn gọn chủ đề của người dùng rồi nói chuyên môn chỉ về mụn, mời hỏi về mụn. Giữ **hard refusal vẫn cứng**.

---

## PHẦN A — Đảo thứ tự (router-first)

### A.1 Thứ tự đích
```
1. preprocess (clean_text)
2. Lưới SAFETY RẺ, chạy trên MỌI lượt (độc lập 1.5B):
   - _extract_safety_terms + regex thai kỳ/cho bú + drug regex (đã có sẵn)
   - Nếu bắt được tín hiệu nguy hiểm rõ (thai kỳ + retinoid/tetracycline, isotretinoin+tetracycline) -> hard refuse NGAY (chuỗi cứng), KHÔNG cần 1.5B, KHÔNG cần router.
3. Gate text rẻ: _is_genital_scope / _is_acne_scope (chỉ cần clean_text)
   - genital-only -> hard refuse (cứng).
4. SEMANTIC ROUTER (text-based, ~244ms) -> route_decision
5. Rẽ nhánh:
   - reject  -> SOFT REFUSE qua 7B (Phần B). KHÔNG extract, KHÔNG RAG.
   - clarify -> template clarify. KHÔNG extract (hoặc extract tối thiểu nếu cần), KHÔNG RAG bắt buộc.
   - advise/knowledge -> EXTRACT (1.5B) BÂY GIỜ:
       6. base_user = llm_extractor.run(...) (fallback rule nếu lỗi)
       7. guardrail cứng phụ thuộc field: pre_check(base_user),
          medication_safety_refusal(user, safety_terms) — chạy TRƯỚC generate
       8. fold (advise) / completeness (advise) / retrieval / prompt / stream 7B
```

### A.2 Nguyên tắc an toàn khi đảo (BẮT BUỘC)
- **Lưới safety regex ở bước 2 phải chạy trước router và độc lập với 1.5B.** Đây là bảo hiểm: kể cả router misroute một câu thai kỳ/thuốc, regex vẫn bắt. Regex này ĐÃ CÓ (`_raw_safety_overrides`, `_raw_safety_lists`, `medication_safety_refusal` phần current-turn) — chỉ cần đảm bảo nó chạy trên clean_text trước router, không phụ thuộc `base_user` từ 1.5B.
- Guardrail cứng cần field đầy đủ (`pre_check`, medication refusal sau fold) vẫn chạy **trên nhánh advise/knowledge sau khi extract**, trước generate. Không bỏ.
- Chỉ **defer cú 1.5B**; KHÔNG defer safety.

### A.3 Dọn dead code
Router text-based nên `current_clinical_gated` / `base_user_for_routing` (gate confidence cho routing, `_confidence_gated_current_clinical`) giờ chỉ còn dùng ở nhánh fallback `route_intent`. Nếu fallback rule vẫn giữ → giữ tối thiểu; nếu không → gỡ. Ghi rõ trong report cái gì đã gỡ.

### A.4 Điểm sửa (intake.py)
- Chuyển block `llm_extractor.run(...)` (dòng ~388) xuống **sau** semantic router, chỉ chạy khi `primary_intent in {"advise","knowledge"}`.
- Đưa lưới safety regex + genital/scope gate lên **trước** router.
- `pre_check` + medication refusal phụ thuộc field: chạy sau extract, trên nhánh advise/knowledge.
- Với reject/clarify: tạo `PreparedChatTurn`/IntakeResult không có extraction (base_user tối giản/None-safe).

---

## PHẦN B — Soft reject qua 7B

### B.1 Hành vi mong muốn
`reject` (OOS mềm từ semantic router) KHÔNG trả chuỗi cứng nữa. Thay vào đó 7B sinh câu **ngắn, thân thiện**: thừa nhận chủ đề người dùng một câu (KHÔNG trả lời/tư vấn về nó) → nói chuyên môn chỉ về mụn → mời hỏi về mụn.

Ví dụ mong đợi:
- "goku đẹp trai ko" → "Goku đúng là được nhiều người mê thật đó! Nhưng mình chỉ chuyên về da mụn thôi, bạn có điều gì về mụn muốn hỏi không?"
- "hôm nay trời mưa có nên đi chơi" → "Trời mưa thì tùy bạn thôi nè. Mình chỉ hỗ trợ về mụn trứng cá, có gì về da mụn mình giúp nhé."

### B.2 Ranh giới (an toàn)
- **Chỉ áp cho reject từ SEMANTIC ROUTER (OOS mềm).** Các **hard refusal** (pre_check, genital, medication/pregnancy, jailbreak) GIỮ chuỗi cứng — không để 7B làm mềm/đối thoại phần nhạy cảm.
- Template phải cấm 7B **trả lời/tư vấn chủ đề ngoài phạm vi**; chỉ thừa nhận 1 câu rồi chuyển hướng. Nếu chủ đề là vấn đề y tế khác → khuyên gặp bác sĩ, không tư vấn.
- reject **không RAG, không completeness, không fold, không snapshot.** Chạy `mode="llm_only"`.

### B.3 Điểm sửa
- **Tạo template mới** `reject_user.j2` (cạnh `clarify_user.j2`, `knowledge_user.j2`, `stream_user.j2`). Nội dung: đưa `clean_text` + chỉ dẫn soft-refuse (thừa nhận ngắn, không trả lời chủ đề, nói chỉ chuyên mụn, mời hỏi mụn, tối đa 2–3 câu, giọng thân thiện).
- **orchestrator.py** (chỗ chọn template ~182): thêm nhánh `elif primary_intent == "reject": template = "reject_user.j2"` và cho nó **đi tiếp vào generate** thay vì early-return refusal. Đặt `should_retrieve=False` cho reject.
- **intake.py**: semantic reject KHÔNG set `scope_refusal` (cái đó dành hard refuse); thay vào đó set `effective_mode` cho phép generate + template reject. Prompt builder nhận reject → dựng prompt từ `reject_user.j2`.
- **runtime.py**: nhánh reject stream 7B bình thường (như clarify/knowledge), không cap đặc biệt; kết thúc không kèm citation.
- Prompt builder: đảm bảo reject KHÔNG chèn known_facts/clinical (không có extraction) và KHÔNG chèn chunk RAG.

> Lưu ý: SYSTEM của model 7B (`model/Modelfile`) đã có luật "chỉ tư vấn da mụn; từ chối lịch sự phần ngoài phạm vi" + chống jailbreak → template reject chỉ cần steer giọng, không cần lặp luật an toàn.

---

## PHẦN C — Test & Report

### C.1 Guardrail an toàn (BẮT BUỘC pass — chứng minh đảo thứ tự không hở)
Chạy runtime thật, xác nhận vẫn **hard refuse** (chuỗi cứng, KHÔNG qua soft reject) cho:
- thai kỳ + tretinoin/isotretinoin
- cho con bú + retinoid
- isotretinoin + doxycycline
- vùng sinh dục
Xác nhận các case này **refuse trước cả router/extract** (nhờ lưới safety regex sớm), không lọt.

### C.2 Latency reject/clarify trước/sau
Đo latency lượt "goku đẹp trai ko" (reject) và một câu clarify: trước (có extract) vs sau (không extract). Kỳ vọng giảm ~cú 1.5B (vài giây).

### C.3 Soft reject chất lượng
Chạy 3–5 câu OOS ("goku đẹp trai ko", "z t đẹp trai ko", "trời mưa có nên đi chơi", "1+1 bằng mấy") → xác nhận 7B ra câu **mềm, thừa nhận + chuyển hướng về mụn**, KHÔNG trả lời chủ đề, KHÔNG RAG.

### C.4 Không regress
- advise/knowledge/clarify vẫn đúng route + template + completeness như vòng 3 (A/B/C/D).
- `pytest -q` xanh; cập nhật test nào giả định reject trả chuỗi cứng.

### C.5 Report `reports/reorder_softreject_round4_<date>.md`
Ghi: thứ tự mới (sơ đồ), xác nhận lưới safety chạy sớm + 4 case guardrail vẫn refuse cứng, latency reject/clarify trước/sau, ví dụ soft reject, dead code đã gỡ, kết quả A/B/C/D + pytest.

---

## Ràng buộc tuyệt đối
- KHÔNG defer/bỏ safety: lưới regex thai kỳ/thuốc chạy sớm trên mọi lượt; guardrail cứng cần field chạy trước generate trên nhánh advise/knowledge.
- Soft reject CHỈ cho OOS mềm từ semantic router; hard refusal giữ chuỗi cứng.
- reject soft: llm_only, không RAG/completeness/fold; template cấm trả lời chủ đề ngoài phạm vi.
- Giữ fallback rule + fallback extractor như các vòng trước.
- Mọi thay đổi phải test runtime thật, không chỉ đọc code.
