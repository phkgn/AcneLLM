---
title: AcneLLM Defense — 16-slide E2E Context
status: current-proposed
as_of: 2026-08-25
source_head: 487a7f614e628b804e693992060465fe54275e37
audit_run: 20260825T090826Z
primary_thesis: E:/FINAL_KL_2026_REVISED_20260825.docx
---

# AcneLLM — context chi tiết cho 16 slide bảo vệ

## Nguyên tắc trình bày

- Luận điểm xuyên suốt: **AcneLLM là prototype nghiên cứu local-first, tách Intake — Retrieval — Generator — Safety để đo và truy vết từng nút thắt.**
- Không gọi hệ thống là công cụ chẩn đoán, kê đơn, an toàn lâm sàng hay production-ready.
- Kết quả `v2_full` là artifact giao thức lịch sử ngày 22/08/2026, chưa chạy lại toàn bộ sau remediation.
- `pytest 495 passed, 1 xfailed` chứng minh regression hiện tại, không thay cho endpoint/T4/SSE parity hoặc đánh giá y khoa.
- Mỗi slide chỉ có một claim chính; phần chi tiết và nguồn nằm trong speaker notes.

## Slide 1 — AcneLLM

**Claim chính:** AcneLLM là hệ thống tiếng Việt hỗ trợ cung cấp thông tin về mụn trứng cá, vận hành local-first và có giới hạn trách nhiệm rõ ràng.

**Nội dung hiển thị:**

- Tên đề tài: *Tìm hiểu LLM, xây dựng mô hình đưa ra lời khuyên về các loại da mụn*.
- Tên hệ thống: **AcneLLM**.
- Nhóm thực hiện: Phan Gia Khang — 23DH111507; Lê Minh Đăng Khoa — 23DH114386.
- GVHD: ThS. Phan Thị Ngọc Hân.
- Một câu phạm vi: “Hỗ trợ thông tin — không chẩn đoán, không kê đơn, không thay thế bác sĩ.”

**Visual:** Tiêu đề tối giản, một trục nhỏ `Intake → RAG → Generator → Safety`, không dùng ảnh stock.

**Context nói:** Mở bằng phạm vi thay vì hứa hẹn quá mức. Nhấn mạnh đây là đề tài vừa nghiên cứu LLM/QLoRA, vừa xây dựng hệ thống có frontend, backend, model runtime, knowledge base và evaluation. Câu chuyển: “Vì sao một chatbot mụn cần nhiều lớp hơn một LLM thông thường?”

**Nguồn:** `E:/FINAL_KL_2026_REVISED_20260825.docx`; `README.md`; `.audit/CURRENT_TRUTH.md`.

## Slide 2 — Bài toán không chỉ là sinh câu trả lời tự nhiên

**Claim chính:** Giá trị và rủi ro xuất hiện đồng thời: LLM giao tiếp tự nhiên, nhưng miền chăm sóc da có sai số tri thức, tín hiệu lâm sàng khó và nguy cơ khuyến nghị quá mức.

**Nội dung hiển thị:**

| Nhu cầu | Rủi ro kỹ thuật | Hệ quả thiết kế |
|---|---|---|
| Hỏi bằng tiếng Việt tự nhiên | Câu hỏi thiếu dữ kiện, nhiều ý định | Cần Intake + session context |
| Thông tin chăm sóc da | Hallucination, nguồn không rõ | Cần RAG + truy vết nguồn |
| Cá nhân hóa hội thoại | Thai kỳ, dị ứng, thuốc, viêm nặng | Cần hard guardrails + referral |
| Phản hồi nhanh và riêng tư | Phụ thuộc cloud/dữ liệu nhạy cảm | Local Ollama + audit có che PII |

**Visual:** Chuỗi nhân quả `LLM linh hoạt → rủi ro miền y tế → kiến trúc tách lớp`, kèm ba điểm đỏ: thuốc, tín hiệu nặng, khẳng định chẩn đoán.

**Context nói:** Không nói AcneLLM giải quyết hoàn toàn rủi ro. Slide này chỉ chứng minh vì sao không thể “đưa câu hỏi thẳng vào LLM”. Phạm vi da mụn có các trường hợp retinoid/isotretinoin, mang thai/cho con bú, dị ứng và viêm nặng nên phải có đường từ chối/chuyển tuyến.

**Nguồn:** DOCX đoạn Đặt vấn đề/Lý do chọn đề tài; `src/acne_llm/chat/_intake_hard_safety.py`; `src/acne_llm/safety/`; `src/acne_llm/storage/`.

## Slide 3 — Mục tiêu là prototype có thể đo, không phải bác sĩ số

**Claim chính:** Đề tài xây dựng và đánh giá một chuỗi E2E; đóng góp nằm ở khả năng tách trách nhiệm, kiểm thử và truy vết.

**Nội dung hiển thị:**

| Làm | Không làm | Đóng góp kiểm chứng được |
|---|---|---|
| Chatbot tiếng Việt về mụn | Phân tích ảnh/vision | Hai model chuyên trách |
| QLoRA ROLE + Intaker | Chẩn đoán chính thức | Hybrid retrieval có provenance |
| FastAPI + Next.js + Ollama | Kê thuốc/kê liều | Safety nhiều tầng + SSE/audit |
| Đánh giá Intake/Retrieval/Ablation | Clinical trial/production claim | Giao thức đánh giá phân rã |

**Context nói:** Mục tiêu lý thuyết là hiểu LLM, PEFT/LoRA/QLoRA và áp dụng vào hệ thống. Mục tiêu hệ thống là xây dựng runtime local-first. Mục tiêu đánh giá là trả lời bốn RQ: Intake, Retrieval, đóng góp component và độ ổn định/an toàn. Đóng góp không phải “độ chính xác y khoa đã được chứng minh”.

**Nguồn:** DOCX mục Mục tiêu, Phạm vi, Đóng góp; DOCX Bảng 1.1; `.audit/SLIDE_FACT_CHECK_2026-08-25.md`.

## Slide 4 — Từ mô hình nền đến hệ thống chuyên biệt

**Claim chính:** LLM chỉ là năng lực nền; AcneLLM hình thành từ ba lớp thích nghi: hành vi, tri thức theo truy vấn và kiểm soát hệ thống.

**Nội dung hiển thị:**

1. **Foundation LLM:** Transformer decoder-only, instruction-tuned, sinh token theo ngữ cảnh.
2. **Behavior adaptation:** QLoRA/LoRA định hướng JSON Intake và vai trò/giọng ROLE.
3. **Knowledge adaptation:** RAG đưa tối đa 5 đoạn liên quan vào prompt tại thời điểm hỏi.
4. **System adaptation:** routing, session, safety, SSE và persistence biến model thành ứng dụng.

**Visual:** Bốn lớp đồng tâm hoặc pipeline `Qwen2.5 → QLoRA → RAG/prompt → AcneLLM runtime`; ghi chú “fine-tune hành vi ≠ xác nhận tri thức y khoa”.

**Context nói:** Lý thuyết chỉ đủ để giải thích quyết định thiết kế. QLoRA đóng băng phần lớn trọng số 4-bit và huấn luyện adapter hạng thấp, phù hợp tài nguyên hạn chế. RAG bổ sung tri thức mà không cần nhồi toàn bộ vào trọng số. Safety và orchestration chịu trách nhiệm mà model đơn lẻ không bảo đảm.

**Nguồn:** DOCX Chương 2; `research/notebooks/HYPERPARAMS_RATIONALE.md`; `research/notebooks/HYPERPARAMS_RATIONALE_intake.md`.

## Slide 5 — Kiến trúc xương sống: hai pipeline gặp nhau tại hai model Ollama

**Claim chính:** Toàn bộ repo có hai pipeline song song — xây artifact và phục vụ runtime — được bao quanh bởi evaluation/provenance.

**Nội dung hiển thị:**

- **Data/model lane:** KB sources → clean/chunk → Chroma + BM25; Intake/ROLE data → gates → QLoRA → GGUF.
- **Runtime lane:** Next.js → FastAPI/SSE → Unified Intake → Orchestrator → Hybrid RAG → Prompt → Generator → Output Safety → SQLite/audit.
- **Evaluation lane:** A Intake (1.490) → B Retrieval (120) → C Ablation (145 × 6) → human calibration.
- **Provenance lane:** code truth → immutable audit → Current Truth/context → Obsidian mirror → defense claim.

**Visual:** Sơ đồ kiến trúc bốn lane, màu xanh đậm cho runtime chính, nét đứt cho fallback, kho dữ liệu bằng ký hiệu storage.

**Context nói:** Đây là slide bản đồ. Chỉ rõ evaluation và Obsidian không nằm trong đường trả lời người dùng; chúng là lớp đo lường và bằng chứng. Hai lane model gặp runtime ở `acne-intaker` và `acne-generator-v2`.

**Nguồn:** `src/acne_llm/di.py`; `src/acne_llm/chat/runtime.py`; `docker-compose.yml`; `research/dashboards/architecture/01_system_context.png`; `.audit/KNOWLEDGE_INDEX.md`.

## Slide 6 — Hai LLM, hai hợp đồng đầu ra khác nhau

**Claim chính:** Intaker giảm độ mơ hồ thành dữ liệu có cấu trúc; ROLE/Generator dùng cấu trúc và context để tạo câu trả lời có phạm vi.

**Nội dung hiển thị:**

| Thuộc tính | Unified Intaker | ROLE / Generator |
|---|---|---|
| Base | Qwen2.5-3B-Instruct 4-bit | Qwen2.5-7B-Instruct 4-bit |
| Model Ollama | `acne-intaker` | `acne-generator-v2` |
| Input | câu hiện tại + schema | system/user prompt + history + KB |
| Output | JSON: intent, fields, confidence | văn bản tiếng Việt theo luồng |
| Trách nhiệm | route + extract + safety signals | giải thích, cấu trúc câu trả lời, giọng ROLE |
| Không chịu trách nhiệm | chẩn đoán/sinh tư vấn hoàn chỉnh | xác nhận field, quyết định safety duy nhất |

**Context nói:** Current code dùng một `UnifiedIntake` chung cho interface router và extractor; không có hai LLM intake độc lập. Khi Intaker lỗi, SemanticRouter rồi rule fallback mới tham gia. Generator không tự gọi retrieval; Orchestrator xây prompt trước khi gọi Ollama.

**Nguồn:** `src/acne_llm/di.py`; `src/acne_llm/chat/intake.py`; `model/intaker/MANIFEST.json`; `model/generator/Modelfile`.

## Slide 7 — Intake biến hội thoại thành quyết định có thể kiểm soát

**Claim chính:** Intake chạy current-turn-first, kiểm tra hard safety, sinh cấu trúc, gấp lịch sử và định tuyến; fallback là cơ chế khả dụng, không phải safety authority.

**Nội dung hiển thị:**

`Raw text → normalize → hard safety → Unified Intaker → validate/parse → session fold → route`

- Intent: `advise | knowledge | clarify | reject`.
- Context: tuổi, giới tính, loại da, thai kỳ/cho con bú, dị ứng, thuốc/sản phẩm.
- Clinical: tổn thương, vị trí, thời gian, mức viêm.
- Fallback nét đứt: `SemanticRouter → rule router` khi model/parse không dùng được.
- Guard: field nhạy cảm chưa xác nhận phải giữ `unknown` hoặc hỏi lại.

**Visual:** Flowchart trái sang phải + một mẫu JSON rút gọn; nhánh hard reject màu đỏ, fallback nét đứt.

**Context nói:** Session memory không phải bệnh án. Cơ chế correction/negation cố tránh giữ thông tin đã bị phủ định; mức viêm được xử lý thận trọng. Runtime hiện chưa cập nhật deterministic `asked_fields` sau mỗi câu hỏi, nên chưa bảo đảm không hỏi lặp.

**Nguồn:** `src/acne_llm/chat/intake.py`; `src/acne_llm/chat/_intake_parse.py`; `src/acne_llm/chat/_intake_history.py`; `src/acne_llm/chat/_intake_hard_safety.py`; DOCX mục 3.4.

## Slide 8 — QLoRA ROLE: dữ liệu có gate → adapter → GGUF triển khai

**Claim chính:** ROLE fine-tuning điều chỉnh cách trả lời với chi phí thấp; corpus usable đã hình thành nhưng chưa đạt target và chưa có base-model control.

**Nội dung hiển thị:**

- Target 3.500; skeleton 3.335; accepted **3.077**; rejected audit **1.460**.
- Split: **2.616 train / 246 validation / 215 holdout**; 3 lỗi hậu kiểm `anchor_pair_corpus`.
- Base `Qwen2.5-7B-Instruct-bnb-4bit`; QLoRA `r=16`, `α=32`, dropout `0,05`.
- Best observed checkpoint: step **300**, validation loss **0,7477**, epoch ~1,83; export GGUF Q4_K_M → `acne-generator-v2`.
- Boundary: không có đối chứng base-Qwen nên chưa chứng minh hiệu quả fine-tune độc lập.

**Visual:** Funnel dữ liệu ở trái; pipeline QLoRA ở giữa; đường validation loss/điểm chọn checkpoint ở phải.

**Context nói:** Taxonomy gồm các nhóm role/safety/knowledge-preservation. Gate loại mẫu vi phạm schema, style và consistency; rejected audit là bằng chứng quy trình, không phải dữ liệu train. QLoRA chỉ cập nhật adapter hạng thấp trên nền 4-bit. Chọn checkpoint theo validation loss là kiểm soát overfit, nhưng loss thấp không tự chứng minh đúng y khoa.

**Nguồn:** `research/datagen/roledatav2/output/generation_summary.json`; `research/datagen/roledatav2/output/splits/`; `model/generator/qwen25_acne_role_v2_lora/checkpoint-300/trainer_state.json`; `model/generator/Modelfile`; `research/notebooks/HYPERPARAMS_RATIONALE.md`.

## Slide 9 — Hybrid Retrieval: dense và từ khóa bổ sung cho nhau

**Claim chính:** Retrieval kết hợp semantic, lexical và source-prior, nhưng vẫn coi “0 context” là trạng thái hợp lệ và minh bạch.

**Nội dung hiển thị:**

`Query → Dense top-25 + BM25 top-25 → RRF(k=60) → guideline/safety pass → BGE reranker → filters → max 5 chunks / 6.000 ký tự`

| Artifact | Quy mô |
|---|---:|
| Raw documents | 6.835 |
| Documents quality ≥ 0,3 | 6.796 |
| Final chunks | 24.393 |
| Chroma vectors | 24.393 |
| BM25 ids/texts | 24.393 / 24.393 |

**Context nói:** Dense phù hợp tương đồng ngữ nghĩa, BM25 giữ thuật ngữ/hoạt chất chính xác. Không cộng score trực tiếp vì khác thang; RRF dùng thứ hạng. Guideline/safety pass chỉ bổ sung ứng viên, vẫn qua reranker và ngưỡng. Reranker relevance không chứng minh tính đúng y khoa; chunk được đưa vào prompt cũng không chứng minh generator sử dụng đúng.

**Nguồn:** `src/acne_llm/retrieval/`; `data/raw/documents.jsonl`; `data/raw/chunks.jsonl`; `data/chroma_db`; `data/bm25_index.pkl`; DOCX Bảng 3.1–3.2.

## Slide 10 — Safety là boundary nhiều tầng, không phải một câu prompt

**Claim chính:** AcneLLM dùng pre-safety, routing, prompt contract và post-safety; suffix cảnh báo không thể thu hồi token đã stream.

**Nội dung hiển thị:**

| Thời điểm | Cơ chế | Ví dụ |
|---|---|---|
| Trước Intake | hard input/medication guard | prompt injection, kê đơn/liều, crisis |
| Sau Intake | intent + clinical/safety signals | reject/clarify, thai kỳ, dị ứng, viêm nặng |
| Trước Generator | prompt hai tầng + dữ kiện xác nhận | scope, source context, unknown fields |
| Sau Generator | output checks + suffix/referral | cảnh báo, không thay bác sĩ, đi khám |
| Sau response | SQLite/audit + PII redaction | route, model, used_chunks, latency |

**Visual:** Boundary diagram bao quanh prompt/generator; đường màu đỏ cho reject/referral, ghi chú “streamed token cannot be retracted”.

**Context nói:** Prompt chọn template theo nhánh `advise/knowledge/clarify/reject`. Output safety hiện có cả rule check và suffix, nhưng không phải bộ lọc token hoàn chỉnh. Vì SSE truyền dần, nội dung xấu đã hiển thị không thể được suffix “sửa ngược”. Đây là lý do safety vẫn là limitation chính và cần lane production parity.

**Nguồn:** `src/acne_llm/safety/`; `src/acne_llm/prompts/`; `src/acne_llm/chat/orchestrator.py`; `src/acne_llm/chat/runtime.py`; DOCX mục 3.5.

## Slide 11 — Một request đi qua toàn hệ thống theo thứ tự xác định

**Claim chính:** E2E inference là chuỗi có trace: request → intake → retrieval/prompt → stream → safety/persistence → SSE client.

**Nội dung hiển thị:**

1. Next.js mở `/api/v1/chat/stream` với session/mode.
2. FastAPI chuẩn hóa và gọi `run_intake`.
3. Orchestrator chọn `hybrid` hoặc `llm_only`; reject/clarify có nhánh riêng.
4. Hybrid RAG trả context + `used_chunks`; PromptBuilder lắp system/user prompt.
5. Ollama Generator stream token.
6. Backend thêm source/safety, lưu session/audit và phát `token | source | done | error`.

**Visual:** Sequence diagram 6 lifeline: UI, API, Intake, Retrieval/Prompt, Ollama, SQLite; normal flow solid, fallback dashed.

**Context nói:** Chỉ rõ nhánh zero-context: generator vẫn có thể trả lời `llm_only`, nhưng `used_chunks=[]` và không được mô tả là grounded. Nếu lỗi stream trước bước persistence, lượt chat có thể không được lưu đủ; event error giúp UI kết thúc trạng thái chờ.

**Nguồn:** `frontend/src/hooks/useSSE.ts`; `src/acne_llm/api/routes/chat.py`; `src/acne_llm/chat/runtime.py`; `src/acne_llm/chat/orchestrator.py`; DOCX mục 3.3.

## Slide 12 — Thiết kế thực nghiệm tách ba tầng và sáu arm

**Claim chính:** Giao thức tách “hiểu đầu vào”, “chất lượng context” và “chất lượng câu trả lời” để không quy mọi lỗi cho một model.

**Nội dung hiển thị:**

| Lane | Dataset | n | Chỉ số chính |
|---|---|---:|---|
| A — Intake | `intake_eval.v2` | 1.490 | schema, intent F1, field F1, hallucination, ECE |
| B — Retrieval | subset `eval_set.v3` | 120 | relevance, precision, sufficiency, nDCG |
| C — E2E/Ablation | `eval_set.v3` | 145 × 6 | answer quality, content errors, tone, safety |

**Arm legend:** `R=real`, `O=oracle`, `N=none`; RRR baseline, ORR intake oracle, RNR no RAG, ROR oracle RAG, RRO API generator, RNO API + no RAG.

**Context nói:** Paired bootstrap 2.000 lần, seed 42, báo 95% CI. Các arm có số cặp so sánh khác nhau do lỗi/thiếu oracle; không đọc delta như bảng xếp hạng tuyệt đối. LLM-as-a-judge là thước đo định hướng và được kiểm riêng bằng human calibration.

**Nguồn:** `research/evaluation/reports/v2_full/`; `research/evaluation/eval_context.md`; DOCX Bảng 4.3–4.6.

## Slide 13 — Intake định tuyến tốt hơn trích field; Retrieval xếp hạng tốt hơn bao phủ

**Claim chính:** Hai tầng đầu tạo giá trị nhưng để lại bottleneck rõ: field nhạy cảm của Intake và coverage/relevance của Retrieval.

**Nội dung hiển thị:**

**Intake — n=1.490**

- Schema valid **98,12%**; intent accuracy **95,70%**.
- Intent macro-F1 **74,05%**; extraction micro-F1 **61,31%**.
- Hallucinated fields **8,20%**; inflammation F1 **21,26%**.

**Retrieval — n=120**

- Có context **91/120 = 75,83%**; không context **29/120**.
- Relevance **2,5919/5**; precision **0,5344**; sufficiency **2,8462/5**.
- nDCG **0,9365**: thứ tự tốt không đồng nghĩa context đủ và đúng.

**Visual:** Hai biểu đồ bar cùng thang rõ ràng; callout `Intake: verify sensitive fields` và `Retrieval: coverage bottleneck`.

**Context nói:** Accuracy cao chịu ảnh hưởng lệch lớp vì `advise` chiếm đa số. Macro-F1 thấp hơn cho thấy lớp minority yếu. Field confidence ECE 0,3062 nên không xem confidence là xác suất đúng. Với retrieval, nDCG chỉ đánh giá thứ tự trong các đoạn đã có; 29 query zero-context và relevance thấp mới là điểm nghẽn hệ thống.

**Nguồn:** `research/evaluation/reports/v2_full/intake/`; `research/evaluation/reports/v2_full/retrieval/`; `research/dashboards/evaluation/06_intake_headline_metrics.png`; `research/dashboards/evaluation/12_retrieval_headline_metrics.png`; DOCX Bảng 4.7–4.10.

## Slide 14 — Generator local là bottleneck lớn nhất quan sát được; safety vẫn chưa đóng

**Claim chính:** Oracle context có ích, RAG thật chưa khai thác được ích lợi đó, và thay Generator gắn với delta lớn nhất; mọi arm vẫn có cờ an toàn.

**Nội dung hiển thị:**

| So với RRR | Delta answer quality | 95% CI | Diễn giải |
|---|---:|---|---|
| ORR — intake oracle | −0,0194 | [−0,1165; 0,0777] | chưa thấy prose quality tăng |
| RNR — no RAG | +0,0185 | [−0,0833; 0,1204] | RAG thật chưa tạo khác biệt rõ |
| ROR — oracle context | +0,4118 | [0,2353; 0,5882] | context phù hợp có tiềm năng |
| RRO — API generator | +0,7248 | [0,5688; 0,8807] | delta lớn nhất quan sát |
| RNO — API + no RAG | +0,8214 | [0,6696; 0,9645] | tập cặp riêng; không so trực tiếp RRO |

**Safety:** RRR 32, ORR 24, RNR 26, ROR 18/100, RRO 16, RNO 13 cờ; human RRR xác nhận 24/145, judge có 12 false positive và 4 false negative.

**Visual:** Forest plot delta ở trái; bar safety count/rate ở phải; boundary bar dưới: “directional, historical v2_full, not clinically validated”.

**Context nói:** Không kết luận RAG vô dụng: ROR dương cho thấy context tốt có giá trị, còn RNR gần 0 nói RAG thật hiện chưa phát huy. Không kết luận fine-tune thất bại vì thiếu base-Qwen control. Human calibration một người không phải bác sĩ; κ quadratic cho bốn trục 0,3188–0,5663, đều dưới 0,61.

**Nguồn:** `research/evaluation/reports/v2_full/ablation/`; `research/evaluation/reports/calibration_rrr/ket_qua_rrr145.json`; `research/dashboards/evaluation/22_ablation_paired_delta_forest.png`; DOCX Bảng 4.11–4.13.

## Slide 15 — Demo và deployment: local-first, stream được, nhưng chưa đóng parity runtime

**Claim chính:** Sản phẩm có đầy đủ UI/API/model/data services; demo minh họa đường đi thật, không được dùng như bằng chứng clinical hoặc production readiness.

**Nội dung hiển thị:**

**Demo 45–60 giây**

1. Chọn câu hỏi có tín hiệu: “Đang mang thai có dùng retinol trị mụn được không?”
2. Quan sát stream trả lời + disclaimer/referral và source cards nếu có context.
3. Mở KB Explorer để xem chunk/source/score; không sửa settings trong demo chính.

**Deployment**

- `frontend`: Next.js.
- `backend`: FastAPI, SSE, Prometheus `/metrics`.
- `ollama`: `acne-intaker` + `acne-generator-v2`.
- state: Chroma, BM25, SQLite/audit; Docker Compose nối service và volume.

**Visual:** Ảnh giao diện thật của frontend hiện tại ở trái; deployment topology ở phải; event strip `token → source → done/error`.

**Context nói:** Nếu live model chưa ready, dùng UI walkthrough và không giả vờ đó là endpoint smoke. Current source default đã thống nhất `acne-generator-v2`, nhưng chưa chạy real SSE smoke trong phiên audit. `495 passed, 1 xfailed` chỉ là regression gate. Demo dùng câu hỏi safety để cho thấy kiến trúc, không yêu cầu hội đồng đánh giá độ đúng y khoa bằng một ví dụ.

**Nguồn:** `frontend/src/components/chat/ChatWindow.tsx`; `frontend/src/hooks/useSSE.ts`; `docker-compose.yml`; `docker/ollama-init.sh`; `src/acne_llm/config.py`; `tests/`.

## Slide 16 — Kết luận trung thực và roadmap theo verification gate

**Claim chính:** AcneLLM đã hoàn thành prototype E2E có thể truy vết và định vị bottleneck; bước tiếp theo phải nâng cấp bằng chứng, không chỉ thêm tính năng.

**Nội dung hiển thị:**

**Đã chứng minh**

- Kiến trúc module local-first từ dữ liệu → model → runtime → evaluation.
- Intake định tuyến tốt nhưng field chưa đều; Retrieval thiếu coverage; Generator local là bottleneck lớn nhất quan sát.
- Code hiện tại: 495 passed, 1 xfailed; snapshot audit 837/837 path, 0 hash mismatch.

**Chưa chứng minh**

- Độ đúng/an toàn lâm sàng; production/T4/SSE parity.
- Hiệu quả fine-tune so với base model.
- Delta giữa arm được bác sĩ/nhiều rater xác nhận.

**Roadmap có gate**

1. Retrieval: giảm no-context + qrels/groundedness.
2. Human evidence: ≥2 rater + bác sĩ + paired arm.
3. Runtime: full rerun + T4/SSE endpoint parity.
4. Fine-tuning: base-Qwen control cùng protocol.

**Visual:** Ma trận `Evidence achieved / Evidence gap / Verification gate`, kết bằng một câu: “Prototype nghiên cứu có bằng chứng kỹ thuật — chưa phải công cụ y khoa độc lập.”

**Context nói:** Kết luận trả lời lại vấn đề ở slide 2: kiến trúc tách lớp giúp kiểm soát và đo rủi ro tốt hơn một LLM đơn lẻ, nhưng không xóa rủi ro. Giá trị khoa học của đề tài là chuỗi bằng chứng và khả năng chỉ ra đúng nơi cần cải tiến. Mời hội đồng đặt câu hỏi ở kiến trúc, QLoRA, evaluation hoặc safety.

**Nguồn:** DOCX Chương 5; `.audit/SLIDE_FACT_CHECK_2026-08-25.md`; `.audit/runs/20260825T090826Z/SNAPSHOT_GATE.md`; `research/evaluation/reports/v2_full/`; `research/evaluation/reports/calibration_rrr/`.

## Nhịp thời gian đề xuất

| Slide | Thời lượng |
|---:|---:|
| 1–4 | 3:10 |
| 5–11 | 8:00 |
| 12–14 | 5:20 |
| 15–16 | 2:50 |
| **Tổng** | **19:20** |

40 giây còn lại dành cho chuyển slide, mở demo hoặc xử lý gián đoạn. Nếu phải rút ngắn, rút lời ở slide 4 và 15; không cắt các kết luận ở slide 14 và 16.
