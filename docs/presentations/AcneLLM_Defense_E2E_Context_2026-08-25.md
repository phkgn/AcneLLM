---
title: AcneLLM Defense E2E Context and Slide Structure
status: proposed-current
as_of: 2026-08-25
source_head: 487a7f614e628b804e693992060465fe54275e37
audit_run: 20260825T090826Z
talk_duration: 20 minutes
---

# AcneLLM — context bảo vệ và cấu trúc slide E2E

## Current delivery — 16-slide compact defense deck

Theo cấu trúc 16 slide được người dùng chốt ngày 25/08/2026, bản compact hiện
tại là `AcneLLM_Defense_16slides_E2E_20260825.pptx`; context từng slide nằm ở
`AcneLLM_Defense_16slides_CONTEXT.md`. Deck có 16/16 speaker notes với
`[Sources]`, đã render lại từ file PPTX trên đĩa và vượt `slides_test.py` mà
không có overflow. Phần 22 slide bên dưới được giữ như phương án mở rộng và
nguồn thiết kế chi tiết, không phải cấu trúc bàn giao compact hiện tại.

## Phán quyết tổng thể

Đề tài đủ cơ sở để bảo vệ như một **prototype nghiên cứu đầu-cuối có đánh giá
hệ thống và truy vết bằng chứng**. Luận điểm mạnh nhất không phải “chatbot tư
vấn đúng y khoa”, mà là: nhóm đã xây được chuỗi dữ liệu -> fine-tune -> runtime
local-first -> RAG -> safety -> SSE -> đánh giá tách tầng; nhờ vậy chỉ ra được
nút thắt kỹ thuật thay vì chỉ trình diễn giao diện.

Mức bằng chứng hiện tại chưa cho phép gọi hệ thống là production-ready, an toàn
lâm sàng, công cụ chẩn đoán hoặc công cụ kê đơn. `v2_full` là bằng chứng module,
retrieval và ablation của protocol ngày 22/8; full behavior/T4/SSE chưa được
chạy lại sau remediation. Human calibration mới có một người chấm không phải
bác sĩ và tất cả bốn trục đều dưới ngưỡng κ_quad 0,61.

## Ba câu phải giữ xuyên suốt bài nói

1. AcneLLM tách đọc hiểu, truy hồi, sinh câu trả lời và an toàn thành các trách
   nhiệm có thể đo riêng.
2. Kết quả cho thấy Intaker định tuyến tốt nhưng trích field chưa đều,
   retrieval thiếu độ phủ và Generator local là nút thắt chất lượng lớn nhất
   quan sát được.
3. Hệ thống truy vết và tái lập được ở mức prototype; bằng chứng chưa đủ cho
   tuyên bố lâm sàng hoặc production.

## Chuỗi E2E cần trình bày

```text
Nguồn tri thức -> làm sạch/chunk -> Chroma + BM25
        |                              |
        +-> dữ liệu Intaker/Generator  |
              -> QLoRA -> GGUF/Ollama |
                                        v
UI Next.js -> FastAPI/SSE -> Unified Intake -> Orchestrator
                                  |              |
                                  |              +-> hybrid RAG -> prompt
                                  +-> semantic/rule fallback
                                                   |
                                                   v
                                    Generator -> output safety
                                        -> SQLite/audit -> SSE client

Đánh giá: A Intaker -> B Retrieval -> C Ablation -> Human judge calibration
Provenance: code truth -> immutable audit -> Current Truth -> Obsidian mirror
```

Đây là backbone của bài bảo vệ. Data pipeline và runtime pipeline gặp nhau ở
hai artifact triển khai `acne-intaker` và `acne-generator-v2`; evaluation đứng
ngoài runtime để đo từng tầng; audit/Obsidian không phải thành phần trả lời mà là
lớp provenance chứng minh claim truy được về source và artifact.

## Cấu trúc đề xuất: 22 slide chính / khoảng 19 phút 20 giây

| # | Thời gian | Câu hỏi hội đồng | Claim chính | Bằng chứng/visual |
|---:|---:|---|---|---|
| 1 | 0:20 | Đề tài là gì? | AcneLLM là prototype local-first cho tư vấn thông tin về mụn, không chẩn đoán/kê đơn. | Tên đề tài + một câu phạm vi. |
| 2 | 0:45 | Vì sao bài toán đáng làm? | Thông tin web nhiễu, thuốc có rủi ro và hội thoại có dữ liệu riêng tư. | Ba rủi ro, không dùng stock image. |
| 3 | 0:50 | Nhóm nghiên cứu câu hỏi gì? | Đo riêng năng lực đọc hiểu, truy hồi và sinh trả lời; kiểm cả độ tin cậy của thước đo. | Ba research questions + một claim boundary. |
| 4 | 0:45 | Đóng góp cụ thể là gì? | Đóng góp là chuỗi E2E có tách trách nhiệm, dữ liệu có gate, safety nhiều tầng và evaluation định vị bottleneck. | Bốn dòng đóng góp gắn artifact. |
| 5 | 0:55 | Toàn bộ hệ thống nối với nhau thế nào? | Hai pipeline dữ liệu và runtime gặp nhau tại hai model GGUF; evaluation và provenance bao quanh. | Sơ đồ E2E toàn dự án, một chiều trái -> phải. |
| 6 | 0:55 | Kiến trúc runtime hiện tại là gì? | FastAPI/SSE -> Intake -> Orchestrator -> RAG/Prompt -> Generator -> Safety -> SQLite. | Architecture diagram theo live source; solid/dashed arrows phân biệt normal/fallback. |
| 7 | 0:55 | Một câu hỏi chạy ra sao? | Một lượt chat có thứ tự kiểm soát rõ và stream token/source/done về UI. | Sequence diagram UI, API, Intake, RAG, Ollama, DB. |
| 8 | 0:50 | Intaker làm gì và lỗi thì sao? | Một Unified Intaker tạo intent+field; semantic rồi rule fallback không gọi LLM thứ hai. | JSON tối giản + fallback dashed path. |
| 9 | 0:50 | RAG thực hiện thế nào? | Dense + BM25 -> RRF -> source passes -> BGE rerank -> tối đa 5 chunk; 0 context là hợp lệ. | Pipeline truy hồi, ghi số 24,393 ở nguồn. |
| 10 | 0:50 | Safety nằm ở đâu? | Safety không chỉ ở prompt: hard input/medication, routing signals, output checks/suffix, persistence audit. | Boundary diagram; phân biệt availability fallback với safety authority. |
| 11 | 0:45 | Tri thức được xây từ đâu? | 6,835 tài liệu -> 6,796 qua ngưỡng -> 24,393 chunk; Chroma và BM25 đồng số lượng. | Funnel + biểu đồ nhóm nguồn; ghi guideline coverage hạn chế nếu dùng. |
| 12 | 0:55 | Dữ liệu Intaker có provenance gì? | 4,000 = 836 Python relabel + 3,164 GPT-4o-mini; 3,600/400 split; relabel không phải LLM call. | Funnel + một before/after schema. |
| 13 | 0:50 | Dữ liệu Generator có đạt target không? | 3,077 accepted, split 2,616/246/215; gate loại dữ liệu kém nhưng target 3,500 chưa hoàn tất. | Funnel có target và actual, không gọi 3,500 là achieved. |
| 14 | 0:55 | Fine-tune và artifact triển khai là gì? | QLoRA cho Qwen2.5 3B/7B; checkpoint chọn theo validation artifact; deploy dùng hai GGUF có hash. | Hai lane model + loss chart + hash ngắn. |
| 15 | 0:55 | Đánh giá được thiết kế ra sao? | A: 1,490 Intaker; B: 120 retrieval; C: 145 x 6 ablation; metric và dataset boundary khác nhau. | Ma trận A/B/C + legend R/O/N. |
| 16 | 0:50 | Intaker tốt ở đâu, yếu ở đâu? | Schema 98.12% và intent 95.70%, nhưng macro-F1 74.05%, extraction 61.31%, inflammation F1 21.26%. | Headline metrics + per-field bar; nêu lệch lớp. |
| 17 | 0:50 | Retrieval có dùng được không? | 29/120 không context; relevance 2.59/5 và sufficiency 2.85/5; ranking 0.94 không chứng minh coverage. | Bar/boxplot + annotation “coverage bottleneck”. |
| 18 | 1:20 | Thành phần nào chi phối câu trả lời? | RRO +0.7248 là hiệu ứng lớn nhất quan sát; ROR +0.4118 cho thấy context tốt có giá trị; RNR gần 0 cho thấy RAG thật chưa phát huy. | Forest plot CI + raw safety counts. |
| 19 | 1:00 | Có tin LLM judge được không? | Một người chấm 145 RRR: cả bốn κ_quad < 0.61; safety precision 0.50/0.42. | Agreement chart + confusion matrices; ghi one-rater/non-clinician. |
| 20 | 0:55 | Vì sao claim của nhóm truy vết được? | Snapshot 837/837 path, 0 hash mismatch; Current Truth tách current/historical/planned; Obsidian là knowledge mirror, không thay code truth. | Provenance ladder code -> audit -> context -> vault -> slide. |
| 21 | 0:55 | Điều gì chưa được chứng minh? | Không base-model control, dữ liệu eval tổng hợp, judge yếu, chưa T4/SSE rerun, chưa bác sĩ/inter-rater. | Ma trận methodological vs engineering limitations. |
| 22 | 0:55 | Kết luận và bước tiếp theo? | Prototype E2E đã định vị generator/retrieval/intake bottleneck; ưu tiên retrieval chunking, paired human arm và T4/SSE gate. | Ba kết luận + roadmap 3 gate, kết bằng claim boundary. |

Tổng thời gian nói dự kiến khoảng 19:20, chừa 40 giây cho chuyển slide hoặc xử
lý gián đoạn. Slide 18, 19 và 22 không được cắt vì lần lượt là kết quả chính,
độ tin cậy của thước đo và kết luận.

## Điều chỉnh so với deck 22 slide hiện tại

Deck hiện tại đã có trục kể chuyện tốt và gần với cấu trúc đề xuất. Thay đổi
quan trọng nhất là làm rõ hai lớp còn thiếu:

- Dùng slide 5 làm **bản đồ E2E toàn dự án**, không chỉ runtime. Kiến trúc runtime
  chuyển sang slide 6 và sequence chat giữ ở slide 7.
- Dành một slide chính cho **provenance/audit/Obsidian**. Đây không phải khoe số
  file; mục tiêu là chứng minh vì sao mỗi claim có thể lần về code/artifact và
  vì sao report cũ không lấn át current source.
- Gộp phần “vì sao chọn Qwen2.5” vào slide fine-tune; lựa chọn model là quyết
  định thiết kế, không nên chiếm một slide riêng nếu phải nhường chỗ cho
  provenance và threats to validity.
- Tách rõ “kết quả” khỏi “hạn chế”. Slide 21 là threats to validity; slide 22
  mới kết luận và roadmap có verification gate.
- UI thật và fallback chi tiết giữ ở appendix. Không dùng screenshot UI làm bằng
  chứng rằng runtime/model đang ready nếu chưa chạy endpoint smoke trong phiên.

## Phụ lục đề xuất

| # | Mở khi được hỏi | Nội dung |
|---:|---|---|
| A1 | Demo/UI | Screenshot thật + event `token/source/done/error`; nói rõ ảnh không thay endpoint smoke. |
| A2 | Intake detail | Confusion matrix intent, per-field F1, schema violation và fallback behavior. |
| A3 | Retrieval detail | Nguồn tài liệu, score distributions, 29 no-context và ví dụ chunk tốt/xấu. |
| A4 | Ablation protocol | Ý nghĩa RRR/RNR/ROR/ORR/RRO/RNO, paired filtering, asymmetric failures. |
| A5 | Human calibration | Kappa, quadratic kappa, Gwet AC1, within-one agreement và safety confusion. |
| A6 | Data provenance | `golden_relabel` before/after, overlap purge 149, Generator rejection semantics. |
| A7 | Training provenance | Notebook vs trainer-state drift; checkpoint 300; GGUF hashes và deploy parity. |
| A8 | Audit/Obsidian | Manifest denominator, skip reasons, snapshot hashes, vault link/orphan/secret gates. |
| A9 | Reproducibility | Commands/artifact paths; phân biệt T3 batch và T4/SSE. |
| A10 | Q&A claim boundary | Bảng “được nói / không được nói” cho clinical, fine-tune, RAG và production. |

## Evidence map bắt buộc cho speaker notes

| Claim family | Primary evidence |
|---|---|
| Current runtime wiring | `src/acne_llm/di.py`, `chat/intake.py`, `chat/orchestrator.py`, `chat/runtime.py`, API routes |
| Deploy/model parity | `src/acne_llm/config.py`, `docker-compose.yml`, `docker/ollama-init.sh`, model Modelfiles |
| Knowledge base counts | `data/raw/documents.jsonl`, `data/raw/chunks.jsonl`, Chroma/BM25 live artifacts |
| Intaker data | `research/datagen/intakedata/output/intake/`, `seed.py`, final summary/records |
| Generator data | `research/datagen/roledatav2/output/`, generation summary and split artifacts |
| Training | notebooks, trainer states/checkpoints, model manifests and GGUF hashes |
| Evaluation | `research/evaluation/reports/v2_full/` and `research/evaluation/eval_context.md` |
| Human calibration | `research/evaluation/reports/calibration_rrr/ket_qua_rrr145.json` |
| Current audit | `.audit/runs/20260825T090826Z/SNAPSHOT_GATE.md` and scope/manifest |
| Claim policy | `.audit/CURRENT_TRUTH.md`, `CONTEXT_INTEGRITY.md`, this file and the 2026-08-25 fact ledger |

Mỗi slide có claim không hiển nhiên nên có `[Sources]` trong speaker notes với
đường dẫn cụ thể. Với số liệu `v2_full`, ghi thêm nhãn `historical protocol
artifact; not rerun after remediation`. Với code truth, ghi HEAD và nếu trích
từ worktree dirty thì ghi cả audit run.

## Hướng phát triển phải gắn verification gate

1. **Retrieval:** sửa chunking tài liệu scan và coverage; gate bằng retrieval
   evaluation + ROR/RRR/RNR liên quan, không chỉ xem screenshot chunk.
2. **Human evidence:** thêm rater thứ hai, bác sĩ da liễu và ít nhất một arm
   paired `RRO`; gate bằng inter-rater agreement và human paired delta.
3. **Runtime parity:** thêm lane T4/SSE trên package deploy; gate bằng stream
   assembly, crisis prefix, safety suffix, persistence và endpoint smoke.
4. **Fine-tuning claim:** thêm base-Qwen control; gate bằng cùng dataset,
   protocol, prompt và judge/human scale.

## Kết luận dùng cho bảo vệ

“AcneLLM đã hoàn thành một chuỗi nghiên cứu đầu-cuối có thể truy vết từ dữ liệu,
mô hình, runtime đến đánh giá. Kết quả cho thấy điểm mạnh là kiến trúc tách tầng
và khả năng định vị lỗi; điểm nghẽn lớn nhất hiện tại là Generator local, tiếp
theo là độ phủ/chất lượng retrieval và các field lâm sàng khó của Intaker. Đây
là bằng chứng cho một prototype nghiên cứu có đánh giá hệ thống, chưa phải bằng
chứng cho độ đúng hay an toàn lâm sàng.”
