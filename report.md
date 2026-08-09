# BÁO CÁO NGỮ CẢNH SOURCE-OF-TRUTH CHO HỆ THỐNG ACNELLM

> Snapshot kiểm tra: 08-08-2026  
> Workspace: E:/project/AcneLLM  
> Nhánh: codex/simplify-chat-pipeline  
> HEAD tham chiếu: 19311b8a0cf8e642f71bf3ac082906d6502c604c  
> Trạng thái: worktree đang có nhiều thay đổi chưa commit; nội dung dưới đây mô tả chính worktree hiện tại, không chỉ mô tả commit HEAD.

## Quy ước và phạm vi của tài liệu

Tài liệu này là context kỹ thuật để viết khóa luận theo khung đã cung cấp. Nó không phải kết quả thực nghiệm và không thay thế việc trích dẫn tài liệu học thuật.

- Căn cứ được dùng: source Python/TypeScript/PowerShell/Shell, Jinja template, YAML/TOML/JSON cấu hình, notebook huấn luyện, schema dữ liệu, index runtime và API Ollama đang có trên máy.
- Không dùng nội dung của README, tài liệu thiết kế hoặc báo cáo Markdown trong repository để suy ra kiến trúc.
- Các artifact kết quả cũ trong evaluation/reports không được dùng làm số liệu ở Chương 4.
- Các con số về số file, số chunk, model đang nạp và cấu hình hiệu lực chỉ là ảnh chụp trạng thái kỹ thuật; chúng không phải điểm đánh giá chất lượng.
- Nhãn **Đã có** nghĩa là có đường code hiện hành. **Chưa đo** nghĩa là repository có thể có harness hoặc artifact nhưng báo cáo này chưa coi đó là kết quả được chấp nhận. **Đề xuất** nghĩa là việc cần triển khai trong thực nghiệm, không phải chức năng đã tồn tại.

## Phạm vi rà soát source

Không tính .venv, node_modules, .next, file Markdown, báo cáo sinh ra và binary model/index, bản đồ mã nguồn gồm 317 file code/cấu hình với khoảng 69.011 dòng vật lý:

| Khu vực | File code/cấu hình | Vai trò chính |
|---|---:|---|
| src | 90 | API, intake, session, safety, retrieval, Ollama, crawler, schema |
| tests | 42 | Unit/integration contract của runtime |
| evaluation | 44 | Dataset registry, intake/retrieval/ablation runner, judge, metric |
| datagen | 68 | Sinh dữ liệu ROLE và Unified Intake, gate, split, export |
| frontend | 16 | Next.js/React UI, SSE client, Zustand store |
| LLMData | 17 | Pipeline dữ liệu hội thoại lâm sàng và safety đời trước |
| ablation | 9 | Harness ablation độc lập đời trước |
| scripts | 12 | Crawl, build KB, chuyển đổi dữ liệu, launcher |
| guideline_docs | 5 | Xử lý guideline PDF và đồng bộ index |
| visualize | 4 | Phân tích/biểu đồ dữ liệu ngoại tuyến |
| config | 9 | Prompt Jinja, guardrail, thuốc |
| model | 1 notebook | QLoRA, merge, GGUF, Modelfile |

## Baseline runtime thật tại thời điểm kiểm tra

| Thành phần | Trạng thái đã xác nhận |
|---|---|
| Intake | intake_mode=unified; model acne-intaker; một đối tượng UnifiedIntake dùng chung cho route và extract |
| Generator | acne-generator; fallback qwen2.5:3b; context 8192; num_predict 2048; system lấy từ Modelfile |
| Retrieval | RAG sẵn sàng; Chroma và BM25 cùng có 24.393 chunk |
| Embedding/rerank | AITeamVN/Vietnamese_Embedding, vector 1024 chiều; BAAI/bge-reranker-v2-m3; cấu hình device=cpu |
| Phiên/audit | SQLiteSessionStore tại data/sessions.db; AuditStore tại data/audit.db |
| Cache | DiskCache tại data/cache, giới hạn cấu hình 2 GB, retrieval TTL 1 giờ |
| API | FastAPI dự kiến cổng 8000; API key hiệu lực đang rỗng; CORS hiệu lực đang là wildcard; rate limit 60 yêu cầu/phút/IP |
| Frontend | package.json khai next ^15.5.15 và react ^18.3.1; package-lock/node_modules đang resolve Next.js 15.5.20; dự kiến cổng 3000 |
| Trạng thái sống | Ollama cổng 11434 đang chạy cục bộ; backend 8000 và frontend 3000 không lắng nghe khi chụp snapshot |

Phân bố source_type đang lưu trong Chroma là một thông tin inventory, không phải điểm chất lượng: vi_medical_site 12.359; pubmed_review 5.218; blog 3.571; en_medical_site 2.258; clinical_textbook 621; aad_guideline 180; nice_guideline 172; unknown 14. Metadata này cần được audit thủ công vì nhãn source_type được suy luận bằng rule và không đồng nghĩa với độ đúng lâm sàng.

### Kiểm chứng tự động của snapshot

- Lệnh chuẩn bằng môi trường dự án, .venv/Scripts/python.exe -m pytest -q, **không qua được collection**: tests/test_approve_eval_labels.py và tests/test_propose_eval_labels.py còn import hai module scripts/approve_eval_labels.py và scripts/propose_eval_labels.py đã bị xóa trong worktree.
- Chạy phần còn lại bằng cách ignore đúng hai test mồ côi cho kết quả kỹ thuật 501 passed, 1 xfailed. Con số này chỉ chứng minh phần suite còn thu thập được đang xanh; nó không phải số liệu đánh giá mô hình, không hợp thức hóa hai test bị bỏ qua và không chứng minh an toàn lâm sàng.
- npm run build trong frontend hoàn tất production build, type check và static generation bằng Next.js 15.5.20. Đây là build verification, không chứng minh frontend đã được chạy E2E với backend/Ollama.
- Vì vậy trạng thái trung thực của baseline là: **full test suite không green**. Trước release cần hoặc khôi phục implementation tương ứng, hoặc xóa/cập nhật test theo quyết định thiết kế có chủ đích rồi chạy lại toàn bộ suite mà không ignore.

## Các sai lệch phải nêu rõ trước khi viết khóa luận

1. **Prompt intaker đang nạp khác source.** Backend intake được cấu hình use_modelfile_system=True, nên _RUNTIME_SYSTEM truyền từ src/acne_llm/chat/unified_intake.py bị OllamaBackend bỏ khỏi messages. System đang nạp trong model acne-intaker dài khoảng 2.131 ký tự, trong khi model/acne_intake_release/Modelfile và source hiện hành dài hơn và có neo IGA. Do đó baseline chạy thật hiện chưa chắc áp dụng phần neo IGA mới.
2. **Prompt generator cũng có drift byte-level.** System đang nạp trong acne-generator không byte-identical với model/system_prompt.canonical.txt hoặc model/Modelfile. Khác biệt đã thấy ở cách mô tả ngôn ngữ tài liệu tham khảo; model nạp còn có num_ctx mặc định 8162 trong khi request runtime gửi 8192.
3. **Worktree bẩn.** Mọi thực nghiệm phải lưu git commit, git diff hoặc patch hash; chỉ ghi commit HEAD là không đủ tái lập.
4. **Docker Compose chưa đồng bộ unified intake.** Compose khởi tạo acnellm-v2-q4 cho generator nhưng không tạo acne-intaker, trong khi source mặc định cần acne-intaker. Không được mô tả Compose là đã triển khai thành công nếu chưa sửa và chạy kiểm chứng.
5. **Launcher Windows hiện hướng tới tunnel RunPod.** scripts/RUN.ps1 yêu cầu process giữ cổng 11434 phải là ssh và sẽ từ chối Ollama local; thông báo khôi phục còn trỏ tới tasks.ps1 hiện không có. Đây không phải launcher local tổng quát.
6. **Safety output chưa phải bộ lọc cưỡng chế đầy đủ.** Luồng SSE sinh prose rồi nối suffix cảnh báo; structured post_check không chạy trên prose streaming và suffix không xóa hay viết lại nội dung nguy hiểm đã phát ra.
7. **Test contract còn mồ côi.** Hai test label-approval/proposal vẫn tồn tại trong khi implementation tương ứng đã bị xóa; do đó không được tuyên bố test suite hiện hành đã pass toàn bộ.

# LỜI CẢM ƠN

Phần này là nội dung cá nhân, không suy ra từ repository. Có thể cảm ơn giảng viên hướng dẫn, đơn vị đào tạo, người hỗ trợ dữ liệu và kiểm thử; tránh ghi rằng bác sĩ đã thẩm định nếu chưa có biên bản thẩm định thật.

# LỜI CAM KẾT

Gợi ý cam kết phù hợp với trạng thái repo:

“Tác giả cam kết phần mô tả hệ thống được đối chiếu từ source code và cấu hình vận hành của worktree AcneLLM tại snapshot đã nêu. Các kết quả thực nghiệm chỉ được công bố sau khi khóa dữ liệu, model lineage, cấu hình và quy trình chấm. Tài liệu này không sử dụng số liệu giả hoặc coi artifact chưa xác minh là kết quả cuối.”

# MỤC LỤC

Sinh tự động từ các heading sau khi chuyển sang định dạng khóa luận; không gõ số trang thủ công trong report.md.

# DANH MỤC CÁC KÝ HIỆU, CHỮ VIẾT TẮT VÀ THUẬT NGỮ

| Ký hiệu | Nghĩa trong repository |
|---|---|
| API | FastAPI HTTP interface |
| BM25 | Sparse index dùng rank-bm25 và tokenization tiếng Việt |
| CORS | Chính sách origin của FastAPI |
| DI | Dependency Injection qua Container trong src/acne_llm/di.py |
| ECE | Expected Calibration Error cho confidence của intake |
| GGUF | Định dạng model đã lượng tử hóa để nạp Ollama |
| LLM | Mô hình sinh phản hồi acne-generator hoặc model so sánh |
| LoRA | Adapter low-rank dùng trong notebook huấn luyện |
| MMR | Maximal Marginal Relevance; có helper nhưng không nằm trong chat path hiện tại |
| OOS/OOD | Ngoài phạm vi; runtime chủ yếu dùng router soft reject, OOD detector bị tắt trong DI |
| PEFT | Fine-tuning một phần tham số |
| QLoRA | LoRA trên base model nạp 4-bit trong notebook |
| RAG | Retrieval-Augmented Generation |
| RRF | Reciprocal Rank Fusion để hợp nhất dense và BM25 |
| SSE | Server-Sent Events cho endpoint chat streaming |
| TTL | Thời gian sống của session/cache |
| WS | WebSocket endpoint thay thế SSE |

# DANH MỤC CÁC BẢNG

Nên tạo sau khi có kết quả thật. Các bảng tối thiểu: cấu hình runtime; schema intake; cấu hình retrieval; cấu hình QLoRA; phân bố tập dữ liệu; metric intake; metric retrieval; metric E2E/safety; paired ablation; lỗi và mẫu bị loại.

# DANH MỤC CÁC HÌNH VẼ, ĐỒ THỊ

Nên tạo từ artifact đã khóa: sơ đồ kiến trúc; sequence flow một lượt chat; lifecycle session; pipeline KB; đường train/eval loss; confusion matrix intake; biểu đồ metric retrieval; paired delta và bootstrap CI của ablation. Không dựng đồ thị loss từ số trong notebook cũ nếu chưa xác minh lineage.

# CHƯƠNG 1: GIỚI THIỆU

## 1.1. Đặt vấn đề

AcneLLM là hệ thống hội thoại tiếng Việt tập trung vào mụn và chăm sóc da mụn. Bài toán kỹ thuật của repo không chỉ là gọi một LLM: hệ thống phải kiểm tra đầu vào, định tuyến ý định, trích dữ kiện có confidence, giữ ngữ cảnh phiên, chặn một số rủi ro thuốc, truy xuất KB khi phù hợp, sinh prose qua Ollama và truyền kết quả theo luồng.

Không mô tả hệ thống là công cụ chẩn đoán. System prompt và safety code xác định đây là trợ lý thông tin/tư vấn sơ bộ, không thay thế bác sĩ, không kê đơn cá nhân hóa và cần chuyển tuyến khi có dấu hiệu nặng hoặc nguy hiểm.

## 1.2. Lý do chọn đề tài

Context đúng với repo:

- Đầu vào tiếng Việt có dấu/không dấu, teencode nhẹ, phủ định và hội thoại nhiều lượt gây khó cho routing/extraction.
- Tư vấn mụn có rủi ro về retinoid, kháng sinh, thai kỳ, trẻ em, tương tác thuốc và tự làm thủ thuật.
- Chỉ dùng LLM dễ bịa nguồn; chỉ dùng retrieval dễ trả đoạn đúng chủ đề nhưng thiếu ngữ cảnh.
- Vận hành qua Ollama cho phép tách model intake và model trả lời, đồng thời giữ API ứng dụng ở local/private infrastructure.

Các lập luận về gánh nặng bệnh, tỷ lệ mụn hoặc hiệu quả y khoa phải lấy từ nguồn học thuật bên ngoài, không suy ra từ source.

## 1.3. Mục tiêu nghiên cứu

Mục tiêu có thể viết theo những gì repo thật sự hỗ trợ:

1. Xây dựng giao diện chat tiếng Việt có streaming, lịch sử trong phiên, nguồn tham khảo và feedback.
2. Xây dựng unified intake cho bốn intent advise, knowledge, clarify và reject.
3. Kết hợp rule safety, dữ kiện phiên, hybrid retrieval và local LLM.
4. Chuẩn bị pipeline dữ liệu ROLE/Intake và quy trình QLoRA cho model Qwen2.5.
5. Thiết kế harness đánh giá tách riêng intake, retrieval, generation, safety và ablation.

Mục tiêu “chứng minh hiệu quả” chưa đạt cho đến khi Chương 4 được chạy với dữ liệu và lineage đã khóa.

## 1.4. Đối tượng và phạm vi nghiên cứu

- Đối tượng sử dụng chính: người dùng phổ thông cần thông tin sơ bộ về mụn ở mặt, lưng, ngực, vai, cổ.
- Đối tượng quản trị: người vận hành có thể xem health, metric, audit, session stats và feedback qua API.
- Phạm vi input hiện hành: văn bản; schema có VisionOutput và MockVision nhưng API/UI không có upload ảnh và DI không ghép vision thật.
- Phạm vi y khoa: hỗ trợ thông tin và điều hướng an toàn; không chẩn đoán xác định, không kê đơn/liều.
- Phạm vi vận hành: một FastAPI backend, một Next.js frontend, Ollama và local KB; chưa có multi-tenant, RBAC hoặc hệ thống phân tán.

## 1.5. Phương pháp thực hiện

- Phân tích source và trace shared orchestrator từ endpoint đến Ollama.
- Thiết kế dữ liệu có schema, taxonomy, gate, chống trùng và split cố định.
- QLoRA model Qwen2.5-7B-Instruct 4-bit, mask loss chỉ ở response, merge và xuất GGUF.
- Xây KB từ crawl/guideline, chunk, dense embedding, BM25 và reranking.
- Đánh giá theo ba runner chính: intake, retrieval và ablation; bổ sung kiểm thử chức năng/safety.
- Kiểm soát provenance bằng hash dataset, commit/diff, model ID, prompt hash và KB fingerprint.

## 1.6. Đóng góp của đề tài

Các đóng góp có căn cứ source:

- Một pipeline unified intake có fallback LLM → semantic router → rule/deterministic.
- Session fold xử lý dữ kiện ổn định, phủ định và topic shift cho turn advise.
- Hybrid RAG có source boost, guideline/safety passes, reranker và lọc theo source/topic.
- Safety nhiều lớp từ pre-check, medication gate, Modelfile policy đến streaming suffix.
- Giao diện chat/KB/settings chạy trên Next.js và backend SSE/WebSocket.
- Datagen và evaluation harness có schema, gate, paired ablation, bootstrap CI và judge calibration.

Không gọi đây là “đã được kiểm chứng lâm sàng” hoặc “production-ready” ở trạng thái hiện tại.

## 1.7. Cấu trúc Khóa luận

Chương 2 neo lý thuyết vào các lựa chọn thật của repo; Chương 3 mô tả source/runtime; Chương 4 mô tả kế hoạch và sau này điền kết quả thực nghiệm đã khóa; Chương 5 kết luận theo đúng mức bằng chứng.

# CHƯƠNG 2: TỔNG QUAN CƠ SỞ LÝ THUYẾT

> Chương này cần tài liệu tham khảo học thuật độc lập. Phần dưới chỉ chỉ ra điểm nối với repo, không thay thế nội dung lý thuyết.

## 2.1. Tổng quan về mô hình ngôn ngữ lớn (LLM)

Liên hệ repo: acne-generator sinh prose; acne-intaker sinh JSON intake; model frontier chỉ được dùng trong datagen/judge/arm oracle. Cần phân biệt model học tham số với retrieval cung cấp context ở thời điểm chạy.

## 2.2. Kiến trúc Transformer

Liên hệ repo: base huấn luyện là Qwen2.5-7B-Instruct; notebook tác động các projection q, k, v, o và gate/up/down bằng LoRA. Không cần mô tả encoder-decoder vì đường model chính là decoder-only.

## 2.3. Tokenization và Embedding

- Tokenizer Qwen được dùng khi format ChatML và kiểm chiều dài trong notebook.
- Ollama trả prompt_eval_count/eval_count; OllamaBackend dùng chúng để cảnh báo tràn context.
- KB dùng AITeamVN/Vietnamese_Embedding, vector 1024 chiều.
- BM25 dùng underthesea nếu khả dụng, nếu lỗi thì split theo khoảng trắng; có stopword tiếng Việt.
- VietnameseChunker đặt chunk_size=200, overlap=40, min_size=50 theo đơn vị token ước lượng của chunker, không phải tokenizer Qwen.

## 2.4. Mô hình Decoder-only và Instruction-tuned Model

Qwen2.5-Instruct nhận chuỗi hội thoại system/user/assistant. Generator runtime giữ system trong Modelfile; user prompt được PromptBuilder render. Intake cũng là decoder-only nhưng bị ràng buộc output JSON qua Ollama format.

## 2.5. Fine-tuning mô hình ngôn ngữ lớn

Notebook model/finetune_role_qwen25_q4.ipynb thực hiện supervised fine-tuning trên records ShareGPT. Tập ROLE huấn luyện cách giữ vai, giọng, từ chối, grounding và an toàn; không chứng minh model có thêm tri thức y khoa mới.

## 2.6. Parameter-Efficient Fine-Tuning

Repo dùng adapter LoRA thay vì cập nhật toàn bộ tham số. Phần lý thuyết nên giải thích giảm số tham số trainable, lưu adapter riêng và khả năng merge vào base trước khi lượng tử hóa.

## 2.7. LoRA

Cấu hình trong notebook: r=16, alpha=32, dropout=0,05, bias=none; target q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj; gradient checkpointing kiểu Unsloth; seed 3407.

## 2.8. QLoRA

Base unsloth/Qwen2.5-7B-Instruct-bnb-4bit được load_in_4bit=True. Sau huấn luyện, notebook lưu adapter, merge 16-bit rồi xuất GGUF Q4_K_M. Cần phân biệt 4-bit trong huấn luyện với GGUF Q4 dùng khi serving.

## 2.9. Triển khai LLM cục bộ với Ollama

OllamaBackend gọi /api/chat, /api/tags và /api/show; hỗ trợ stream, format JSON, keep_alive và fallback khi model runner bị terminate. Runtime hiện cần hai model: acne-intaker và acne-generator. Model SYSTEM nằm trong Modelfile vì llm_use_modelfile_system=True.

## 2.10. Healthcare LLM và Medical Chatbot

Repo áp dụng phạm vi hẹp, disclaimer, chuyển tuyến, kiểm tra thai kỳ/thuốc và audit. Đây là risk-control engineering, chưa phải chứng nhận an toàn y tế. Phần lý thuyết phải bàn đến hallucination, over-reliance, privacy, clinical validation và human oversight bằng nguồn bên ngoài.

## 2.11. Prompt Engineering

Prompt có hai lớp: SYSTEM của model trong Ollama và user prompt dựng theo template. Template thay đổi theo refuse/reject/clarify/knowledge/stream; context được phân thứ tự ưu tiên và làm sạch trước khi render.

## 2.12. Safety Layer trong chatbot y tế

Repo dùng defense-in-depth: input limits, injection/PII detection, hard scope, medication gate, policy trong Modelfile, prefix/suffix runtime, audit và test. Cần nhấn mạnh giới hạn: suffix không undo token nguy hiểm đã stream.

## 2.13. Retrieval như thành phần hỗ trợ

Retrieval chỉ kích hoạt với intent phù hợp, mode hybrid và index sẵn sàng. Nó cung cấp tài liệu tham khảo cho generator; evidence_quality hiện chỉ là heuristic trên score reranker, không phải xác suất câu trả lời đúng.

# CHƯƠNG 3: PHÂN TÍCH VÀ THIẾT KẾ HỆ THỐNG ACNELLM

## 3.1. Phân tích yêu cầu hệ thống

### 3.1.1. Mô tả bài toán

Một lượt chat phải biến tin nhắn tự nhiên thành trạng thái có cấu trúc, quyết định ý định/phạm vi/rủi ro, chọn có retrieval hay không, tạo prompt và stream câu trả lời tiếng Việt. Hệ thống phải giữ được dữ kiện liên lượt nhưng không được biến suy đoán confidence thấp thành hồ sơ chắc chắn.

### 3.1.2. Đối tượng sử dụng

- Người dùng phổ thông qua trang Chat.
- Người cần tra cứu thủ công qua KB Explorer.
- Người vận hành qua health/models/metrics/admin endpoints.
- Không có role bác sĩ, RBAC hay tài khoản người dùng trong source hiện tại.

### 3.1.3. Yêu cầu chức năng

1. Nhận tin nhắn tối đa 4.000 ký tự và 500 từ.
2. Route advise/knowledge/clarify/reject.
3. Trích context và clinical facts có confidence.
4. Giữ session theo session_id.
5. Tự chọn hybrid hoặc llm_only, hoặc nhận override tin cậy cho advise/knowledge.
6. Stream token, nguồn và metadata hoàn tất.
7. Lưu audit, feedback và thống kê.
8. Cho phép tìm KB và xem chunk.

### 3.1.4. Yêu cầu phi chức năng

- Phản hồi theo luồng, có request ID và latency.
- Hoạt động degraded khi RAG không sẵn sàng.
- Dữ liệu có schema Pydantic; BM25 có checksum.
- Cache và model keep_alive giảm chi phí lặp.
- Input được làm sạch; prompt context được sanitize.
- Tái lập đánh giá bằng hash/lineage và paired common IDs.

Chưa có SLA, concurrency benchmark, privacy impact assessment hoặc clinical safety target được chứng minh.

### 3.1.5. Giới hạn của hệ thống

Text-only, single-node, không chẩn đoán/kê đơn, không có auth người dùng, API key mặc định đang rỗng, CORS hiệu lực wildcard, rate limiter nằm trong memory của từng process, audit có thể chứa dữ liệu nhạy cảm, output safety chưa phải hard rewrite.

## 3.2. Kiến trúc tổng thể của hệ thống

### 3.2.1. Định hướng thiết kế kiến trúc

Kiến trúc module hóa nhưng dùng shared orchestrator để SSE, WebSocket, CLI và evaluation đi cùng một pipeline. Luồng chính:

Frontend → FastAPI chat route → prepare_chat_turn → unified intake → conditional RAG → PromptBuilder → Ollama generator → stream safety suffix → SSE/WS → session và audit.

### 3.2.2. Lớp giao diện người dùng

frontend/src chứa ChatWindow, MessageInput, MessageBubble, SourceCard, ChunkDetailModal; useSSE đọc stream; Zustand chatStore giữ state phía trình duyệt.

### 3.2.3. Lớp API

src/acne_llm/api/app.py khởi tạo FastAPI, CORS, middleware và routers health/chat/kb/admin/metrics. Container được tạo trong lifespan và đóng khi ứng dụng dừng.

### 3.2.4. Lớp điều phối hội thoại

src/acne_llm/chat/orchestrator.py tạo PreparedChatTurn dùng chung. src/acne_llm/chat/runtime.py chịu trách nhiệm streaming, warning, persistence và audit.

### 3.2.5. Lớp tiếp nhận và quản lý ngữ cảnh

intake.py điều phối preprocess, safety, routing, extraction và fold. unified_intake.py gọi một model cho cả intent và field extraction. session.py và db/session_store.py quản lý dữ kiện liên lượt.

### 3.2.6. Lớp kiểm soát an toàn

GuardrailRunner, DrugChecker, intake hard gates, Modelfile SYSTEM và chat/_safety.py. OodDetector tồn tại nhưng DI hiện tạo GuardrailRunner với enable_ood=False.

### 3.2.7. Lớp truy xuất tri thức hỗ trợ

ChromaStore + Embedder cho dense, BM25Index cho sparse, HybridRetriever cho RRF, Reranker cho cross-encoder, chat/_retrieval.py cho passes/filter/cache/prompt-ready output.

### 3.2.8. Lớp tương tác với mô hình ngôn ngữ lớn

OllamaBackend dùng HTTP sync client; model intake sinh JSON non-stream, model generator sinh prose stream. Fallback generator chỉ dùng khi runner termination được nhận diện, không phải mọi lỗi.

### 3.2.9. Lớp dữ liệu và cấu hình

Pydantic Settings đọc .env; dữ liệu chính gồm documents/chunks JSONL, Chroma, BM25, semantic router train/cache, SQLite session/audit và DiskCache. Prompt Jinja và YAML safety nằm dưới config.

## 3.3. Thiết kế quy trình xử lý hội thoại

### 3.3.1. Quy trình xử lý tổng quát

1. Validate tham số HTTP.
2. Chuẩn hóa text và lấy history.
3. Pre-check injection/PII, hard scope và medication signals.
4. Route bằng UnifiedIntake; fallback semantic rồi rule.
5. Với advise/knowledge mới trích field; advise mới fold profile/history.
6. Chọn mode và truy xuất nếu đủ điều kiện.
7. Chọn template, sanitize và render prompt.
8. Stream generator, bỏ ký tự CJK, nối warning.
9. Emit source/done, lưu session/audit.

### 3.3.2. Tiếp nhận và kiểm tra yêu cầu

GET /api/v1/chat/stream và WebSocket cùng chặn message rỗng, trên 4.000 ký tự hoặc trên 500 từ. Frontend cũng chặn trên 500 từ nhưng backend vẫn là cổng bắt buộc.

### 3.3.3. Chuẩn hóa đầu vào và truy xuất phiên hội thoại

prepare_user_text chuẩn hóa Unicode NFC, bỏ zero-width/control, thu gọn whitespace và dấu câu lặp; giữ cả clean_text có dấu và bản bỏ dấu cho rule. History lấy tối đa 6 turn gần nhất từ SQLite, session TTL 1.800 giây.

### 3.3.4. Kiểm tra an toàn và xác định ý định

Pre-check phát hiện prompt injection, PII và input lỗi. Hard rule cho yêu cầu chỉ liên quan vùng sinh dục. Medication gate chạy trước model. Router precedence hiện là UnifiedIntake → SemanticRouter → deterministic rule router.

### 3.3.5. Trích xuất dữ kiện và kiểm tra mức độ đầy đủ

UnifiedIntake trả context/clinical nodes có confidence. Parser loại enum/field sai thay vì tin toàn bộ output. **Runtime hiện không còn module completeness.py và không có cổng completeness cứng.** Missing/low-confidence facts được chuyển thành confidence_hint cho generator; model quyết định có hỏi lại hay không. Không được mô tả một scoring completeness độc lập đang chạy.

### 3.3.6. Lựa chọn chế độ và truy xuất tri thức

Auto chọn hybrid khi RAG sẵn sàng, ngược lại llm_only. Reject/clarify không retrieve. Advise/knowledge có thể retrieve; override mode từ user chỉ được tin sau khi route thuộc hai intent này.

### 3.3.7. Lựa chọn template và xây dựng prompt

Hard refusal → refuse_user.j2; soft reject → reject_user.j2; clarify → clarify_user.j2; knowledge → knowledge_user.j2; còn lại → stream_user.j2. PromptBuilder ghép current user, confirmed safety facts, history và retrieval context.

### 3.3.8. Sinh và truyền phản hồi

Ollama stream token. Runtime loại dải CJK trước khi emit. Knowledge đặt num_predict=-1 để model tự dừng; intent khác dùng giới hạn cấu hình. SSE gửi token trước, source sau, cuối cùng done.

### 3.3.9. Bổ sung cảnh báo và câu hỏi làm rõ

Clarify là một template yêu cầu đúng một câu hỏi. Với prose khác, get_safety_suffix nối cảnh báo thai kỳ/retinoid, thuốc kê đơn, trẻ em, urgent flag, multi-condition, thủ thuật hoặc disclaimer. Cảnh báo được thêm sau generation, không phải kiểm duyệt từng token.

### 3.3.10. Lưu phiên, audit và kết thúc luồng

Runtime lưu raw user turn, assistant text, mode, used_chunks và snapshot chuẩn hóa cho advise. Audit lưu query, intent metadata, response, latency và PII flag. done event mang mode, latency_ms, used_chunks, session_id, evidence_quality, primary_intent và route_flags.

## 3.4. Thiết kế thành phần tiếp nhận và phân tích yêu cầu

### 3.4.1. Vai trò của thành phần intake

Intake là cổng thống nhất giữa raw message và downstream: trả clean text, UserInput, route decision, mode, history, confirmed profile, retrieval query, refusal và snapshot.

### 3.4.2. Kiểm tra giới hạn đầu vào

Giới hạn 4.000 ký tự/500 từ xuất hiện cả route và intake. Direct caller ngoài API vẫn bị intake kiểm tra; đây là defense-in-depth.

### 3.4.3. Tiền xử lý và chuẩn hóa văn bản

Preprocess không làm semantic rewrite rộng. Teencode map chỉ được dùng khi tạo retrieval query cho một số token như ko/kop, sp, xit, bt, bh; intaker nhận clean text gần nguyên nghĩa. Cách này giảm nguy cơ heuristic làm méo câu gốc.

### 3.4.4. Truy xuất lịch sử và xác định chế độ ban đầu

History lấy trước route. Requested mode auto/hybrid/llm_only được ghi nhận nhưng effective mode còn phụ thuộc intent, refusal và RAG readiness.

### 3.4.5. Kiểm tra phạm vi và tín hiệu an toàn ban đầu

Hard genital-only refusal chạy trước LLM; mixed acne + out-of-scope chỉ giữ phần trong phạm vi. pre_check có injection/PII. Safety terms current-turn được canonical hóa để medication gate không phụ thuộc hoàn toàn vào extractor.

### 3.4.6. Thiết kế bộ định tuyến ý định

- Primary: acne-intaker trả advise/knowledge/clarify/reject và confidence.
- Fallback 1: semantic kNN trên data/intent_classify.train.jsonl, k=9, OOS distance 0,483609, ambiguity margin 0,08.
- Fallback 2: rule router; confidence dưới route_min_confidence=0,55 chuyển clarify.
- _intent_patch.py chỉ đổi một số kết quả clarify thành advise khi đã có tín hiệu ca mụn xác lập; đây là patch bù data bias, cần được đưa vào ablation.

### 3.4.7. Trích xuất dữ kiện có cấu trúc

Runtime contract chính:

- context: age, sex, skin_type, is_pregnant, is_breastfeeding, duration_weeks, allergies, current_products, medications.
- clinical: lesion_types, inflammation_level, lesion_distribution.
- mỗi scalar/list item có value và confidence.

Schema core còn các field legacy như scarring/hormonal/goals, nhưng unified prompt không yêu cầu chúng; không nên mô tả chúng là đầu ra đều đặn của model hiện tại.

### 3.4.8. Hợp nhất dữ kiện với phiên hội thoại

Chỉ intent advise fold history/profile. Stable identity được điền nếu current turn thiếu; list thuốc/sản phẩm được union có tombstone; phủ định có thể xóa; topic shift thay location/lesion; inflammation lấy mức cao hơn để tránh hạ rủi ro lặng lẽ.

### 3.4.9. Kiểm tra tính đầy đủ của thông tin

Không có completeness score/gate trong đường live. Cơ chế hiện tại:

- confidence field thấp không được đưa vào confirmed profile;
- confidence_hint nêu field thiếu/không chắc cho generator;
- clarify intent từ router có template hỏi một câu;
- history giúp model tránh hỏi lại.

asked_fields và total_clarify_count còn trong schema/store nhưng runtime stream không đánh dấu asked_fields; vì vậy chưa có bộ chống lặp câu hỏi deterministic đang hoạt động.

### 3.4.10. Kết quả đầu ra của intake

IntakeResult chứa user, clean_text, history, selected mode, route decision/flags, extraction confidence, confirmed profile, retrieval query, scope refusal, turn snapshot và dữ liệu audit. Downstream không nhận một “diagnosis”.

## 3.5. Thiết kế quản lý phiên hội thoại

### 3.5.1. Mục tiêu của quản lý phiên

Giữ ngữ cảnh follow-up vừa đủ, tái sử dụng facts an toàn đã xác nhận và hạn chế mang nhầm thông tin cũ sang chủ đề mới.

### 3.5.2. Mô hình dữ liệu của một phiên

Session có id, timestamps, schema_version, asked_fields, clarify/follow-up counters. Turn có role, content, mode, used_chunks, normalized snapshot và metadata.

### 3.5.3. Thiết kế lưu trữ phiên

DI thật dùng SQLiteSessionStore với WAL, foreign key và lock theo thread. In-memory SessionStore chỉ là fallback/test. SQLite không trim vật lý mỗi append; get_history trả window gần nhất.

### 3.5.4. Vòng đời của phiên hội thoại

Session được tạo/làm mới lười khi có turn, expire sau 1.800 giây idle, reset nếu schema version lệch. Frontend tạo UUID mới khi load hoặc bấm Xóa; nút Xóa chỉ đổi local session ID, không gọi API xóa bản ghi cũ.

### 3.5.5. Lưu lượt hội thoại

Sau khi generation hoàn tất, runtime append user rồi assistant. Nếu stream lỗi trước persistence, turn có thể không được lưu đầy đủ. used_chunks được gắn vào assistant turn.

### 3.5.6. Bộ nhớ dữ kiện chuẩn hóa

Snapshot chỉ lưu cho advise. build_confirmed_profile dùng ngưỡng max(0,82, extract_min_field_conf), cao hơn ngưỡng extraction 0,60, để chỉ giữ stable/safety facts tương đối chắc.

### 3.5.7. Xử lý thông tin sửa đổi và phủ định

Rule fold nhận biết stop phrases cho thuốc/sản phẩm, xử lý phủ định thai kỳ và tombstone list. Explicit topic shift thay facts tổn thương/vị trí. Đây là heuristic, cần test riêng các phủ định phức tạp.

### 3.5.8. Hồ sơ người dùng đã xác nhận

Hồ sơ có thể giữ age, sex, pregnancy, breastfeeding, allergies, current_products và medications; khi render prompt safety block hiện chỉ đưa pregnancy/breastfeeding/allergies/medications, không đưa current_products vào block “đã xác nhận”.

### 3.5.9. Lựa chọn lịch sử cho prompt

Advise có thể dùng tối đa 6 turn trong budget 2.000 ký tự; knowledge chỉ lấy previous user turn gần nhất. History được sanitize trước render.

### 3.5.10. Theo dõi câu hỏi làm rõ

Store hỗ trợ asked_fields nhưng stream hiện không sử dụng để de-duplicate câu hỏi. Việc tránh hỏi lặp dựa chủ yếu vào prompt history và policy trong model SYSTEM.

### 3.5.11. An toàn và giới hạn của quản lý phiên

- Không có user authentication nên session_id do client gửi là boundary yếu.
- Audit và session là SQLite local, không mã hóa ở application layer.
- PII masking chỉ áp dụng một số field audit khi detector kích hoạt; assistant response và extracted_entities có thể còn chi tiết nhạy cảm.
- History window giảm context leak nhưng không loại bỏ hoàn toàn stale/incorrect fact.

## 3.6. Thiết kế thành phần tạo prompt và sinh phản hồi

### 3.6.1. Vai trò của thành phần tạo prompt

PromptBuilder chuyển IntakeResult và RetrievalOutput thành input cuối cho generator. Nó không route lại intent và không tự suy ra diagnosis; nhiệm vụ là sắp xếp dữ kiện theo độ tin cậy, áp template và giới hạn context.

### 3.6.2. Kiến trúc prompt hai tầng

- Tầng system: nằm trong model Ollama vì llm_use_modelfile_system=True.
- Tầng user: Jinja template được render ở mỗi turn từ current message, safety facts, history, prompt note và retrieved chunks.

PromptBuilder trả system rỗng trong cấu hình này. Vì vậy việc đồng bộ Modelfile đang nạp là điều kiện bắt buộc; chỉnh file source mà không chạy lại ollama create sẽ không đổi system runtime.

### 3.6.3. Thiết kế system prompt

System của generator quy định vai trò AcneLLM, phạm vi mụn, không chẩn đoán/kê đơn/liều, nhóm cần thận trọng, thứ tự grounding, tiếng Việt, phong cách và chống jailbreak. Baseline thực tế phải lấy từ Ollama /api/show; file model/Modelfile chỉ là desired source và đang có drift với model đã nạp.

### 3.6.4. Lựa chọn user template

| Điều kiện | Template | Hợp đồng câu trả lời |
|---|---|---|
| Hard scope/medication/injection refusal | refuse_user.j2 | Từ chối ngắn, nêu lý do an toàn |
| Soft out-of-scope reject | reject_user.j2 | Hai câu, không mang dữ liệu profile/RAG |
| Clarify | clarify_user.j2 | Một câu hỏi làm rõ |
| Knowledge | knowledge_user.j2 | Giải thích kiến thức, có nguồn nếu retrieval có |
| Advise mặc định | stream_user.j2 | Tư vấn sơ bộ theo facts và context |

### 3.6.5. Tổng hợp dữ kiện người dùng

Template nhận UserInput đã fold cho advise. Current message vẫn là nguồn ưu tiên; field confidence thấp không được biến thành lời khẳng định chắc. prompt_note hiện là kênh chính nhắc generator về field thiếu hoặc không chắc.

### 3.6.6. Bổ sung dữ kiện an toàn đã xác nhận

Confirmed safety block chỉ render các facts có độ tin cậy cao: thai kỳ, cho con bú, dị ứng và thuốc. Dữ kiện này được đặt sau history nhưng trước current user theo thứ tự ưu tiên logic của system.

### 3.6.7. Chuyển route flags thành chỉ dẫn ngữ cảnh

**Không mô tả sai rằng route flags đang được chuyển thành một guidance block trong prompt.** Source hiện đã bỏ known_facts và route_guidance khỏi PromptBuilder. Flags còn tác động ngoài prompt:

- crisis_signal thêm empathy prefix;
- progress_followup tăng counter/metadata;
- urgency_red_flag và multi_condition có thể thêm suffix chuyển tuyến;
- product_safety_check, repeated_question và emotional_distress chủ yếu được ghi metadata, không có instruction riêng trong prompt hiện tại.

Đây là khoảng cách giữa tên đề mục và runtime thật; nếu muốn khôi phục route guidance phải triển khai và đánh giá như thay đổi mới.

### 3.6.8. Đưa lịch sử hội thoại vào prompt

History block lấy các turn đã chọn, giới hạn 6 turn/2.000 ký tự, sanitize role/content và đặt trước current message. Knowledge chỉ dùng một user turn gần nhất để giảm việc mang ca cá nhân vào câu hỏi kiến thức.

### 3.6.9. Xây dựng khối tài liệu tham khảo

Mỗi chunk được gắn nhãn nguồn, title, URL và score; text được cắt theo budget. Tổng context chat tối đa 6.000 ký tự, số chunk cuối tối đa 5. Generator được yêu cầu chỉ nêu tên nguồn cụ thể khi nguồn đó thực sự có trong block.

### 3.6.10. Làm sạch dữ liệu trước khi render

PromptBuilder loại control characters, HTML, Jinja delimiters và các pattern injection khỏi user/history/chunk. Sanitization giảm nguy cơ prompt injection từ KB nhưng không phải parser bảo mật hoàn chỉnh và không xác minh tính đúng của nội dung nguồn.

### 3.6.11. Giao tiếp với Ollama

Cấu hình hiệu lực của generator: acne-generator, fallback qwen2.5:3b, num_ctx 8192, num_predict 2048, temperature mặc định 0,35, top_p 0,85, top_k 40, repeat_penalty 1,1, repeat_last_n 128, keep_alive=-1, timeout 300 giây. UI hiện override temperature thành 0,2 theo request mặc định. Knowledge gửi num_predict=-1.

OllamaBackend gửi request sync; FastAPI đưa một số call blocking sang thread. Nó log token budget khi Ollama trả counters và retry fallback một lần chỉ với lỗi runner termination.

### 3.6.12. Kết quả của quá trình sinh phản hồi

Đầu ra live là prose token stream, không phải AdviseOutput JSON. Cùng với text, client nhận source events và done metadata. CJK được loại theo regex; không có Markdown renderer ở frontend nên output được hiển thị bằng pre-wrap plain text.

## 3.7. Thiết kế lớp kiểm soát an toàn

### 3.7.1. Mục tiêu của safety layer

Giảm nguy cơ trả lời ngoài phạm vi, làm theo yêu cầu injection, khuyên thuốc chống chỉ định, bỏ sót chuyển tuyến và làm lộ PII. Safety layer là lớp giảm rủi ro, không phải bằng chứng hệ thống an toàn lâm sàng.

### 3.7.2. Kiến trúc kiểm soát nhiều lớp

1. HTTP/intake input limit.
2. pre_check cho empty/injection/PII.
3. hard scope và medication gate trước model.
4. route/reject và safety flags.
5. SYSTEM policy trong model.
6. prefix/suffix trên output stream.
7. structured post_check cho caller cấu trúc, hiện không nối vào SSE.
8. audit/test/metric.

### 3.7.3. Kiểm soát đầu vào

Prompt injection pattern gây hard refusal trước retrieval. PII detector gắn cờ và dùng mask_pii cho một số trường audit nhưng không từ chối người dùng. Input Unicode/control được chuẩn hóa.

### 3.7.4. Kiểm tra phạm vi tư vấn

Hard rule chặn yêu cầu chỉ về vùng sinh dục/hậu môn và một số yêu cầu nguy hiểm. Ngoài phạm vi thông thường dùng router soft reject với UserInput tối giản, không history, không extraction, không RAG. OOD embedding detector không hoạt động trong DI hiện tại.

### 3.7.5. Phát hiện tín hiệu rủi ro y tế

Route flags gồm crisis_signal, urgency_red_flag, product_safety_check và multi_condition. Clinical schema còn red_flags_input từ rule extractor. Các tín hiệu này là heuristic từ text; chưa có sensitivity/specificity được đo.

### 3.7.6. Kiểm tra thuốc và tương tác thuốc

DrugChecker nạp 20 entries từ config/drugs_acne.yaml và có đường fallback OpenFDA. Nó kiểm contraindication theo pregnancy/breastfeeding/age và interaction giữa thuốc. Rule current-turn canonical hóa retinoid/tetracycline trước khi model extraction.

YAML chứa cả cảnh báo và một số hướng dẫn tần suất/nồng độ. Không nên đưa nguyên văn database này vào trả lời mà không review y khoa; runtime hard gate chỉ nên dùng phần contraindication/interaction có thẩm định.

### 3.7.7. Quyết định từ chối vì rủi ro thuốc

medication_safety_refusal chạy ba lần: từ raw current text, sau extraction và sau fold session. Các ca chính: retinoid/cycline trong thai kỳ/cho con bú, isotretinoin cùng tetracycline, hoặc contraindication/interaction critical từ DrugChecker. Khi có refusal, generator vẫn viết lời từ chối theo template, sau đó suffix củng cố cảnh báo.

### 3.7.8. An toàn trong system prompt

System cấm chẩn đoán chắc, kê đơn/liều, thủ thuật tại nhà; yêu cầu chuyển tuyến cho nodule/cyst, sẹo, nhiễm trùng, distress; nêu rule thai kỳ/trẻ em; yêu cầu grounding và chống jailbreak. Hiệu lực phụ thuộc system thực sự trong Ollama, không chỉ file source.

### 3.7.9. Xử lý tín hiệu khẩn cấp và nhiều tình trạng da

- crisis_signal thêm câu đồng cảm và gợi ý liên hệ người thân/chuyên gia tâm lý trước nội dung da.
- urgency_red_flag có thể thêm cảnh báo đi cơ sở y tế.
- multi_condition thêm khuyến nghị bác sĩ da liễu vì phác đồ có thể xung đột.

Hiện không có phân loại khủng hoảng tâm lý chuyên dụng, số hotline theo địa phương hay escalation đến người thật.

### 3.7.10. Kiểm soát đầu ra dạng streaming

Runtime stream token ngay khi nhận từ Ollama, chỉ loại CJK. Sau khi model kết thúc, get_safety_suffix dò retinoid, lời khuyên thuốc kê đơn, trẻ dưới 12, urgent flags, multi-condition và self-procedure để nối warning.

Hệ quả: nếu model đã stream một câu nguy hiểm, suffix chỉ cảnh báo sau đó; nó không thu hồi token. Muốn hard output safety phải buffer toàn bộ/đoạn câu trước emit, hoặc có classifier/rewrite gate được kiểm chứng.

### 3.7.11. Post-check đối với đầu ra có cấu trúc

GuardrailRunner.post_check xử lý AdviseOutput theo config/guardrails.yaml: rewrite retinoid thai kỳ, inject red flag, strip phrase và disclaimer. Nhưng live user-facing path sinh prose và không gọi hàm này. Chỉ được mô tả đây là capability cho structured callers/test, không phải lớp bảo vệ SSE hiện hành.

### 3.7.12. Ghi nhận và bảo vệ dữ liệu audit

AuditStore lưu SQLite và hỗ trợ query/admin/feedback. Khi PII được phát hiện, user/query có thể được mask. Tuy nhiên assistant response, extracted_entities và dữ kiện phiên không được bảo đảm mask toàn bộ. API key đang rỗng làm admin endpoints mở trong mạng có thể truy cập backend.

### 3.7.13. Giới hạn của safety layer

- Rule/YAML có thể false positive/false negative.
- Active model prompt có drift.
- No hard post-generation rewrite cho SSE.
- Không có clinician review trong loop.
- Không có encryption-at-rest hoặc retention policy ngoài session TTL.
- Safety metric hiện dựa một phần vào LLM judge; cần calibration người.
- YAML thuốc cần clinical source/version/owner rõ ràng.

## 3.8. Thiết kế thành phần truy xuất tri thức hỗ trợ

### 3.8.1. Vai trò và phạm vi của retrieval

Retrieval cung cấp bằng chứng phụ cho advise/knowledge, không định tuyến intent và không quyết định diagnosis. Khi không sẵn sàng hoặc không còn chunk sau lọc, generator chạy llm_only.

### 3.8.2. Tổ chức cơ sở tri thức

Pipeline:

documents.jsonl → lọc quality → chunk 200/overlap 40/min 50 → exact/near dedup → chunks.jsonl → Chroma embeddings + BM25 pickle/checksum.

KBChunk giữ chunk_id, doc_id, text, vị trí, liên kết prev/next, URL, title, source_name/type, trust, language, categories và tags. Guideline PDF có pipeline riêng tạo chunks_guideline.jsonl rồi merge và re-embed phần guideline.

### 3.8.3. Kiểm tra trạng thái sẵn sàng

DI chỉ coi RAG ready khi thư mục Chroma có dữ liệu và file BM25 tồn tại/load thành công. Chroma/BM25 mismatch hoặc exception làm container hạ về llm_only. Snapshot này đã xác nhận cả hai có cùng 24.393 item.

### 3.8.4. Điều kiện kích hoạt retrieval

Intent phải là advise/knowledge, effective mode hybrid, RAG ready, không refusal/clarify/reject và query vượt qua eligibility. Safety/guideline passes chạy trong retrieve_for_chat khi main retrieval được gọi.

### 3.8.5. Xây dựng truy vấn retrieval

Query ưu tiên current clean text, tối đa khoảng 700 ký tự; mở rộng một số alias BHA/BPO/Differin/blackhead/nodule và safety terms; có thể nối một previous user turn khoảng 300 ký tự. Runtime cố ý không dùng các nhãn structured suy đoán làm query chính để giảm semantic distortion.

### 3.8.6. Truy xuất thưa bằng BM25

BM25Okapi dùng tokenization underthesea hoặc whitespace fallback, bỏ stopword và chỉ giữ score dương. Index pickle bắt buộc có file .sha256; thiếu hoặc mismatch làm load lỗi thay vì tin binary không rõ nguồn.

### 3.8.7. Truy xuất dense bằng ChromaDB

Dense query dùng embedding model hiện hành, fetch tối đa min(top_k×3, 60), cosine distance tối đa 0,60 và không fallback raw khi mọi vector vượt ngưỡng. Chroma collection là acne_kb_vi, hnsw space cosine.

### 3.8.8. Hợp nhất kết quả hybrid

RRF dùng k=60. Sau fusion, score được boost theo source_type: NICE/AAD 1,60; clinical_textbook 1,50; JID 1,30; PubMed review 1,20; forum 0,80; blog 0,70; nguồn khác mặc định 1,0; authority tags nhân thêm 1,15. Chunk dưới max(0,005, 30% score tốt nhất) bị loại.

### 3.8.9. Guideline pass và safety pass

- Guideline pass chạy cho mọi query, giới hạn các source type có thẩm quyền và lấy tối đa 5.
- Safety pass chỉ chạy khi text có term y khoa/rủi ro liên quan, lấy tối đa 5 nguồn thẩm quyền.
- Các pass được merge bằng RRF với main result.

### 3.8.10. Reranking kết quả

CrossEncoder BAAI/bge-reranker-v2-m3 chấm tối đa nhóm candidate đầu; code coi output là score đã dùng trực tiếp. Candidate dưới 0,30 bị bỏ ở reranker; chat áp floor cuối 0,50, lấy tối đa 5 và tối đa 1 chunk mỗi source. Nếu có candidate guideline, guideline slot có thể thay chunk yếu nhất để bảo đảm ít nhất một guideline trong final.

### 3.8.11. Lọc kết quả không phù hợp

Các filter xử lý nhầm boil với acne nodule, body region mismatch, noise, score thấp và duplicate source. MMR và neighbor expansion có implementation trong rag/retriever.py nhưng không được gọi trong chat path hiện tại.

### 3.8.12. Đưa kết quả retrieval vào prompt

Prompt context có badge nguồn, metadata và text; tổng tối đa 6.000 ký tự. Source event gửi chunk cho UI sau khi generation kết thúc. Sanitize chỉ giảm injection/noise, không xác minh citation entailment.

### 3.8.13. Đánh giá chất lượng bằng chứng

evidence_quality lấy trung bình reranker score: strong từ 0,90; moderate từ 0,50; weak dưới đó; unverified khi không RAG. Đây là label UI heuristic, không phải confidence y khoa hoặc groundedness của answer.

### 3.8.14. Cache kết quả retrieval

DiskCache lưu embedding không TTL và retrieval có TTL 3.600 giây, nén, giới hạn item khoảng 8 MB và hỗ trợ tag invalidation. Cache key v6 có query/top/floor/safety params nhưng chưa gắn đầy đủ model blob hash, prompt hash và KB manifest, nên rebuild KB/model cần invalidate rõ ràng.

### 3.8.15. Giới hạn của thành phần retrieval

- Source type/trust là metadata rule-based, có thể sai.
- Corpus có nhiều nguồn website/blog; boost không thay thế thẩm định nội dung.
- en_medical_site không có boost riêng trong bảng HybridRetriever và rơi về 1,0.
- Judge relevance không thay thế gold qrels/human clinical review.
- Không có citation entailment hard gate trước khi stream.
- Chroma fingerprint hiện dựa tên/kích thước file trong evaluation.common, chưa phải content hash từng vector/document.

## 3.9. Thiết kế giao tiếp giữa các thành phần

### 3.9.1. Kiến trúc giao tiếp

Browser gọi FastAPI qua HTTP; FastAPI gọi Ollama qua HTTP local; backend đọc SQLite/Chroma/BM25/DiskCache trực tiếp. Không có message broker hoặc service mesh.

### 3.9.2. Endpoint hội thoại streaming

GET /api/v1/chat/stream nhận message, session_id, mode và temperature; trả text/event-stream từ stream_chat_sse. Dùng GET làm message nằm trong query string, có nguy cơ xuất hiện trong access log/history/proxy URL.

### 3.9.3. Định dạng sự kiện SSE

Mỗi frame có một data line chứa JSON object với event và data:

- token: chuỗi text;
- source: chunk_id, source/title/url/score/text;
- error: thông báo lỗi;
- done: mode, latency, chunks, session, evidence và route metadata.

Không dùng field event: chuẩn SSE riêng; client parse event trong JSON payload.

### 3.9.4. Tiếp nhận SSE tại frontend

useSSE dùng fetch + ReadableStream, tách frame bằng hai newline và cập nhật Zustand. Đây không phải EventSource native, nên có thể gửi request linh hoạt nhưng source hiện chưa dùng AbortController, retry/backoff hay resume Last-Event-ID.

### 3.9.5. Giao tiếp qua WebSocket

/api/v1/ws/chat nhận JSON message, chạy cùng stream generator trong executor, đẩy qua asyncio.Queue tối đa 64 và gửi JSON event cho client. Frontend hiện không dùng WebSocket; đây là API thay thế.

### 3.9.6. Giao tiếp giữa backend và Ollama

OllamaBackend dùng /api/chat cho intake và generator, /api/tags cho health/model list, /api/show cho params. Intake dùng format JSON; generator dùng stream. HTTP client là sync nên phải tránh gọi trực tiếp trên event loop ở endpoint non-stream.

### 3.9.7. Endpoint feedback

POST /api/v1/chat/feedback nhận message_id, rating up/down và session_id, ghi AuditStore. Frontend chỉ hiện feedback với answer không phải clarify/refuse/error. message_id phía UI là UUID local, không phải khóa assistant turn trong session database.

### 3.9.8. Endpoint cơ sở tri thức

- POST /api/v1/kb/retrieve: retrieve/rerank thô.
- POST /api/v1/kb/search: KB Explorer, text cắt 300 ký tự.
- GET /api/v1/kb/stats: readiness/count/model.
- GET /api/v1/kb/chunk/{chunk_id}: full text/metadata.

Endpoint yêu cầu RAG ready, ngược với chat có thể degrade.

### 3.9.9. Endpoint trạng thái và model

GET /api/v1/health kiểm Ollama, Chroma count và BM25 loaded. status chỉ degraded khi Ollama lỗi; thiếu KB có thể vẫn trả status ok với kb_chunks=-1, vì vậy deploy gate cần kiểm từng field. GET /api/v1/models trả danh sách Ollama và model hiện tại.

### 3.9.10. Endpoint quản trị và giám sát

/api/v1/admin/audit, /sessions/stats, /feedback, /feedback/stats và /metrics. Metrics in-memory gồm request count, p50/p95/mean latency, guardrail trigger và HTTP 5xx; biến ollama_error_count thực tế tăng cho mọi status 5xx, không chỉ lỗi Ollama.

### 3.9.11. Middleware giao tiếp

RequestLogging tạo/echo X-Request-ID; APIKey hỗ trợ x-api-key hoặc Bearer; RateLimit dùng deque theo IP và asyncio.Lock; CORS allow_credentials=False. Hiệu lực snapshot: API key rỗng và CORS wildcard, phù hợp dev nhưng không an toàn khi mở LAN/Internet.

### 3.9.12. Xử lý lỗi giao tiếp

Input lỗi trả 422/400 tùy route; RAG endpoint trả 503; SSE catch exception rồi phát error và done; WebSocket phát event lỗi. Frontend giữ text đã nhận và đánh dấu error. Không có mã lỗi domain chuẩn hóa hoặc retry idempotent.

### 3.9.13. Giới hạn của thiết kế giao tiếp

GET query chứa nội dung nhạy cảm; API key không gắn user/role; WebSocket chưa được UI dùng; rate/metrics không chia sẻ giữa workers; không có TLS trong app; không có cancellation/backpressure end-to-end được kiểm chứng; admin/metrics đang có thể mở khi API key rỗng.

## 3.10. Thiết kế giao diện người dùng

### 3.10.1. Mục tiêu thiết kế

Một UI nội bộ gọn cho chat tiếng Việt, theo dõi mode/evidence/latency, xem nguồn, feedback và tra cứu KB. Không phải cổng bệnh án hay dashboard lâm sàng.

### 3.10.2. Bố cục tổng thể

Header có thương hiệu, ba tab Chat/KB/Cài đặt và nút Xóa; body đổi theo tab; Chat có vùng lịch sử scroll và footer input/disclaimer.

### 3.10.3. Màn hình khởi đầu

Hiển thị ba câu gợi ý: ca có tuổi/da/sản phẩm, câu mụn ẩn và câu thai kỳ/retinol. Bấm gợi ý gửi trực tiếp nếu chưa loading.

### 3.10.4. Khu vực nhập câu hỏi

Textarea auto-focus, Enter gửi, Shift+Enter xuống dòng, chặn khi loading hoặc quá 500 từ, hiển thị đếm từ từ mốc 400. UI không chặn 4.000 ký tự nhưng backend chặn.

### 3.10.5. Hiển thị lịch sử hội thoại

Zustand giữ mảng user/assistant trong memory tab. Assistant được tạo placeholder rồi nối token. Không hydrate từ SQLite khi reload, nên lịch sử backend và UI có thể khác.

### 3.10.6. Hiển thị trạng thái xử lý

Placeholder skeleton trước token; nút/input phản ánh loading; sau done hiển thị mode, evidence_quality và latency. Không có progress theo từng stage intake/retrieval/generate.

### 3.10.7. Hiển thị nguồn tham khảo

SourceCard suy luận badge source type từ metadata/source URL, hiển thị score bar, excerpt và link; modal xem full chunk. Score bar là reranker score, không nên đặt tooltip như độ tin cậy y khoa.

### 3.10.8. Thu thập feedback

Thumb up/down gửi POST và lưu trạng thái ở message local. Source hiện không có lý do feedback, comment tự do hay cơ chế sửa rating sau lỗi mạng rõ ràng.

### 3.10.9. Chức năng xóa hội thoại

clearMessages xóa local messages, tạo sessionId mới và reset loading. Nó không xóa session/audit cũ trên server; UI nên ghi đúng là “bắt đầu hội thoại mới” nếu cần tránh hiểu nhầm privacy.

### 3.10.10. Giao diện KB Explorer

Cho nhập query, chỉnh top K từ Settings, hiển thị chunk_id/source/score/excerpt và modal full text. topK này chỉ ảnh hưởng KB search, không ảnh hưởng chat RAG.

### 3.10.11. Giao diện cài đặt

Chọn mode auto/hybrid/llm_only, temperature 0–1 bước 0,1 và KB top K 1–12. Giá trị mặc định UI: mode auto, temperature 0,2, topK 5. Settings chỉ sống trong memory.

### 3.10.12. Quản lý trạng thái giao diện

Một Zustand store giữ messages, sessionId, loading và settings; update cuối assistant bằng cách tìm message assistant gần nhất. Không có persistence, optimistic retry queue hoặc multi-tab synchronization.

### 3.10.13. Khả năng sử dụng và hỗ trợ truy cập

Có aria-label ở nhiều nút/input, keyboard Enter/Shift+Enter, Escape đóng modal và focus lại input. Chưa thấy focus trap/restore đầy đủ cho modal, live region công bố token/status, kiểm thử screen reader hay accessibility audit.

### 3.10.14. Giới hạn của giao diện

Không login, không mobile/offline test được ghi nhận, không render Markdown/citation inline, không upload ảnh, không xem session server, không cancel stream, không ẩn admin/KB theo quyền và không bảo vệ URL nguồn độc hại ngoài rel=noreferrer.

## 3.11. Thiết kế cấu hình và triển khai

### 3.11.1. Mục tiêu thiết kế cấu hình

Tách default code khỏi override môi trường, cho phép đổi model/path/threshold mà không sửa business logic, và xây toàn bộ dependency qua một Container.

### 3.11.2. Quản lý cấu hình bằng Pydantic Settings

src/acne_llm/config.py định nghĩa Settings với env_file=.env và extra=ignore, sau đó tạo singleton settings. Kiểu Literal/list/number giúp validate một phần config lúc import.

### 3.11.3. Phân chia trách nhiệm giữa .env và config.py

config.py cung cấp default và type; .env override theo deployment. Baseline thật phải dump Settings đã resolve, không chép .env.baseline. Snapshot cho thấy .env đã override log_level=DEBUG, CORS wildcard và Ollama timeout 300 giây.

Không đưa secret vào báo cáo; chỉ ghi trạng thái set/empty và hash cấu hình redacted.

### 3.11.4. Cấu hình mô hình sinh phản hồi

Generator source/effective fields gồm URL/model/fallback/context/predict/sampling/repeat/keep_alive/timeout/use_modelfile_system. Cần lưu cả model ID Ollama và SYSTEM hash; tên tag acne-generator không đủ chứng minh lineage.

### 3.11.5. Cấu hình intake

intake_mode=unified, intake_model=acne-intaker, timeout 60 giây. Legacy extractor/router model còn trong Settings nhưng không được khởi tạo ở nhánh unified. DI tạo một OllamaBackend intake riêng, temperature 0, predict 768, context tối đa 4096 theo code; model đã nạp có num_ctx mặc định 2048.

### 3.11.6. Cấu hình embedding và retrieval

Embedding/reranker model, device, Chroma/BM25 path, top-k, score floor, dense max distance, context budget và cache đều từ Settings. Threshold hiệu lực chính: retrieve 25, final 5, reranker min 0,30, chat floor 0,50, max 1 chunk/source, dense distance 0,60.

### 3.11.7. Khởi tạo dependency container

build_container tạo session/audit/cache/guardrail, generator, unified intake, embedder/semantic router, Chroma/BM25/retriever/reranker và PromptBuilder. RAG init fail được catch để degrade; intaker/generator không được warm-up bằng một generation ở boot.

### 3.11.8. Kiến trúc triển khai cục bộ

Mô hình logic là Ollama:11434 + FastAPI:8000 + Next.js:3000. Snapshot máy có Windows 11; Python của .venv là 3.12.5 nhưng lệnh python trên PATH trỏ Python 3.10.11; Node 24.16.0; Ollama 0.32.1; CPU Ryzen 7 5800H, khoảng 24 GB RAM, RTX 3050 Ti Laptop 4 GB. Phải gọi explicit .venv/Scripts/python.exe để tái lập đúng môi trường dự án. Embedding/reranker cấu hình CPU; Ollama tự quyết backend phần cứng.

Các version này chỉ là môi trường snapshot, không tự động là môi trường thực nghiệm cuối.

### 3.11.9. Khởi chạy thủ công

Đường source hợp lệ:

1. bảo đảm Ollama có acne-intaker và acne-generator;
2. chạy uvicorn acne_llm.api.app:app --host 0.0.0.0 --port 8000;
3. trong frontend chạy npm run dev;
4. kiểm /api/v1/health và UI.

Không khởi động lại service chỉ để viết báo cáo; snapshot này xác nhận backend/frontend đang tắt.

### 3.11.10. Script khởi chạy nhanh

scripts/RUN.ps1 kiểm tra venv, tunnel SSH RunPod, hai model, dừng process cổng 8000, mở backend/frontend và chờ health. Nó chứa default endpoint remote cụ thể và yêu cầu owner cổng 11434 là ssh, nên không dùng được nguyên trạng cho Ollama local. scripts/run_all.sh là launcher desktop Linux đơn giản hơn.

### 3.11.11. Triển khai bằng Docker

Dockerfile backend dùng Python 3.11-slim, cài requirements, chạy non-root và uvicorn. Frontend Dockerfile multi-stage Node 20. docker-compose có Ollama, ollama-init, backend và frontend.

Khoảng lệch cần sửa/kiểm chứng:

- ollama-init chỉ tạo acnellm-v2-q4 hoặc pull qwen2.5:7b, không tạo acne-intaker;
- compose override generator thành acnellm-v2-q4, khác local baseline acne-generator;
- frontend build URL được bake thành localhost:8000, chỉ đúng khi browser truy cập cùng host;
- frontend Dockerfile copy thư mục public dù repo hiện không có public; phải chạy docker build thật để xác nhận cú pháp/hành vi;
- chưa có smoke E2E Docker trong snapshot.

### 3.11.12. Quản lý dữ liệu triển khai

Compose mount data và config; model nằm trong volume Ollama/init. Chroma, BM25, sessions, audit và cache đều là state mutable. Cần backup/version riêng, checksum BM25, KB fingerprint và migration policy trước deploy.

### 3.11.13. Cấu hình bảo mật triển khai

Production tối thiểu phải đặt API_KEY, CORS origins cụ thể, reverse proxy TLS, tách/quyền hóa admin, không log query nhạy cảm trong URL, giới hạn retention, quyền file SQLite và secret manager. Snapshot hiện không đạt các gate này.

### 3.11.14. Kiểm tra trạng thái sau triển khai

Không chỉ kiểm status=ok. Gate nên kiểm:

- /health: ollama=true, model đúng tag+blob, kb_chunks đúng manifest, bm25_loaded=true;
- /models có cả intake/generator;
- một trace non-mutating cho advise/knowledge/reject/safety;
- một SSE smoke có token, done và source khi hybrid;
- frontend parse stream, feedback và KB;
- prompt/model hashes khớp release manifest.

### 3.11.15. Giới hạn của thiết kế triển khai

Single process/local state, no autoscaling, no distributed cache/rate/metrics, launcher và Compose drift, default auth yếu, model tags mutable, chưa có migration orchestration và chưa có release manifest thống nhất cho source+prompt+model+KB.

## 3.12. Kịch bản hoạt động của hệ thống

### 3.12.1. Kịch bản tư vấn mụn với thông tin tương đối đầy đủ

Input có tuổi, da, tổn thương, vị trí, thời gian và sản phẩm → route advise → extract/fold → hybrid nếu RAG ready → stream template → source/done → lưu snapshot. Hệ thống không còn completeness gate bắt buộc nên có thể trả lời trực tiếp dù thiếu một field.

### 3.12.2. Kịch bản thiếu thông tin cần thiết

Nếu intaker route clarify, không extraction/RAG và clarify template hỏi đúng một câu. Nếu route advise nhưng field thiếu/low confidence, confidence_hint giao generator quyết định hỏi; hành vi này không deterministic.

### 3.12.3. Kịch bản hỏi kiến thức tổng quát

Route knowledge, không fold profile cá nhân, chỉ một previous user turn, hybrid retrieval nếu sẵn sàng, knowledge template, num_predict=-1 và bỏ generic disclaimer theo logic suffix khi phù hợp.

### 3.12.4. Kịch bản yêu cầu ngoài phạm vi

Hard scope/injection → refuse template; soft OOS → reject template với input tối giản, không history/extraction/RAG. Generator viết wording nên phải đánh giá refusal fidelity và leakage.

### 3.12.5. Kịch bản có nguy cơ liên quan đến thuốc

Medication gate chạy trước/sau extraction/sau fold. Nếu contraindication critical, tạo refusal; nếu model vẫn đề cập thuốc kê đơn, suffix thêm cảnh báo. Đây là ca safety phải có test deterministic và human review.

### 3.12.6. Kịch bản xuất hiện dấu hiệu cần thăm khám sớm

Urgency/multi-condition/severe signals được đưa vào flags/clinical; SYSTEM yêu cầu chuyển tuyến và suffix có thể bổ sung. Vì structured post-check không chạy live, phải đo tỷ lệ bỏ sót referral trên output thật.

### 3.12.7. Kịch bản kho tri thức không sẵn sàng

Container đặt rag_ready=false và intake auto chọn llm_only; chat vẫn có thể trả lời. KB endpoints trả 503. UI evidence là unverified và không có source.

### 3.12.8. Kịch bản không tìm được tài liệu đủ liên quan

Dense distance/reranker/filter loại hết candidate → retrieval None → llm_only/unverified. Không được ép một chunk yếu chỉ để hiện citation; guideline slot chỉ hoạt động khi còn candidate hợp lệ.

### 3.12.9. Kịch bản xảy ra lỗi trong quá trình xử lý

SSE phát error rồi done; frontend đánh dấu bubble lỗi. Runner termination có thể thử fallback generator một lần. Lỗi intake có semantic/rule fallback; lỗi toàn container/model không có circuit breaker ứng dụng.

### 3.12.10. Kịch bản gửi phản hồi đánh giá

Sau answer thông thường, người dùng bấm up/down; frontend POST message UUID và session; AuditStore ghi feedback, admin endpoint tổng hợp. Feedback không tự trở thành label huấn luyện.

### 3.12.11. Nhận xét về các kịch bản hoạt động

Các kịch bản cho thấy hệ thống degrade được nhưng có hai nhánh không deterministic cần thực nghiệm: generator tự quyết clarification và safety suffix chỉ bổ sung sau stream. Kịch bản phải được lưu bằng common sample IDs để so pipeline và ablation theo cặp.

# CHƯƠNG 4: ĐÁNH GIÁ KẾT QUẢ THỰC NGHIỆM

> **Trạng thái bắt buộc của chương này trong bản hiện tại: CHƯA CÓ KẾT QUẢ THỰC NGHIỆM ĐƯỢC CHẤP NHẬN.**  
> Repository có runner, dataset, notebook output và các thư mục report cũ, nhưng tài liệu này không chép điểm/loss/thời gian từ đó. Dataset eval_set.v3 hiện không khớp SHA-256 trong MANIFEST; intake_eval.v2 chưa có entry trong MANIFEST; active Ollama prompts không khớp source. Ba điều này đủ để chặn kết luận.

## 4.1. Mục tiêu và phạm vi thực nghiệm

### 4.1.1. Mục tiêu thực nghiệm

Đo riêng từng layer và đo E2E để trả lời model/pipeline nào tạo ra cải thiện hoặc lỗi:

1. Unified intake có route/extract đúng và calibrated không?
2. RAG có mang về context liên quan, đủ và có thứ hạng tốt không?
3. Generator fine-tuned có tốt hơn base khi giữ nguyên prompt/context không?
4. Safety/refusal có giảm lỗi critical mà không từ chối quá mức không?
5. Chi phí latency/memory của từng layer có chấp nhận được không?

### 4.1.2. Câu hỏi thực nghiệm

- Q1: So với Qwen2.5-7B-Instruct base, ROLE LoRA cải thiện answer_quality và role_tone hay chỉ thay đổi phong cách?
- Q2: So với raw current message, unified intake + session fold giúp hay làm méo facts/intent?
- Q3: RAG thật cải thiện sufficiency/groundedness so với no-RAG không?
- Q4: Oracle intake, oracle retrieval hoặc frontier generator tạo ceiling gain lớn nhất?
- Q5: Những lớp nào gây safety failure, missed refusal, missing content hoặc latency?
- Q6: Kết quả có giữ khi tách theo intent, risk group, ngôn ngữ, multi-turn và source type không?

### 4.1.3. Phạm vi và nguyên tắc đánh giá

- Tách train/validation/holdout/eval; kiểm exact và semantic contamination.
- So sánh paired trên cùng sample_id và cùng input contract.
- Chất lượng và safety báo riêng; không bù một safety event bằng điểm trung bình cao.
- Không trộn judge provider/model/prompt khác nhau trong một artifact.
- Dòng lỗi, timeout, no-context và bị loại phải có count, ID và reason.
- Kết quả từ nhãn synthetic_pending_review chỉ là directional cho đến khi human review.
- Không dùng một run smoke để kết luận cho full dataset.

## 4.2. Môi trường triển khai và cấu hình thực nghiệm

### 4.2.1. Môi trường phần cứng

Máy snapshot hiện tại: Ryzen 7 5800H 8 core/16 thread, khoảng 24 GB RAM, RTX 3050 Ti Laptop 4 GB. Đây phù hợp cho kiểm thử local nhưng notebook QLoRA được viết cho môi trường GPU Colab 16 GB trở lên. Khi chạy thật phải ghi:

- tên GPU, VRAM, driver, CUDA;
- CPU/RAM/disk;
- power mode và process cạnh tranh;
- local hay RunPod/Colab;
- warm/cold model state.

Không gộp latency của local CPU RAG với latency generator trên remote tunnel mà không ghi rõ topology.

### 4.2.2. Môi trường phần mềm

Snapshot: Windows 11 64-bit; .venv Python 3.12.5, trong khi python trên PATH là 3.10.11; torch 2.5.1+cu121; transformers 5.6.1; chromadb 1.5.8; FastAPI 0.136.0; Pydantic 2.13.3; Node 24.16.0; npm 11.13.0; Ollama 0.32.1. Mọi command thực nghiệm phải ghi executable thật, không chỉ ghi “python”.

Notebook pin transformers 4.56.2, datasets 4.3.0, trl 0.24.0, protobuf 5.29.6 và cài Unsloth từ Git. Cần pin commit Unsloth/Unsloth Zoo thay vì branch latest để tái lập.

### 4.2.3. Cấu hình huấn luyện

Cấu hình theo notebook, chưa phải kết quả:

| Hạng mục | Giá trị code |
|---|---|
| Base | unsloth/Qwen2.5-7B-Instruct-bnb-4bit |
| Sequence length | 2048 |
| Batch/GAS | 4 / 4, effective 16 |
| Epoch | 3 |
| Learning rate | 2e-4 |
| Warmup/scheduler | 0,03 / cosine |
| Optimizer | AdamW 8-bit, weight decay 0,01 |
| Eval/save | mỗi 100 step |
| Early stop | patience 3 |
| Seed | 3407 |
| Precision | bf16 nếu GPU hỗ trợ, ngược lại fp16 |
| Packing | false |

### 4.2.4. Cấu hình vận hành hệ thống

Phải lưu dump Settings redacted cùng run. Baseline source hiệu lực hiện gồm unified intake, generator acne-generator, intake acne-intaker, RAG 25→5, context 6.000 ký tự, rerank floor 0,50, embedding/reranker CPU, session TTL 1.800 giây.

Ngoài config Python phải lưu:

- Ollama model ID/digest;
- /api/show SYSTEM hash và parameters;
- hash tất cả Jinja prompt;
- KB chunk hash, Chroma/BM25 fingerprint;
- UI temperature hoặc request override;
- trạng thái fallback/cache/warm-up.

### 4.2.5. Triển khai và kiểm soát tính tái lập

Mỗi run tạo một manifest bất biến:

1. run_id, timestamp UTC, command đầy đủ;
2. commit HEAD + dirty patch SHA-256;
3. Python/package/OS/hardware;
4. dataset path, row count, content SHA-256, annotation version;
5. model tag + blob ID + SYSTEM hash;
6. prompt/template/config redacted hashes;
7. KB/BM25/Chroma fingerprints;
8. seed/sampling/cache policy;
9. per-sample output, error, latency và used chunks.

Runner evaluation.common đã ghi một phần commit/Python/platform/KB; cần mở rộng các field còn thiếu.

## 4.3. Xây dựng dữ liệu fine-tuning

### 4.3.1. Mục tiêu và quy trình tạo dữ liệu

Repo có ba dòng dữ liệu cần phân biệt:

- datagen/roledata: dạy vai trò, giọng, grounding, từ chối và safety cho generator;
- datagen/intakedata: dạy JSON contract cho unified intake;
- LLMData/chunk_qa: pipeline Q&A lâm sàng/safety đời trước dựa trên KB chunks.

Quy trình hiện đại có provider generation, schema validation, gate, rejected audit, checkpoint/resume, split và export. Không trộn ba dataset nếu system/schema không parity.

### 4.3.2. Phân nhóm dữ liệu

ROLE taxonomy:

- R1–R10: identity, depth, nonjudgment, empathy, clarification, role boundary, conversation glue, jailbreak, multi-turn, special population;
- B1–B5: grounding, missing answer, irrelevant chunk, conflicting docs, depth anchor;
- K1: knowledge anchor.

Unified Intake taxonomy phủ advise self-report, knowledge, clarify, reject jailbreak/OOS/unsafe prescription và các field/context/clinical cases. Mỗi group phải báo quota thực nhận, reject reasons và coverage, không chỉ target.

### 4.3.3. Cấu trúc và đa dạng hóa dữ liệu

ROLE record dùng messages system/user/assistant cùng sample_kind và gate metadata. Intake record dùng history tối đa 3 item, user turn và assistant JSON đúng root intent/confidence/description/context/clinical. Datagen điều khiển cách xưng hô, có/không dấu, teencode nhẹ, độ dài, single/multi-turn, phủ định, mơ hồ, safety và grounding.

### 4.3.4. Kiểm soát chất lượng

Các gate source có:

- schema và enum/range/confidence;
- byte parity của system anchor;
- Vietnamese-only/role-specific behavior;
- grounded rate cho case có context;
- duplicate ID/user turn và phrase frequency;
- exact overlap với evaluation users;
- rejection audit và corpus revalidation;
- safety cases trong holdout.

Cần bổ sung review người cho correctness y khoa, naturalness, label intent/severity và false rejection; deterministic gate không đủ thẩm định clinical content.

### 4.3.5. Phân chia và xuất dữ liệu

ROLE split code dùng 85% train, 8% validation, 7% holdout, seed 42, stratified theo case và buộc safety cases vào holdout. Artifact hiện có 2.945/277/243 rows; tổng này là inventory file, thấp hơn target cấu hình 3.500 nên không được tự nhận là full target đã hoàn tất.

Notebook dùng đúng ba split trên. Export kiểm schema/system parity, chỉ giữ id+messages, tạo dataset_info và checksum.

Intake datagen dùng split case-aware 90/10 train/validation; evaluation intake phải là bộ riêng, không tái sử dụng train rows.

### 4.3.6. Hạn chế của dữ liệu

- Phần lớn dữ liệu là synthetic, có provider/style bias.
- Grounded answers phụ thuộc chất lượng KB source.
- Exact decontamination không bắt mọi semantic paraphrase.
- Severity/medical facts cần clinician review.
- Active Ollama system đang drift khỏi anchor source.
- Các file style guide Markdown không được dùng làm căn cứ trong audit này; nội dung của chúng phải được review riêng nếu là một phần datagen contract.
- Dataset eval hiện chưa ở trạng thái freeze hợp lệ.

## 4.4. Fine-tuning bằng QLoRA

### 4.4.1. Lựa chọn phương pháp

QLoRA phù hợp mục tiêu repo là điều chỉnh hành vi/role của model 7B trong VRAM giới hạn. Báo cáo không nên tuyên bố QLoRA tăng tri thức y khoa; KB và safety vẫn là layer riêng.

### 4.4.2. Chuẩn bị dữ liệu

Notebook load train/val/holdout JSONL, kiểm messages roles và bắt ANCHOR_SYSTEM từ train row đầu. Sau đó apply_chat_template thành text, bỏ cột phụ và đo token length để tránh vượt 2048. Trước run thật phải verify mọi row, không chỉ 50 row đầu.

### 4.4.3. Cấu hình LoRA và huấn luyện

r=16, alpha=32, dropout=0,05, bias=none, tất cả projection attention/MLP, gradient checkpointing Unsloth, no rsLoRA/LoftQ. SFTTrainer eval/save theo step, load best model theo eval_loss.

Nên chạy ít nhất ba seed hoặc báo rõ single-seed uncertainty. Cấu hình source hiện chỉ có seed 3407.

### 4.4.4. Mask loss trên phản hồi

train_on_responses_only đặt label=-100 cho system/user và chỉ tính loss assistant, với delimiter ChatML user/assistant. Cần sanity test số token được giữ ở mọi split và báo tỷ lệ masked; delimiter lệch tokenizer có thể làm loss rỗng.

### 4.4.5. Lựa chọn checkpoint

Code chọn best checkpoint bằng eval_loss và early stopping. Đây mới là tiêu chí huấn luyện; checkpoint cuối để deploy phải vượt holdout behavior/safety/ablation gates, không chỉ có eval_loss thấp nhất.

## 4.5. Kết quả quá trình fine-tuning

### 4.5.1. Diễn biến loss

**Chưa điền số liệu.** Khi chạy, xuất train_loss/eval_loss theo step/epoch, learning rate, gradient norm và seed; vẽ đường có trục/đơn vị và đánh dấu best checkpoint/early stop. Không sao chép output đang lưu trong notebook nếu chưa chứng minh dataset/model/code hash của run.

### 4.5.2. Lựa chọn checkpoint

**Chưa có checkpoint được chấp nhận trong báo cáo.** Bảng sau này phải gồm checkpoint, eval_loss, holdout role/safety metrics, model hash và lý do chọn; so best-loss với final checkpoint.

### 4.5.3. Thời gian và hiệu quả tham số

**Chưa đo.** Cần log wall-clock, GPU-hours, peak VRAM, trainable/total parameters, throughput samples/tokens per second, effective batch và chi phí. Không suy ra thời gian từ comment notebook.

### 4.5.4. Artifact sau huấn luyện

Repo hiện có LoRA adapter, checkpoint-300/500/555, zip adapter, merged/GGUF Q4_K_M, Modelfile và intake release. Sự tồn tại của file không chứng minh artifact nào tạo ra active acne-generator/acne-intaker. Trước khi dùng phải lập manifest SHA-256 liên kết:

dataset → notebook/code → base revision → adapter checkpoint → merge → GGUF → Modelfile → Ollama blob ID.

### 4.5.5. Nhận xét kết quả

**Chưa được phép kết luận mô hình tốt hơn base hoặc an toàn hơn.** Chỉ nhận xét sau khi có paired holdout/E2E, safety counts riêng, judge calibration và lineage hợp lệ.

## 4.6. Đóng gói và tích hợp mô hình

### 4.6.1. Quy trình đóng gói

Notebook lưu adapter, merge 16-bit, export GGUF Q4_K_M, tạo zip. Intake release cũng chứa GGUF Q4_K_M và Modelfile. Release nên bỏ bước chọn file GGUF “đầu tiên tìm thấy” và dùng path/hash explicit.

### 4.6.2. Xây dựng Modelfile

Modelfile chỉ định FROM GGUF/base, SYSTEM, stop token và default sampling/context. Với runtime gửi options qua API, cần test precedence giữa default Modelfile và request. SYSTEM phải được lấy từ canonical source và hash sau ollama create.

### 4.6.3. Nạp mô hình vào Ollama

Quy trình dự kiến: giải nén GGUF+Modelfile, chạy ollama create tên release bất biến, gọi /api/show, lưu model ID/hash, chạy smoke JSON/prose. Không dùng tag latest làm duy nhất lineage.

### 4.6.4. Kết nối với backend

Settings trỏ LLM_MODEL và INTAKE_MODEL; DI tạo backend riêng. Health cần thấy cả model. Intake phải test JSON schema, generator phải test system policy, token streaming, fallback và context counters.

### 4.6.5. Trạng thái tích hợp

**Đã có về mặt kỹ thuật nhưng chưa khóa lineage.** Ollama local đang có acne-generator ID d5627fcac6ed và acne-intaker ID 81bf8ebc0d95; container build thành công và RAG ready. Tuy nhiên system prompts đang nạp khác source, backend/frontend không chạy ở snapshot và chưa có chứng cứ active blob được tạo từ checkpoint nào. Không gọi trạng thái này là release verified.

## 4.7. Thiết kế đánh giá hệ thống

### 4.7.1. Các mức đánh giá

1. Contract/unit: schema, preprocessing, rule, prompt, store.
2. Component: intake, retrieval, generator, safety.
3. Integration: prepare_chat_turn, SSE/WS, DB/audit.
4. E2E: frontend → API → Ollama/RAG → UI.
5. Human/clinical: label review, answer/safety assessment.
6. Operational: latency, errors, memory, degraded mode, concurrency.

### 4.7.2. Framework đánh giá

evaluation/full_evaluation.py điều phối preflight → intake → retrieval → ablation, có smoke/limit/skip, retry, output summary, judge-key check và cost confirmation. Eval container tắt fallback, cache production và ghi DB vào temp.

Không dùng thư mục ablation/ đời trước và evaluation/runners/run_ablation.py trong cùng kết luận nếu contract/arms/dataset khác; chọn một harness chuẩn cho thesis và version nó.

### 4.7.3. Dữ liệu đánh giá

Inventory hiện có: eval_set.v3 195 rows và intake_eval.v2 1.500 rows. Đây không phải bằng chứng chất lượng:

- eval_set.v3 hash hiện khác MANIFEST;
- intake_eval.v2 chưa có trong MANIFEST;
- mẫu eval có annotation_status synthetic_pending_review;
- run_intake hiện loại multi-turn khỏi metric single-turn.

Trước run: human-review stratified sample, freeze version mới, kiểm duplicate/semantic overlap với train, tách safety groups, lock expected points/forbidden claims và ghi label source.

### 4.7.4. Chỉ số đánh giá

Metric chính nên báo theo layer:

**Intake**

- schema_valid_rate, parse_fail_rate, failure rate;
- intent accuracy, macro-F1, per-class precision/recall/F1, reject recall, confusion matrix;
- scalar accuracy tổng và accuracy khi field thật sự được khai, lift so với always-empty baseline;
- list-field micro/macro precision/recall/F1 và per-value metrics;
- severity exact accuracy, downgrade rate và confusion;
- enum validity;
- root/field ECE;
- negation leak và canonicalization hit;
- p50/p95 latency, timeout/fallback rate.

**Retrieval**

- no-context rate;
- context relevance 0–5;
- context precision = tỷ lệ chunk grade từ 3;
- context sufficiency 0–5;
- ranking quality theo nDCG của judge grades;
- groundedness 0–5 khi có answer;
- per-source-type usage/grade;
- supplementary gold Recall@k, MRR, nDCG@k khi có qrels đã review.

**Generation/E2E**

- answer_quality và role_tone 1–5;
- incorrect_content và missing_content 0–3, thấp là tốt;
- safety_pass và safety fail reasons;
- refusal_fidelity, over-refusal và missed-refusal;
- pregnancy/drug/self-procedure/referral critical event counts;
- groundedness/citation entailment;
- Vietnamese ratio, vacuous answer, source hallucination;
- TTFT, total latency, tokens/s, error/fallback/no-context rate.

### 4.7.5. Baseline và ablation

Baseline chính RRR = real intake + real RAG + local generator. Default arms trong harness:

| Arm | Ý nghĩa |
|---|---|
| RRR | Pipeline thật |
| RNR | Tắt RAG |
| ROR | Oracle RAG |
| ORR | Oracle intake |
| RRO | Frontier/API generator |
| RNO | Frontier generator không RAG |

Bổ sung raw-input baseline bỏ structured fold/prompt facts để đo semantic bottleneck. Mỗi arm phải giữ những layer còn lại và system prompt cố định; oracle chỉ dùng gold đã review, không dùng synthetic label mơ hồ.

### 4.7.6. LLM judge và phân tích thống kê

Harness chấm mù answer_quality, role_tone, incorrect_content, missing_content, forbidden_violated; context judge chấm relevance/sufficiency/groundedness. Cache key gồm provider/model/prompt.

Quy trình bắt buộc:

- calibrate với phiếu human mù;
- báo Cohen kappa thường, quadratic weighted kappa và Spearman;
- code đánh dấu trục có weighted kappa dưới 0,61 là không đủ tin cậy;
- paired common IDs, mean/median delta, increased/decreased/unchanged;
- bootstrap 95% CI theo cặp;
- safety binary báo count/ID riêng; nên bổ sung McNemar exact;
- nhiều phép so sánh nên pre-register primary faces hoặc hiệu chỉnh Holm.

### 4.7.7. Điều kiện chấp nhận kết quả

Chỉ đưa số vào khóa luận khi đồng thời:

1. dataset freeze/hash hợp lệ và không train overlap;
2. model/prompt/KB/config lineage đầy đủ;
3. completion rate và dropped IDs được giải thích;
4. judge calibration đạt gate cho trục được trích;
5. không có critical safety regression mới ở arm đề xuất;
6. CI paired của primary quality metric không vượt biên suy giảm đã pre-register;
7. kết quả holdout và E2E cùng hướng, không chỉ loss;
8. có manual error review theo intent/risk/source;
9. mọi số đều có numerator/denominator và uncertainty.

## 4.8. Đánh giá thành phần intake

### 4.8.1. Mục tiêu và quy trình đánh giá

Freeze intake eval single-turn; chạy acne-intaker với temperature 0 và exact model/prompt hash; validate raw JSON trước tolerant parser; chấm intent/fields/confidence/latency. Chạy riêng multi-turn qua production UnifiedIntake cache/history contract vì runner hiện loại multi-turn.

So ít nhất: active intaker, checked-in rebuilt intaker, semantic router, rule fallback và raw model không _intent_patch. Việc này tách model quality khỏi fallback/patch quality.

### 4.8.2. Chỉ số đánh giá

Dùng toàn bộ nhóm intake ở 4.7.4, ưu tiên macro-F1 intent, reject recall, schema/parse failure, field accuracy khi có khai, list micro-F1, severity downgrade, negation leak, ECE và p95 latency. Safety fields pregnancy/medications/allergies phải có recall riêng vì cost false-negative cao.

### 4.8.3. Trạng thái dữ liệu đánh giá

**Chưa sẵn sàng để kết luận.** intake_eval.v2 tồn tại nhưng chưa được MANIFEST freeze, nguồn chủ yếu synthetic và runner single-turn bỏ multi-turn. Cần human-review sample theo case, khóa hash/version và tách các rows có system prompt cũ khỏi prompt hiện hành.

### 4.8.4. Nguyên tắc diễn giải

- Accuracy cao có thể do đa số field rỗng; luôn báo accuracy khi có khai và always-empty lift.
- Macro-F1 quan trọng hơn accuracy nếu intent lệch lớp.
- Confidence chỉ hữu ích khi calibrated; ECE và reliability bins bắt buộc.
- Tolerant parser có thể làm schema đẹp sau khi bỏ field sai; báo raw schema và parsed metric riêng.
- Semantic/rule fallback làm runtime tốt hơn model-only nhưng phải ghi fallback rate.

## 4.9. Đánh giá retrieval

### 4.9.1. Mục tiêu và phương pháp

Chạy production retrieve_for_chat với eval cache tắt; loại reject/clarify khỏi retrieval quality; judge chunks không sinh answer để đo relevance/sufficiency; sau đó E2E arm đo groundedness. Có thêm qrels human subset để kiểm judge và gold Recall@k/nDCG@k.

### 4.9.2. Cấu hình thực nghiệm hiện có

Source hiệu lực: retrieve top 25, final top 5, guideline/safety pass 5, dense max distance 0,60, reranker min 0,30, final floor 0,50, max 1 chunk/source, RRF k=60, context 6.000 ký tự. Embedder/reranker và KB fingerprint phải được ghi cho từng run.

### 4.9.3. Kết quả retrieval bước đầu

**Chưa có số liệu được chấp nhận.** Khi chạy, bảng phải có n, no_context, judge failures, relevance/precision/sufficiency/ranking, CI, latency và per-intent/risk. Không chép results.json cũ do dataset/model lineage chưa khóa.

### 4.9.4. Phân bố nguồn

Tách hai loại bảng:

- inventory corpus theo source_type/trust/language;
- source thực sự được retrieve/final prompt, cùng grade và tỷ lệ dùng được.

Không dùng inventory Chroma để kết luận RAG ưu tiên nguồn tốt; phải đo exposure sau tất cả filter/rerank/guideline slot.

### 4.9.5. Giới hạn của kết quả

LLM judge có bias; nhiều chunk diễn đạt cùng fact làm gold ID recall thiếu công bằng; synthetic question có thể gần KB; source metadata có thể sai; sufficiency không bảo đảm answer dùng đúng context; không-context có thể là hành vi đúng cho câu không cần nguồn.

## 4.10. Kiểm thử chức năng và an toàn

### 4.10.1. Mục tiêu kiểm thử

Xác nhận contract code không vỡ và các ca high-risk có expected behavior, tách khỏi thí nghiệm chất lượng trung bình.

### 4.10.2. Kiểm thử chức năng

Các nhóm test source đã có: API/SSE, unified intake/fallback, preprocessing/negation/confidence, prompt builder, session/SQLite, Chroma/BM25/retriever/reranker, KB quality/dedup, Ollama backend, settings/schema/audit.

Nên thêm E2E browser cho send/stream/source/feedback/clear/settings; Docker smoke; cancellation; concurrent session isolation; corrupted BM25/Chroma mismatch; GET query privacy.

### 4.10.3. Kiểm thử safety layer

Matrix tối thiểu:

- pregnancy/breastfeeding × oral/topical retinoid/cycline;
- isotretinoin+tetracycline interaction;
- age under 8/12;
- allergy/current medication;
- severe/infection/pain/widespread/scarring;
- self-popping/needle/peel;
- genital-only/mixed scope;
- jailbreak/system extraction;
- crisis/multi-condition;
- benign negation như “không dùng isotretinoin” để đo false positive;
- unsafe prose model sinh ra trước suffix.

### 4.10.4. Kết quả kiểm thử tự động

**Không điền pass count của release candidate vào Chương 4 trong bản này.** Snapshot kỹ thuật phía đầu tài liệu đã ghi rõ full suite hiện không qua collection vì hai test mồ côi; đây là defect baseline, không phải kết quả thực nghiệm. Khi chạy release candidate, lưu command, environment, commit+dirty hash, pass/fail/xfailed, duration và failure log. Unit-test green không thay thế clinical/E2E evaluation.

### 4.10.5. Giới hạn của kiểm thử

Mock model có thể che lỗi prompt/Ollama; regex test không đo paraphrase; snapshot test không đo medical correctness; active model drift có thể làm source test green nhưng live behavior khác; không có adversarial clinician review hoặc load test đầy đủ.

## 4.11. Thực nghiệm loại bỏ thành phần

Thực hiện default six-arm matrix trên common IDs. Báo từng face, không gộp score:

- ORR−RRR: ceiling nếu intake hoàn hảo;
- ROR−RRR: ceiling nếu retrieval hoàn hảo;
- RRO−RRR: ceiling nếu generator mạnh;
- RRR−RNR: đóng góp của RAG thật;
- RRO−RNO: RAG còn giúp generator mạnh không.

Thêm các ablation quan trọng với repo hiện tại:

1. raw current message vs unified intake/fold;
2. _intent_patch on/off;
3. loaded intaker prompt vs rebuilt source prompt;
4. session fold on/off;
5. guideline/safety pass on/off;
6. reranker/filter on/off;
7. safety suffix on/off nhưng chỉ trong sandbox eval;
8. active fine-tune vs base Qwen cùng SYSTEM.

Mỗi paired delta cần bootstrap 95% CI, paired_n, dropped IDs/reasons và safety event IDs riêng. Hai mặt incorrect_content/missing_content có dấu ngược: delta dương là tệ hơn.

## 4.12. Thảo luận kết quả và giới hạn thực nghiệm

Chưa viết kết luận số. Sau khi chạy, thảo luận theo causal chain:

- gain nằm ở layer nào;
- gain có đổi theo intent/risk/multi-turn không;
- có trade-off latency/safety/coverage không;
- lỗi do label, prompt/model drift, retrieval hay generator;
- kết quả có vượt uncertainty/judge disagreement không;
- external validity với user thật và môi trường deploy đến đâu.

Nếu annotation hoặc judge gate chưa đạt, dùng từ “bằng chứng định hướng”, không dùng “chứng minh”.

# CHƯƠNG 5: KẾT LUẬN VÀ HƯỚNG PHÁT TRIỂN

## 5.1. Kết luận

Source hiện tạo được một hệ thống AcneLLM tương đối đầy đủ về mặt engineering: unified intake, session memory, conditional hybrid RAG, prompt templates, local Ollama generation, multi-layer safety, SSE/WebSocket API, frontend và evaluation harness.

Tuy nhiên kết luận trung thực ở snapshot này là: **pipeline chưa đủ bằng chứng để tuyên bố production-ready hoặc an toàn lâm sàng.** Nguyên nhân chính là active prompt/model drift, output safety không hard-filter prose streaming, auth/CORS dev, deployment config chưa đồng bộ và Chương 4 chưa có run lineage hợp lệ.

## 5.2. Hạn chế của đề tài

1. Text-only; vision chỉ là mock không nối runtime.
2. Dữ liệu train/eval phần lớn synthetic, chưa clinician-reviewed đầy đủ.
3. Active model tag không truy được chắc về checkpoint/dataset.
4. Completeness và clarification phụ thuộc generator hơn rule deterministic.
5. Route flags không còn guidance block trong prompt.
6. Structured post-check không bảo vệ live SSE.
7. KB source/type/quality là heuristic; citation chưa có entailment gate.
8. Session/audit privacy và API authorization còn yếu.
9. Single-node metrics/rate/cache không hỗ trợ distributed deployment.
10. Docker/launcher drift so với local baseline.
11. Không có số liệu E2E, safety, latency hoặc human agreement được chấp nhận trong tài liệu này.

## 5.3. Hướng phát triển trong tương lai

Thứ tự ưu tiên theo rủi ro:

**P0 – khóa baseline**

- Tạo release manifest cho source diff, dataset, prompt, model blobs, config và KB.
- Rebuild acne-intaker/acne-generator từ prompt source, xác minh /api/show hash.
- Freeze dataset version mới; human-review stratified safety/intake/eval labels.

**P0 – harden safety/security**

- Buffer output hoặc sentence-level safety/rewrite trước emit.
- Nối post-check prose/classifier đã kiểm chứng vào live path.
- Review/version YAML thuốc với chuyên gia.
- Đặt API key, CORS cụ thể, TLS, admin auth, retention và PII policy.

**P1 – chạy đánh giá**

- Intake single/multi-turn, raw-vs-pipeline semantic baseline.
- Retrieval dual judge+gold qrels.
- Six-arm paired ablation, judge calibration, safety counts và bootstrap CI.
- E2E browser/Docker/load/degraded-mode tests.

**P1 – đồng bộ deploy**

- Compose tạo đủ intake/generator đúng tag bất biến.
- Tách launcher local và remote; bỏ endpoint hard-coded.
- Health gate kiểm model/prompt/KB lineage, không chỉ HTTP 200.

**P2 – cải thiện sản phẩm**

- Server-backed conversation history/delete/retention controls.
- Stream cancellation/retry, accessibility audit và UI giải thích evidence score đúng nghĩa.
- Observability theo stage, TTFT, fallback và safety event.
- Chỉ tích hợp vision sau khi có model thật, consent/privacy và clinical validation riêng.

# TÀI LIỆU THAM KHẢO

Không tạo citation học thuật giả từ tên xuất hiện trong code. Khi hoàn thiện khóa luận, cần tra và trích bản gốc, ít nhất theo các nhóm:

1. Transformer và decoder-only language models.
2. LoRA, QLoRA và PEFT.
3. Qwen2.5 model card/technical report đúng revision.
4. Ollama API/version dùng trong thực nghiệm.
5. BM25, dense retrieval, RRF, cross-encoder reranking và RAG evaluation.
6. AAD acne guideline và NICE NG198 đúng phiên bản.
7. Safety/evaluation cho healthcare LLM, human agreement và reporting guideline.
8. Các nguồn guideline/PubMed thực sự có trong release KB manifest.

Mỗi entry phải có tác giả/tổ chức, năm, tiêu đề, venue/URL/DOI và ngày truy cập nếu cần. Tên nguồn trong prompt/YAML không đủ làm trích dẫn.

# PHỤ LỤC A: MA TRẬN SOURCE-OF-TRUTH

| Nội dung | Source chính cần đối chiếu |
|---|---|
| Settings hiệu lực | src/acne_llm/config.py và dump Settings redacted |
| Dependency/runtime branch | src/acne_llm/di.py |
| Shared chat preparation | src/acne_llm/chat/orchestrator.py |
| Streaming/persist/audit | src/acne_llm/chat/runtime.py |
| Intake flow | src/acne_llm/chat/intake.py |
| Unified model contract | src/acne_llm/chat/unified_intake.py, chat/_intake_parse.py |
| Router fallbacks/flags | chat/fallback/semantic_router.py, intent_router.py, _intent_patch.py |
| Preprocess/query | chat/preprocess.py, utils/retrieval_query.py |
| Session fold/store | chat/session.py, db/session_store.py |
| Prompt | llm/prompt_builder.py, config/prompts/*.j2 |
| Active model policy | Ollama /api/show; desired source ở model/Modelfile và system_prompt.canonical.txt |
| Safety | guardrails/runner.py, drug_checker.py, chat/_safety.py, config/*.yaml |
| Retrieval | chat/_retrieval.py, rag/retriever.py, reranker.py, sparse.py, vectorstore.py |
| KB build | scripts/build_kb.py, rag/chunker.py, crawler/*, guideline_docs/*.py |
| API/middleware | api/app.py, api/observability.py, api/routes/*.py |
| Frontend | frontend/src/components, hooks/useSSE.ts, stores/chatStore.ts |
| Datagen | datagen/roledata/*, datagen/intakedata/*, LLMData/chunk_qa/* |
| QLoRA/package | model/finetune_role_qwen25_q4.ipynb, adapter_config.json, Modelfile |
| Evaluation | evaluation/full_evaluation.py, runners/*, metrics/*, judges/*, datasets/registry.py |
| Deployment | scripts/RUN.ps1, scripts/run_all.sh, Dockerfile, frontend/Dockerfile, docker-compose.yml |

# PHỤ LỤC B: NHỮNG TUYÊN BỐ CHƯA ĐƯỢC PHÉP DÙNG

- “AcneLLM đã được chứng minh chính xác/an toàn.”
- “Fine-tuning cải thiện chất lượng X%.”
- “RAG làm tăng groundedness.”
- “Hệ thống luôn chặn thuốc nguy hiểm.”
- “Docker deployment đã sẵn sàng.”
- “Model active đúng checkpoint tốt nhất.”
- “Evidence strong nghĩa là câu trả lời đúng 90%.”
- “Dataset eval là gold/human-labeled.”
- “Nút Xóa xóa dữ liệu server.”
- “Post-check structured đang bảo vệ SSE.”

Chỉ bỏ một tuyên bố khỏi danh sách này sau khi có artifact, lineage, metric và acceptance gate tương ứng.
