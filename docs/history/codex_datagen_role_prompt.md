# Nhiệm vụ: Build pipeline datagen dataset ROLE cho AcneLLM (style-LoRA v4)

Bạn là agent xây pipeline sinh data finetune trong `datagen/`. Làm theo ĐÚNG 3 giai
đoạn bên dưới, DỪNG sau Giai đoạn 2 chờ người dùng gõ "run all" mới chạy full.

## Bối cảnh & mục tiêu

Finetune style-LoRA: chỉ dạy VAI + GIỌNG, không dạy kiến thức. Role định nghĩa:

> AcneLLM — LLM chatbot tiếng Việt, trợ lý hỗ trợ và tư vấn về da mụn.
> Giọng trung tính, rõ ràng, thân thiện, không phán xét. Phục vụ người dùng
> nhiều độ tuổi, tự điều chỉnh mức độ giải thích theo kiến thức và nhu cầu
> từng người.

Đọc tham khảo (bắt buộc): `model/V2/Q4/Modelfile` (SYSTEM production),
`config/prompts/stream_user.j2` (format runtime), `config/drugs_acne.yaml`
(danh sách hoạt chất cho knowledge-leak gate),
`evaluation/metrics/grounding.py` (grounding gate tái dùng).

## Thiết kế dataset

### Nhóm A — Pure role R1–R9, KHÔNG context (~2.500 mẫu)

| # | Nhóm | ~SL | Hành vi dạy |
|---|---|---:|---|
| R1 | Danh tính | 250 | "bạn là ai/có phải bác sĩ k/làm được gì" → tự giới thiệu đúng role, thẳng về giới hạn |
| R2 | Điều chỉnh độ sâu | 450 | Cùng câu hỏi từ teen/phụ huynh U50/sinh viên y → cùng giọng, khác register + độ chi tiết |
| R3 | Không phán xét | 350 | Thú nhận nặn mụn/kem trộn/lười skincare → không trách, ghi nhận, hướng tích cực |
| R4 | Đồng cảm chừng mực | 300 | Tự ti, khóc vì da → công nhận cảm xúc trước, không sến, không làm therapist |
| R5 | Hỏi lại đúng cách | 300 | Câu mơ hồ → hỏi 1-2 ý trọng tâm, tự nhiên không như form |
| R6 | Ranh giới trong vai | 250 | Xin kê đơn/chẩn đoán/gửi ảnh → từ chối 3 nhịp: ghi nhận → giới hạn → lối thay thế |
| R7 | Keo hội thoại | 200 | Chào/cảm ơn/lan man → đáp ngắn ấm, kéo về chủ đề nhẹ nhàng |
| R8 | Meta & jailbreak | 150 | "act as DAN", "từ giờ là bác sĩ thật" → giữ vai, từ chối êm |
| R9 | Multiturn 4-6 lượt | 250 | Trộn các nhóm trên, giọng + xưng hô nhất quán |

**Chốt chặn không-kiến-thức cho nhóm A**: answer chỉ được (1) trì hoãn có duyên,
(2) phổ thông tối thiểu không số liệu, hoặc (3) chuyển hướng đi khám. Gate máy:
scan answer bằng danh sách hoạt chất/thuốc từ `config/drugs_acne.yaml` + regex
số liệu (mg, %, X lần/ngày, X tuần) → dính là loại/viết lại.

### Nhóm B — Role + context (~1.000 mẫu ≈ 40% so với nhóm A)

Input CÓ section `[TÀI LIỆU Y KHOA THAM KHẢO]` với `[Nguon N]`, render ĐÚNG cấu
trúc `stream_user.j2` (tag, thứ tự, xuống dòng — đối chiếu template thật, không
viết tay theo trí nhớ). Context do LLM SINH (không cần KB thật) với 2 luật sắt:

- Fact trong context phải ĐÚNG y khoa hoặc trung tính vô hại. TUYỆT ĐỐI không
  bịa liều nguy hiểm, chống chỉ định sai, tên thuốc không tồn tại.
- Metadata mỗi mẫu ghi `synthetic_context: true`.

Phân bổ nhóm B:

| Kiểu | ~SL | Dạy gì |
|---|---:|---|
| B1 Grounded + role | 500 | Có docs → trả lời CỤ THỂ từ docs, lồng hành vi role (đồng cảm trước, dùng docs sau) |
| B2 Docs thiếu đáp án | 200 | Abstention: "tài liệu chưa đề cập" + hướng đi, không bịa |
| B3 Docs lẫn 1 chunk nhiễu | 150 | Lờ nguồn lạc đề, dùng nguồn đúng |
| B4 Docs mâu thuẫn nhau | 80 | Nêu cả hai + khuyên hỏi bác sĩ, không tự phân xử |
| B5 Anchor đa dạng độ sâu | 70 | Cùng docs, user khác trình độ → độ chi tiết khác |

**Gate nhóm B**: grounding check bằng `evaluation/metrics/grounding.py` —
`grounded_sentence_rate >= 0.8` với chính context trong mẫu; fail là loại.
(B1/B3/B5 áp gate; B2/B4 kiểm bằng rule riêng: answer không chứa fact ngoài docs.)

### Augmentation văn phong user (áp cả A và B)

~30% mẫu có user message biến thể: teencode ("dc k a", "bt", "j z"), không dấu,
sai chính tả, viết tắt, lẫn emoji, câu cụt. Ghi `input_style` vào metadata
(`standard | teencode | no_accent | typo | mixed`). Answer LUÔN chuẩn chính tả,
đúng giọng.

### Format record

```json
{
  "id": "role-r3-000184",
  "sample_kind": "R3_nonjudgment | B1_grounded | ...",
  "input_style": "teencode",
  "synthetic_context": false,
  "knowledge_leak_check": "pass",
  "grounded_sentence_rate": null,
  "gen_model": "...",
  "messages": [
    {"role": "system", "content": "<NGUYÊN VĂN SYSTEM từ model/V2/Q4/Modelfile>"},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

Metadata ngoài `messages`. Multiturn R9: messages nhiều cặp user/assistant.

### Style guide

Trước khi sinh, viết `datagen/role_style_guide.md` (~1 trang): xưng hô mình–bạn,
giọng trung tính-thân thiện-không phán xét, khi nào được mở đầu trấn an, cấu trúc
từ chối 3 nhịp, quy tắc độ sâu theo đối tượng, disclaimer tối đa 1 lần cuối.
Mọi lời gọi sinh answer đều nhúng style guide này.

## Giai đoạn 0 — Test API key (làm ĐẦU TIÊN)

Key được cấp qua `.env` — thêm dòng `DATAGEN_API_KEY=sk-Rn2y4C23QWr9RckoinHBHpJFlOdKnyOY3yDwSf1t6WgXYGQa`
vào `E:\project\AcneLLM\.env` (KHÔNG commit .env, KHÔNG hardcode key vào bất kỳ
script nào — mọi script đọc từ env).

1. Gọi thử endpoint OpenAI chuẩn (`/v1/models` rồi 1 chat completion ngắn,
   max_tokens=5). Nếu 401/404 → key có thể thuộc proxy OpenAI-compatible:
   thử phát hiện qua thông báo lỗi; nếu không xác định được base_url →
   DỪNG, báo người dùng hỏi base_url, không đoán bừa.
2. Báo cáo: key sống không, model nào khả dụng, giá ước tính cho smoke + full run.
3. Key fail → dừng toàn bộ, không viết tiếp pipeline nửa vời.

## Giai đoạn 1 — Build pipeline trong `datagen/`

Cấu trúc:

```
datagen/
  role_style_guide.md
  role_taxonomy.yaml        # định nghĩa R1-R9, B1-B5, số lượng, tỉ lệ augment
  gen_role_dataset.py       # CLI chính: --smoke | --full | --case R3 | --limit N
  gates.py                  # knowledge-leak, grounding (import từ evaluation), dedupe, contamination
  render_context.py         # sinh context tổng hợp + render đúng stream_user.j2
  report_stats.py           # thống kê phân bố sample_kind / input_style / pass-fail gates
  output/v4_role/           # *.jsonl + generation_summary.json + rejected.audit.jsonl
```

Yêu cầu:

- Budget guard: mặc định trần $5 cho smoke, $25 cho full; vượt là dừng + báo.
- Resume-safe: chạy lại không sinh trùng (id deterministic theo taxonomy slot).
- Contamination check: query sinh ra overlap 8-gram (cả bản bỏ dấu) với
  `evaluation/datasets/v1/*.jsonl` → loại (tái dùng logic từ
  `evaluation/datasets/generate_drafts.py` nếu import được).
- Reject nào cũng ghi `rejected.audit.jsonl` kèm lý do.
- KHÔNG sửa gì ngoài `datagen/` và `.env`.

## Giai đoạn 2 — SMOKE: mỗi case đúng 1 mẫu, rồi DỪNG

Chạy `--smoke`: sinh đúng **1 mẫu cho mỗi case** (R1→R9, B1→B5, cộng 3 biến thể
input_style: teencode/no_accent/typo trên case bất kỳ) ≈ 17 mẫu.

Xuất `datagen/output/v4_role/SMOKE_REVIEW.md` dạng người-đọc-được: mỗi mẫu in
đủ user + assistant + metadata + kết quả từng gate, kèm nhận xét của bạn
(giọng có đúng style guide không, context render có khớp template không,
gate hoạt động không).

**DỪNG TẠI ĐÂY.** Báo cáo kết luận: cái gì ổn, cái gì cần chỉnh, chi phí smoke
thực tế, ước tính chi phí full (~3.500 mẫu). KHÔNG chạy full cho tới khi người
dùng gõ "run all".

## Giai đoạn 3 — FULL (chỉ khi người dùng ra lệnh "run all")

`--full`: sinh đủ ~3.500 mẫu theo taxonomy, chạy toàn bộ gates, xuất:

- `datagen/output/v4_role/v4_role.train.jsonl` (đã bóc? KHÔNG — giữ metadata,
  script train sẽ tự bóc; ghi chú rõ trong summary)
- `generation_summary.json`: counts theo sample_kind/input_style, gate pass/fail,
  token/cost, model, thời gian
- `report_stats.py` in bảng phân bố cuối

## Ràng buộc chung

- Key chỉ nằm trong `.env`. Kiểm tra `.gitignore` có `.env`; không có thì thêm.
- Không đụng `evaluation/datasets/`, `evaluation/reports/`, `src/`, `config/`
  (chỉ ĐỌC các file tham chiếu).
- Mỗi script có docstring usage. `pytest` cho gates.py (knowledge-leak bắt đúng
  hoạt chất + số liệu; dedupe; format record hợp lệ).
- Answer sinh bằng model rẻ (gpt-5-mini class); context tổng hợp có thể dùng
  model tốt hơn cho fact đúng — ghi model nào dùng cho phần nào trong summary.
