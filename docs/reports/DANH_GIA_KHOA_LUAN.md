# AcneLLM — Đánh giá mức hoàn thành khoá luận

Rà soát ngày 2026-08-20. Đối chiếu repo thực tế với yêu cầu một khoá luận tốt
nghiệp có báo cáo và buổi bảo vệ đầy đủ.

---

## Kết luận ngắn

**Phần kỹ thuật đã xong ~95%. Phần khoá luận (báo cáo + slide) mới ~15%.**

Nghịch lý của project này: hệ thống và thực nghiệm đã ở mức vượt chuẩn khoá luận
— có ablation một biến, ba judge độc lập, bootstrap CI, McNemar, kiểm thiên lệch
độ dài. Nhưng **không có một trang nào của báo cáo khoá luận tồn tại trong repo.**
`docs/reports/report.md` (1.038 dòng) là tài liệu kiến trúc kỹ thuật, không phải
Chương 1–5. Không có file `.docx`, `.tex`, `.pptx`, không có danh mục tài liệu
tham khảo.

**Còn khoảng 22 task chặn**, ước tính **10–14 ngày công**. Việc chặn duy nhất
phụ thuộc người khác — người thứ hai chấm 60 câu — nên gửi đi **hôm nay**.

---

## PHẦN 1 — Cái đã có, và đủ mạnh để bảo vệ

| Hạng mục | Trạng thái | Bằng chứng trong repo |
|---|---|---|
| Backend production | Xong | `src/acne_llm/` — 8 package, FastAPI + SSE, DI container |
| Pipeline RAG hybrid | Xong | Chroma + BM25 → RRF → cross-encoder rerank, 24.393 chunk |
| Hai model finetune | Xong | `acne-generator-v2` (LoRA r=16, 2.616 mẫu), `acne-intaker` |
| Guardrails lâm sàng | Xong | `guardrails/runner.py` 499 dòng, đọc field có cấu trúc |
| Frontend | Xong | Next.js + Tailwind, SSE, `frontend/src/` |
| Docker bàn giao | Gần xong | Compose 5 service; còn 1 lỗi anchor (mục B5) |
| Bộ test | Xong | 44 file, 502–507 test, ~7–10 giây, mock hoàn toàn |
| Framework eval | Xong | 4 runner, 4 nhóm metric, 3 judge, judge cache SQLite |
| Kết quả thực nghiệm | Xong | `FINALIZE.md` — 8 bảng số liệu đã đo |
| Hình minh hoạ | Có ~90 PNG | `research/dashboards/` — nhưng **là số vòng 1** (xem C6) |
| Tài liệu kỹ thuật | Xong | `context.md`, `report.md`, `EVAL_BLUEPRINT.md`, 20 file `docs/` |

**Ba điểm mạnh hiếm có ở khoá luận, phải làm nổi bật khi bảo vệ:**

1. **Thiết kế một biến.** v1 và v2 giữ nguyên base, LoRA config, effective batch
   — chỉ đổi dữ liệu huấn luyện. Đây là điều kiện để quy nhân quả cho can thiệp.
2. **Kết quả âm được báo cáo trung thực.** `incorrect_content` tăng ở cả ba judge,
   `safety_fail` 12% → 26% với McNemar p < 0,001. Hội đồng đánh giá cao việc dám
   báo cáo hồi quy hơn là một bảng toàn màu xanh.
3. **Truy được cơ chế.** ρ = +0,351 giữa độ dài và lỗi trong nội bộ v2 giải thích
   *tại sao* ràng buộc độ dài gây hồi quy — không dừng ở "kết quả xấu đi".

---

## PHẦN 2 — 22 task còn chặn

### Nhóm A — Bằng chứng còn thiếu (5 task, ~2 ngày, có 1 việc chờ người khác)

Đây là nhóm duy nhất chặn phần **kết quả** của báo cáo.

| # | Task | Ghi chú | Ước tính |
|---|---|---|---|
| A1 | **Gửi gói 60 câu cho người thứ hai chấm** ⭐ | `reports/calibration/cham_60cau.zip` đã đóng gói sẵn 35 KB. Chờ người khác → **gửi ngay hôm nay** | 15 phút gửi + 2–5 ngày chờ |
| A2 | Bạn tự chấm lại bộ **có** checklist | Lần đầu thiếu `expected_answer_points` nên κ = 0,10 — phép đo không hợp lệ. Mở `calibration/cham.html` | 3–4 giờ |
| A3 | Tính κ trọng số bậc hai | `python -m evaluation.judges.calibrate --import <file>`. Ngưỡng dùng được: κ ≥ 0,61 | 30 phút |
| A4 | Cập nhật `METRIC_EVIDENCE.md` | Thêm bảng ba judge (§4 `FINALIZE.md`) + kết quả κ | 2 giờ |
| A5 | Sửa cách mô tả **n = 114** ở mọi tài liệu | Không phải "114/145 thành công" mà là "114 câu giao nhau giữa hai bộ đề". Sai chỗ này là bị hỏi ngay | 1 giờ |

> **Tại sao A1 quan trọng hơn bạn nghĩ:** ba judge đã bất đồng ở `answer_quality`
> và `role_tone` (Luna đảo dấu). Người chấm mù là trọng tài duy nhất còn lại. Và
> κ người–người trả lời thẳng câu phản biện kinh điển *"em vừa là tác giả vừa là
> người chấm"*.

### Nhóm B — Repo bàn giao được (5 task, ~1 ngày)

| # | Task | Trạng thái | Ước tính |
|---|---|---|---|
| B1 | Đổi tên `eval_set.v3.jsonl` trùng | Hai file cùng tên khác nội dung (145 vs 195 dòng) — chính là gốc của nhầm lẫn ở A5. Đề xuất `eval_set.v3_145.jsonl`, sửa 4 chỗ tham chiếu | 30 phút |
| B2 | Chạy `pytest` xác nhận | 502 test, ~7 giây | 10 phút |
| B3 | **Commit 78 file đang dirty** | 40 sửa · 21 mới · 17 xoá. Tách ≥ 3 commit: công cụ eval / dữ liệu `roledatav2` / dọn dẹp | 1–2 giờ |
| B4 | Dọn ~25 GB + `git lfs prune` | `model/legacy/` 20 GB, zip lạc 5,6 GB, `output.round1/` 62 MB. `.git` đang **65 GB** — không ai clone nổi | 2 giờ |
| B5 | Sửa `docker/ollama-init.sh` | Đang tạo `acne-generator` từ `Modelfile.full` (anchor cũ 3.719 ký tự, không `TEMPLATE`) → **Docker phục vụ model khác với local**. Sửa, hoặc ghi rõ hạn chế trong báo cáo | 1 giờ |

> ✅ **B đã xong 1 việc:** `model/generator/Modelfile` giờ đã trỏ đúng
> `FROM ./acnellm-role-v2.Q4_K_M.gguf`. Task 2.1 cũ trong `TASKS.md` đóng được.

### Nhóm C — Báo cáo khoá luận (8 task, ~7–9 ngày) — **CHƯA CÓ GÌ**

Đây là khối lớn nhất và là thứ thật sự chặn "xem như done".

| # | Task | Nguyên liệu đã có sẵn | Ước tính |
|---|---|---|---|
| C1 | Outline 5 chương + bảng ánh xạ *số liệu nào vào mục nào* | `FINALIZE.md` là kho số liệu duy nhất | 0,5 ngày |
| C2 | **Chương 1 — Mở đầu** (bối cảnh, vấn đề, mục tiêu, phạm vi, đóng góp) | Chưa có gì. Phải viết mới | 1 ngày |
| C3 | **Chương 2 — Cơ sở lý thuyết & công trình liên quan** ⚠️ | **Lỗ hổng lớn nhất.** Repo không có một trích dẫn học thuật nào, không `.bib`, không khảo sát chatbot y tế / RAG / LoRA / LLM-as-judge. Hội đồng sẽ hỏi | 2 ngày |
| C4 | **Chương 3 — Thiết kế hệ thống** | Nhiều nhất: `report.md` 1.038 dòng + `context.md` 657 dòng + 7 hình `architecture/` | 1,5 ngày |
| C5 | **Chương 4 — Thực nghiệm & kết quả** | `FINALIZE.md` gần như dán thẳng vào được. Đây là chương mạnh nhất | 1,5 ngày |
| C6 | **Chương 5 — Kết luận & hướng phát triển** | Phần III `FINALIZE.md` đã viết sẵn phát biểu kết luận. Hướng phát triển lấy từ nhóm 3.x/4.x `TASKS.md` | 0,5 ngày |
| C7 | **Danh mục tài liệu tham khảo** ⚠️ | `research/guideline_docs/` có PDF gốc (AAD, guideline VN) nhưng **chưa lập danh mục**. Cần ≥ 25–30 mục theo APA/IEEE | 1 ngày |
| C8 | **Sinh lại ~90 hình cho số vòng 2** + chọn 15–20 hình đưa vào báo cáo | `dashboards/generate_all.py` đã có. Nhưng PNG hiện tại sinh ngày **07/08**, còn eval vòng 2 chạy **17–19/08** → **hình đang lệch số liệu** | 1 ngày |

> ⚠️ **C3 và C7 là rủi ro thật.** Toàn bộ phần "tại sao chọn RAG hybrid", "tại
> sao LoRA r=16", "LLM-as-judge có đáng tin không" hiện chỉ tồn tại dưới dạng
> quyết định kỹ thuật trong `docs/`, không có neo vào literature. Một khoá luận
> thiếu chương 2 bị trừ điểm nặng bất kể hệ thống chạy tốt đến đâu.

### Nhóm D — Slide & bảo vệ (4 task, ~2 ngày)

| # | Task | Ghi chú | Ước tính |
|---|---|---|---|
| D1 | Slide 15–20 trang | Chưa có `.pptx` nào trong repo | 1 ngày |
| D2 | Kịch bản demo + **video backup** | Model 7B chạy CPU ~34 giây/câu — demo live rất rủi ro. Quay sẵn | 0,5 ngày |
| D3 | Chuẩn bị 10 câu phản biện | Nguyên liệu có sẵn: judge bất đồng, `safety_fail` tăng, tự chấm bài mình, `inflammation_level` lift âm | 0,5 ngày |
| D4 | Chạy thử toàn bộ 1 lượt bấm giờ | | 0,5 ngày |

---

## PHẦN 3 — Không chặn (làm nếu còn thời gian)

Đưa vào chương "Hướng phát triển" là đủ, không cần thực hiện:

- **E1.** Vô hiệu hoá `inflammation_level` — lift **−0,415**, tệ hơn cả việc luôn
  trả `unknown`. Recall của `unknown` chỉ 0,106 (bỏ sót 798/893 dòng).
- **E2.** Thêm **trần** cho gate `len_chars` (`roledatav2/taxonomy.yaml` hiện chỉ
  ép sàn) — đây chính là nguyên nhân hồi quy đã truy ra ở C5.
- **E3.** Lưu bộ hồi quy an toàn 25 ca → `datasets/safety_regression.jsonl`.
- **E4.** Thống nhất định nghĩa `reject` 6 nhóm giữa `datagen` và `evaluation`
  (gốc của vụ 93% vs 40%).
- **E5.** Gom enum về `schemas/enums.py` + test canh trôi cho cả 6 enum.
- **E6.** Finetune lại intaker (lỗi 200 dòng multi-turn đều nhãn `clarify`).
- **E7.** Generator v3 sau khi có E2.

---

## PHẦN 4 — Đường tới hạn

```
HÔM NAY ─── A1 gửi gói đi ──────────────┐
                                        │ (2-5 ngày chờ)
Ngày 1-2 ── A2 tự chấm ──────────────┐  │
                                     ├──┴─> A3 κ ──> A4 ──> C5 Chương 4
Ngày 1    ─ B1..B5 repo ─────────────┘                        │
                                                              ▼
Ngày 2-3  ─ C1 outline + C7 tài liệu tham khảo ───> C2 C3 ──> C4 ──> C6
                                                              │
Ngày 8-9  ─ C8 sinh lại hình ────────────────────────────────>│
                                                              ▼
Ngày 10-12 ─────────────────────────────────> D1..D4 ──> BẢO VỆ
```

**Ba nguyên tắc điều phối:**

1. **A1 gửi đi hôm nay**, không chờ gì cả. Nó là việc duy nhất phụ thuộc người
   khác; mọi việc còn lại bạn tự làm được song song.
2. **Nhóm B làm trong lúc chờ A1** — một buổi là xong, và nó gỡ được rủi ro
   `.git` 65 GB không ai clone nổi lúc nộp.
3. **C3 (cơ sở lý thuyết) bắt đầu sớm nhất có thể.** Nó không phụ thuộc bất kỳ
   số liệu nào và là chương duy nhất phải viết từ con số không.

---

## Tổng kết

| Khối | Số task | Ngày công | Chặn cái gì |
|---|---|---|---|
| A — Bằng chứng | 5 | 2 | Chương 4 |
| B — Repo | 5 | 1 | Bàn giao |
| C — Báo cáo | 8 | 7–9 | **Toàn bộ khoá luận** |
| D — Slide & bảo vệ | 4 | 2 | Buổi bảo vệ |
| **Chặn** | **22** | **10–14** | |
| E — Không chặn | 7 | — | (chỉ nêu trong Chương 5) |

**Đánh giá tổng thể:** phần khó nhất — xây hệ thống và chứng minh nó bằng thực
nghiệm chặt chẽ — đã xong. Phần còn lại chủ yếu là **viết**, và bạn đã có sẵn
`FINALIZE.md` làm kho số liệu, `report.md` + `context.md` làm nội dung Chương 3,
90 hình làm phụ lục. Rủi ro lớn nhất không phải kỹ thuật mà là **Chương 2 và danh
mục tài liệu tham khảo chưa tồn tại** — hãy bắt đầu hai thứ đó ngay trong lúc chờ
người thứ hai chấm bài.
