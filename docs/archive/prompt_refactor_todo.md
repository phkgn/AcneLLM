# TODO: Tách prompt — Modelfile định nghĩa hành vi, repo chỉ gửi context

Mục tiêu: **Modelfile SYSTEM là nguồn sự thật duy nhất** cho role / guardrail / phạm vi /
phong cách / ngôn ngữ / triết lý grounding của AcneLLM. **Prompt phía repo KHÔNG ràng buộc
hành vi model nữa** — chỉ đóng gói và gửi càng nhiều, càng đúng thông tin model cần để trả lời
(user message, dữ kiện đã biết, safety facts, KB context, lịch sử), dưới dạng các khối dữ liệu
có nhãn rõ ràng.

---

## 0. Bối cảnh đã xác minh (đọc trước khi làm)

- `config.py:45` → `llm_use_modelfile_system = True` (ĐÃ bật).
- `ollama_backend.py:_build_messages()` khi cờ bật → chỉ gửi `[{role:user}]`, **bỏ system message**.
  ⇒ `PromptBuilder.system()` / `system_stream()` / `system.j2` / `system_core.j2` /
  `system_stream.j2` **hiện là code chết** cho luồng chat chính (`di.py:106`).
- Ràng buộc thực tế đang tới model nằm ở **user template**: `stream_user.j2`, `knowledge_user.j2`,
  `hybrid_user.j2`, `llm_only_user.j2`, `clarify_user.j2` + `system_extended.j2` (nhét qua
  `extended_rules` vào user message).
- Hybrid/llm_only dùng `generate_json(..., format=schema)` → **shape JSON đã được grammar ép cứng**,
  không cần prompt mô tả cấu trúc. Chỉ còn *ngữ nghĩa field* (confidence, causes≤4, citation `[N]`)
  là cần hướng dẫn.
- `qa_generator.py:230` và path eval tự dựng `OllamaBackend` riêng — kiểm tra cờ
  `use_modelfile_system` ở các chỗ này (có thể khác luồng chat).

---

## 1. Chốt 1 quyết định thiết kế (chặn các bước sau)

**Hợp đồng định dạng output (JSON schema semantics, citation `[N]`, plaintext vs JSON) đặt ở đâu?**
Đây là vùng xám duy nhất: nó *đặc thù theo endpoint* (hybrid=JSON, stream=plaintext) nên
**không thể** nhét hết vào một Modelfile dùng chung.

- **Phương án A (khuyến nghị):** Modelfile = role/guardrail/scope/style/ngôn ngữ/grounding
  (bất khả tri về format). Repo giữ lại **một hợp đồng output tối thiểu** cho mỗi endpoint
  (JSON field semantics cho hybrid, "trả plaintext" cho stream, format `[N]` khi có KB).
  Coi đây là *format contract* (thông tin model cần), **không phải** guardrail hành vi.
- **Phương án B:** Tách 2 biến thể model (một cho JSON, một cho stream) mỗi cái có Modelfile
  SYSTEM riêng → repo sạch tuyệt đối nhưng tốn VRAM/bảo trì gấp đôi.

→ Ghi rõ lựa chọn vào đây trước khi code. Phần còn lại của plan giả định **Phương án A**.

---

## 2. Phân loại: cái gì về Modelfile, cái gì ở lại repo

| Nội dung hiện tại | Đích | Ghi chú |
|---|---|---|
| Role "Bạn là AcneLLM…" | **Modelfile** | |
| Phạm vi trả lời (chỉ da mụn, từ chối vùng kín/ngoài phạm vi) | **Modelfile** | gộp cả `query_subject`, `mixed_genital_scope` guidance |
| An toàn: không kê đơn/liều, không tự nặn/chích/lăn kim, nodule/cyst/sẹo/nhiễm trùng → bác sĩ | **Modelfile** | |
| Thai kỳ/cho con bú: cấm retinoid/isotretinoin/… | **Modelfile** | |
| Tuổi <12 → bác sĩ da liễu nhi; an toàn trẻ sơ sinh | **Modelfile** | thay `pediatric_safety` block trong `knowledge_user.j2` |
| Chống jailbreak ("act as"/"DAN"/"ignore previous") | **Modelfile** | |
| Ngôn ngữ: LUÔN tiếng Việt 100%, dịch cả nguồn EN/CN | **Modelfile** | |
| Phong cách: ngắn gọn, thẳng vấn đề, disclaimer 1 lần | **Modelfile** | |
| Grounding: chỉ kết luận từ dữ kiện + context; không bịa tên nguồn; thứ tự ưu tiên nguồn | **Modelfile** | triết lý chung |
| Thang confidence (0.7–0.9 / 0.4–0.6 / …) | **Repo (format contract)** | chỉ có nghĩa với schema JSON |
| Ràng buộc JSON field: causes≤4, recommendations≤5, `source_chunk_id` từ `chunk_ref` | **Repo (format contract)** | đặc thù hybrid/llm_only |
| Citation inline `[N]` khớp `[Nguon N]` | **Repo (format contract)** | chỉ khi có KB |
| "Chỉ giải quyết current_message; recent_context để hiểu follow-up" | **Repo (nhãn khối)** | diễn đạt bằng NHÃN, không phải mệnh lệnh (xem §4) |
| Sanitization: `_escape_jinja`, `_sanitize_chunk_text`, neutralize injection markers | **Repo (BẮT BUỘC giữ)** | vệ sinh dữ liệu, không phải chỉ thị model |

---

## 3. Viết lại `model/Modelfile` SYSTEM

- [ ] Gộp toàn bộ dòng "Modelfile" ở bảng §2 thành 1 SYSTEM prompt mạch lạc, có cấu trúc mục
  (Vai trò / Phạm vi / An toàn / Thai kỳ / Trẻ em / Chống jailbreak / Ngôn ngữ / Grounding / Phong cách).
- [ ] Viết **bất khả tri về format**: không nhắc "JSON" hay "plaintext" (vì dùng chung 2 endpoint).
- [ ] Đồng bộ cùng nội dung sang `model/V2/Q4/Modelfile` và `model/V2/Q2/Modelfile` (đang có 2 biến thể lượng tử hóa).
- [ ] Giữ nguyên block PARAMETER/TEMPLATE hiện có; **không** set sampling ở Modelfile nếu quy ước
  dự án là "Python là source of truth" (xem comment `ollama_backend.py:29`). Xác nhận quy ước rồi mới đụng.
- [ ] Backup file cũ (đã có `Modelfile.bak.*` — theo nếp đó).

## 4. Dọn user template → chỉ còn khối dữ liệu có nhãn

Nguyên tắc: mỗi template chỉ còn (a) các khối `<...>`/`[NHÃN]` chứa dữ liệu, (b) tối thiểu
format contract của §1-A. **Bỏ hết** câu mệnh lệnh về an toàn/ngôn ngữ/phong cách/grounding
(đã nằm ở Modelfile).

- [ ] `stream_user.j2`: bỏ mục "[YÊU CẦU TRẢ LỜI]" phần an toàn/ngôn ngữ/disclaimer/grounding;
  giữ các khối dữ kiện (confirmed_safety_facts, known_facts, route_metadata guidance, completeness_hint,
  history_block, retrieved_context, current_message). Giữ đúng 1 dòng format contract: "khi có
  [TÀI LIỆU], đặt `[N]` sau claim".
- [ ] `knowledge_user.j2`: bỏ block "[AN TOÀN CHO TRẺ SƠ SINH]" (chuyển sang Modelfile) và các
  mệnh lệnh phạm vi; giữ history_block + retrieved_context + current_message + contract `[N]`.
- [ ] `hybrid_user.j2` + `llm_only_user.j2`: giữ khối dữ liệu; rút gọn `<task>` xuống chỉ còn
  JSON field-semantics contract (causes≤4, recommendations≤5, source_chunk_id nguồn gốc).
- [ ] `clarify_user.j2`: giữ khối dữ liệu; "hỏi đúng 1 câu" là format contract của endpoint clarify → giữ.
- [ ] Chuyển các mệnh lệnh dạng "chỉ giải quyết current_message" thành **nhãn khối** thay vì lệnh,
  ví dụ `<current_message>` vs `<recent_context_chi_de_hieu_followup>` — ngữ nghĩa nằm ở tên khối.
- [ ] Đảm bảo template vẫn nhận đủ mọi biến `PromptBuilder.build()` truyền vào (đừng bỏ sót dữ liệu
  hữu ích — mục tiêu là *gửi nhiều thông tin đúng hơn*, không phải cắt dữ liệu).

## 5. Dọn `PromptBuilder` + code đường dẫn system

- [ ] Bỏ/đơn giản hóa `system()`, `system_stream()`, `_extended_rules()`,
  `system_override` (prompt_builder.py:416-447, 466-473) — vì `use_modelfile_system=True`
  khiến `sys_p` bị vứt. Có thể trả `sys_p=""`.
- [ ] `orchestrator.py:214` đang set `system_override=system_stream()` → gỡ (vô tác dụng khi cờ bật).
- [ ] Xóa file chết: `system.j2`, `system_core.j2`, `system_stream.j2`, `system_extended.j2`
  **sau khi** xác nhận không path nào (eval/judge/qa_generator) còn dùng. `grep -rn` trước khi xóa.
- [ ] Kiểm tra `qa_generator.py:230` và eval: nếu chúng vẫn cần system prompt (không dùng Modelfile),
  quyết định giữ 1 template riêng cho *offline datagen/eval* (không thuộc luồng serving) — đây là
  ngoại lệ hợp lệ, ghi chú rõ.
- [ ] GIỮ nguyên toàn bộ hàm sanitization (§2) — không đụng.

## 6. Kiểm thử & hồi quy (bắt buộc)

- [ ] **Trước khi sửa**: chạy bộ câu hỏi mẫu (an toàn: thai kỳ + retinoid; nodule → bác sĩ; jailbreak
  "act as"; ngoài phạm vi; câu hỏi kiến thức có/không KB; hybrid JSON) → lưu output làm baseline.
- [ ] `ollama create` lại model từ Modelfile mới (cả Q4/Q2). Verify bằng `/api/show` (đã có
  `show_params()`) rằng SYSTEM mới đã nạp.
- [ ] Chạy lại đúng bộ trên → **diff** với baseline. Guardrail (kê đơn/thai kỳ/nodule/jailbreak/
  tiếng Việt) phải giữ nguyên hoặc tốt hơn.
- [ ] Chạy `pytest` (đặc biệt test guardrails/prompt) + `ruff`.
- [ ] Chạy harness eval hiện có (`run_eval_overnight.bat` / judge.j2) so điểm trước–sau.
- [ ] Xác nhận citation `[N]` vẫn xuất hiện khi có KB (runtime.py:261 có check regex `\[\d+\]`).

## 7. Dọn dẹp & tài liệu

- [ ] Cập nhật `CODEBASE_AUDIT.md` / `context.md` phản ánh kiến trúc mới (Modelfile = hành vi,
  repo = context).
- [ ] Ghi lại quyết định §1 (A hay B) như một ADR ngắn.
- [ ] Xóa `Modelfile.bak.*` cũ nếu không cần.

---

## Rủi ro cần canh

- **Guardrail suy giảm**: chuyển rule sang SYSTEM có thể khiến model 7B tuân kém hơn so với khi
  rule nằm sát user message. Đây là lý do §6 baseline-diff là bắt buộc, không bỏ qua.
- **num_ctx 8192 nhỏ**: SYSTEM dài luôn chiếm chỗ mỗi request. Lợi: user message gọn hơn nhiều
  (bỏ rule lặp) → thường **tiết kiệm** token ròng. Đo lại độ dài prompt trước–sau.
- **Hai biến thể lượng tử (Q2/Q4)**: nhớ đồng bộ SYSTEM cả hai, tránh lệch hành vi.
