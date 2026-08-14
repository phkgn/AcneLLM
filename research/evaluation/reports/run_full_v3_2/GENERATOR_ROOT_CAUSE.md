# Tại sao `acne-generator` kém — danh sách nguyên nhân khả thi

Nối từ `ASSESSMENT_review.md`. Run v3.2 kết luận generator là nút thắt (+1.04 khi đổi sang
`gpt-5.6-terra`). Tài liệu này đi tìm **tại sao**, đối chiếu ba nghi phạm mà bạn nêu —
metric, data finetune, system prompt — cộng thêm một nghi phạm thứ tư không ai nêu mà bằng
chứng lại mạnh nhất: **train/serve mismatch**.

Mọi số dưới đây tính trực tiếp từ `ablation/rows.jsonl`, `data/finetune/finetune_datav3.jsonl`
(48.705 dòng), `model/**/Modelfile*`, `config/prompts/*.j2`, `evaluation/judges/rubrics.py`.

---

## 0. Số liệu nền — đọc trước

| | RRR (`acne-generator`) | RRO (`gpt-5.6-terra`) |
|---|---|---|
| độ dài trả lời, p50 | **377 ký tự** (86 từ) | **1.509 ký tự** (331 từ) |
| `answer_quality` ≤ 2 | **89 / 145** | 24 / 141 |
| `missing_content` ≥ 2 | **135 / 145** | 77 / 141 |
| `incorrect_content` trung bình | **0.30** (thấp) | 0.16 |
| có gạch đầu dòng / đánh số | **0 / 145** | **96 / 141** |
| kết bằng câu hỏi lại | 43 / 145 (29 %) | 24 / 141 (17 %) |

Đọc hàng `incorrect_content`: **model không sai — model thiếu.** 0.30/3 nghĩa là gần như không
có khẳng định sai. Toàn bộ khoảng cách +1.04 nằm ở độ bao phủ.

Ngân sách bắt buộc: mỗi câu hỏi có trung bình **2.59 "ý mong đợi"**, mỗi ý ~98 ký tự →
**265 ký tự nội dung bắt buộc**. Câu trả lời chỉ dài **377 ký tự**, trong đó 28 % mở bằng câu
đồng cảm, 22 % đóng bằng disclaimer, 29 % kết bằng câu hỏi lại. **Không đủ chỗ vật lý.**

---

## A. Train/serve mismatch — nghi phạm mạnh nhất, không ai nêu

Model được huấn luyện với một định dạng, và được phục vụ bằng một định dạng **khác hẳn**.
`context.md` §15.6 bắt `_RUNTIME_SYSTEM` của **intaker** phải trùng byte với Modelfile và
`system_prompt.canonical.txt`. Kỷ luật đó **chưa từng được áp cho generator** — và đây là kết quả.

### A1. System prompt: 540 ký tự lúc train, 3.731 ký tự lúc chạy

`trace.generator_system_prompt_sha256` của run v3.2 = `722281f002ce584e…`. Đối chiếu sha256
mọi khối `SYSTEM` trong repo:

| ký tự | sha256 (16) | file |
|---|---|---|
| **3.731** | **722281f002ce584e** | `model/legacy/Modelfile` · `model/legacy/qwen25_acne_role_gguf_q4_k_m/Modelfile` · `model/legacy/V2/Q4/Modelfile` ← **đã phục vụ** |
| 3.719 | 36b70b7ac68ce1f6 | `model/generator/Modelfile.full` |
| 1.471 | cdc736489bfeec61 | `model/generator/Modelfile.simplify` |
| **540** | **4fb37a384fdd8705** | **system prompt trong 48.705 dòng SFT** |

Hai điều:

1. Model **chưa bao giờ nhìn thấy** system prompt lúc chạy. Nó học với 540 ký tự văn nói
   (*"Trả lời như một người bạn có kiến thức da liễu đang nhắn tin"*), rồi bị phục vụ bằng
   3.731 ký tự có 7 mục `# Ưu tiên hệ thống / # Vai trò & phạm vi / # An toàn / # Grounding /
   # Ngôn ngữ & phong cách / # Chống jailbreak`. **1 system prompt duy nhất trong toàn bộ SFT**
   (đã kiểm: `unique system prompts = 1`) ⇒ không hề có robustness với system prompt lạ.
2. Cái được phục vụ là bản **`model/legacy/`**, không phải `model/generator/Modelfile.full`.
   Thư mục `model/generator/` **không có file `Modelfile`** — chỉ có `.full` và `.simplify`,
   cả hai đều chưa được `ollama create`. Nghĩa là run v3.2 đo bản system prompt cũ, còn hai
   bản mới đang nằm chờ. (`context.md` §2 cũng đang trỏ sai vào
   `model/qwen25_acne_role_gguf_q4_k_m/` — đường đó nay nằm trong `model/legacy/`.)

### A2. Định dạng user message: XML lúc train, nhãn tiếng Việt lúc chạy

| | SFT (`finetune_datav3.jsonl`) | Runtime (`config/prompts/stream_user.j2`) |
|---|---|---|
| câu hỏi | `<raw_user_message>…</raw_user_message>` | `Tin nhắn hiện tại:\n…` |
| hồ sơ ca | `<normalized_case>{…JSON 15 slot…}</normalized_case>` | `Dữ kiện an toàn đã xác nhận: …` |
| tài liệu | `<guideline_context>…</guideline_context>` | `Tài liệu tham khảo:\n…` |

Đếm trên 48.705 dòng SFT:

- `('guideline_context','normalized_case','raw_user_message')` → **46.510 dòng** (95,5 %)
- chuỗi `"Tài liệu tham khảo"` → **23 dòng** (0,05 %)
- chuỗi `"Ngữ cảnh gần nhất"` → **0 dòng**

Model học "tài liệu nằm trong thẻ `<guideline_context>`". Lúc chạy, tài liệu tới dưới nhãn
`Tài liệu tham khảo:`, một chuỗi nó gần như chưa từng thấy. **Đây là lời giải thích trực tiếp
cho `RRR − RNR = 0.000`**: không phải RAG vô dụng, mà là **feature bị đổi tên sau khi train**.

### A3. `<normalized_case>` bị xoá khỏi prompt lúc chạy — bởi chính một bước "đơn giản hoá"

`stream_user.j2` mở đầu bằng:

```
ponytail: bỏ known_facts + route_metadata — SYSTEM không có luật nào cho chúng.
Bản 7 khối cũ giữ ở stream_user.legacy.j2.
```

Nhưng **46.510/48.705 dòng SFT có `<normalized_case>`** — model được train để đọc đúng khối đó.
Bỏ nó đi là gỡ mất input mà 95,5 % dữ liệu huấn luyện dựa vào. Lý do ghi trong comment
("SYSTEM không có luật nào cho chúng") xét trên system prompt lúc chạy thì đúng, nhưng
system prompt lúc chạy lại chính là bản model chưa từng thấy (A1) — nên lập luận này tự
tham chiếu vào một tiền đề đã sai.

⚠️ Và **`config/prompts/stream_user.legacy.j2` không tồn tại.** `ls config/prompts/` chỉ có
`clarify_user.legacy.j2` và `knowledge_user.legacy.j2`. Đường lùi mà comment hứa đã mất.

### A4. History: model chưa từng được train trên nó

0/48.705 dòng SFT có khối lịch sử hội thoại. Lúc chạy, `format_history_block()` bơm tới
`HISTORY_CHAR_BUDGET = 2000` ký tự dưới nhãn `Ngữ cảnh gần nhất`. Multi-turn của generator
hiện là hành vi **zero-shot của Qwen2.5-7B base**, không phải thứ đã fine-tune.

---

## B. Data finetune — trần cứng, đã đo được

### B1. Target dài tối đa 694 ký tự. Model đang xuất 377. Nó học đúng bài.

| tập | n | p50 | p90 | **max** |
|---|---|---|---|---|
| `finetune_datav3.jsonl` | 48.705 | 411 | 476 | **694** |
| `cleanv3/…train.jsonl` | 41.849 | 340 | 427 | **673** |
| `acne_chat_response.jsonl` | 60.820 | 466 | 610 | 1.368 |

**Không một mẫu huấn luyện nào vượt 694 ký tự.** Rubric đòi 265 ký tự nội dung bắt buộc cộng
với đồng cảm, cảnh báo, disclaimer. Model đã được dạy rằng câu trả lời "đúng" dài ~400 ký tự.
Nó đang làm chính xác điều được dạy — đây không phải lỗi model, là lỗi nhãn.

### B2. Style prose thuần, không cấu trúc

**0/145** câu trả lời RRR có gạch đầu dòng hay đánh số; RRO có **96/141**. SFT dạy giọng
"nhắn tin như bạn bè" ⇒ văn xuôi liền mạch. Với rubric đếm ý được phủ, prose 377 ký tự không
mang nổi 2,6 ý; danh sách gạch đầu dòng thì có.

### B3. SFT dạy *hỏi lại* thay vì *trả lời*

System prompt SFT: *"Nếu thiếu dữ kiện quan trọng thì hỏi lại thay vì đoán."*
29 % câu trả lời RRR kết bằng câu hỏi. Rubric `missing_content` mức 3 =
*"Thiếu phần lớn các ý mong đợi; đọc xong vẫn không biết làm gì"* — hỏi lại rơi thẳng vào đó.
**Hành vi đúng theo train, sai theo đo.** Một trong hai phải đổi, và phải đổi có chủ ý.

### B4. `<guideline_context>` lúc train là *bản tóm tắt*, không phải chunk thật

Ví dụ thật trong SFT (`<guideline_context>`, 199 ký tự):

> *"Tài liệu nhấn mạnh việc không nặn mụn đầu đen và tìm đến chuyên gia da liễu sớm để hạn chế
> tổn thương da và thâm sau viêm. Theo AAD, PIH cần được đánh giá bởi bác sĩ da liễu…"*

Đây là văn do MiniMax-M3 viết lại, sạch, ngắn, đã chắt lọc. Lúc chạy, `chat_max_context_chars
= 6000` ký tự **văn crawl thô** từ 5 chunk. Model chưa từng được train để lọc nhiễu từ văn thô.
Cộng với A2 (đổi nhãn) → hai lý do độc lập cùng dẫn tới `RRR − RNR = 0`.

### B5. Một thầy duy nhất

`gen_model` của **48.705/48.705** dòng = `MiniMax-M3`. Distillation một thầy ⇒ trần chất
lượng, độ dài và độ bao phủ **bằng đúng trần của MiniMax-M3 ở nhiệm vụ này**. Không có cơ chế
nào để học sinh vượt thầy.

### B6. Mất cân bằng lớp

| `sample_type` | n | % |
|---|---|---|
| `clinical_chat_response` | 46.510 | 95,5 |
| `medical_safety` | 503 | 1,0 |
| `insufficient_info` | 448 | 0,9 |
| `out_of_domain` | 493 | 1,0 |
| `prompt_injection` | 415 | 0,9 |
| `abuse_extreme` | 336 | 0,7 |

503 mẫu an toàn y tế trên 48.705. Ghép với phát hiện N2 của `ASSESSMENT_review.md`
(8/21 ca từ chối fail, generator mạnh sửa được 0) — lỗi từ chối gốc ở intake, nhưng
SFT cũng không cho generator đủ ví dụ để cứu vãn khi guard trượt.

---

## C. System prompt lúc chạy — mâu thuẫn trực tiếp với rubric

Ngoài chuyện model chưa từng thấy nó (A1), nội dung của nó **chủ động ép ngắn**:

| Câu trong `SYSTEM` đang phục vụ | Rubric nói ngược lại |
|---|---|
| *"đi thẳng vào vấn đề, không chào hỏi rườm rà, không dẫn dắt dài dòng"* | `answer_quality` 5 = *"phủ hết các ý mong đợi"* |
| *"**Ngắn gọn với ca đơn giản**, chi tiết hơn khi phức tạp"* | `missing_content` 0 = *"không bỏ sót ý mong đợi nào"* |
| *"Thiếu dữ kiện… **hỏi lại ngắn gọn tối đa 1–2 câu**"* | `missing_content` 3 = *"đọc xong vẫn không biết làm gì"* |
| *"Disclaimer… **tối đa một lần ở cuối**"* | ăn mất ~80/377 ký tự ngân sách |

Đây là mâu thuẫn thiết kế thật, không phải bug: prompt tối ưu cho trải nghiệm chat, rubric
tối ưu cho độ đầy đủ lâm sàng. **Phải chọn một.** Nếu chọn rubric thì sửa prompt; nếu chọn
prompt thì rubric hiện tại đang đo sai mục tiêu sản phẩm và con số 2.43/5 mất ý nghĩa.

---

## D. Metric — phần lớn công bằng, một chỗ cần kiểm

**Công bằng:**

- Neo của `answer_quality` **là** neo độ bao phủ, ghi thẳng trong `rubrics.py`: mức 2 =
  *"thiếu phần lớn các ý mong đợi"*, mức 3 = *"thiếu ít nhất một ý mong đợi quan trọng"*.
  RRR có 78/145 dòng đúng mức 2 — không phải judge khắt, mà là neo đang bắn đúng.
- Rubric **có** phân biệt được: cùng thang, RRO đạt 3.54 và RNO 3.70. Không bão hoà, không sập.
- `incorrect_content` tách riêng nên "thiếu" không bị trừ hai lần (§Med-PaLM trong `rubrics.py`).
  RRR = 0.30 xác nhận model không bị chấm oan vì sai.

**Cần kiểm — đây là chỗ "metric không công bằng" còn sống:**

1. `expected_answer_points` là **synthetic, `annotation_status: synthetic_pending_review`**,
   chưa qua mắt người. Nếu một ý mong đợi đòi liều/tần suất mà `SYSTEM` **cấm** nói
   (*"không đưa liều/tần suất/thời gian dùng thuốc"*), thì model đang bị phạt vì tuân thủ
   chính luật an toàn của nó. Phải soi tay ~30 dòng để biết tỉ lệ này.
2. Nhiễu judge trên `answer_quality` **chưa đo**. N1 của `ASSESSMENT_review.md` chỉ đo được
   4 mặt context (nhờ `RRO`/`RRR` dùng chung chunk). Cần chấm lại 2 lượt cùng một tập câu
   trả lời để có sd cho trục chính.

---

## E. Đã loại trừ

| Nghi phạm | Bằng chứng loại |
|---|---|
| `num_predict` cắt câu | advise dùng `llm_num_predict = 2048` (`config.py:29`), knowledge dùng `-1`. Output p50 377 ký tự ≈ 130 token. **Không chạm trần.** |
| `temperature` / `top_p` | 0.3 / 0.9 ở Modelfile, 0.35 / 0.85 ở `config.py`. Lệch nhỏ, không tạo ra khoảng cách 1.04. |
| Retriever | run v3.2 đã chứng minh: `ROR − RRR = +0.25`, và relevance/precision/ranking đã ngang oracle. |
| Quantization Q4_K_M | có thể góp, nhưng không giải thích được vì sao độ dài output trùng khít phân bố nhãn (B1). Kiểm sau, không kiểm trước. |

---

## F. Thứ tự kiểm chứng — rẻ trước, đắt sau

| # | Việc | Chi phí | Bác bỏ / xác nhận |
|---|---|---|---|
| **1** | Chạy lại `RRR` trên đúng 145 mẫu, nhưng prompt theo **định dạng SFT**: system 540 ký tự + `<raw_user_message>` / `<normalized_case>` / `<guideline_context>` | ~2 h GPU, **0 đ** | Nếu `answer_quality` nhảy → **A1–A4 là nguyên nhân, không cần train lại**. Đây là bài test rẻ nhất và có sức bác bỏ mạnh nhất. Làm trước mọi thứ khác. |
| **2** | `ollama show acne-generator --modelfile`, đối chiếu sha256 với `model/generator/Modelfile.full` | 5 phút | Chốt xem production có đang chạy bản legacy như eval không |
| **3** | Soi tay 30 `expected_answer_points`: có ý nào bị `SYSTEM` cấm nói không | 1 h người | Cân đo phần D.1 |
| **4** | Chấm lại `RRR` lần 2 bằng cùng judge → sd của `answer_quality` | ~30 $ | Biết 2.43 dao động bao nhiêu |
| **5** | Nếu #1 không cứu được: sinh lại SFT — target 800–1.500 ký tự, có cấu trúc, chunk **thô** thay vì tóm tắt, ≥ 2 thầy, nâng `medical_safety` lên ≥ 10 % | tốn nhất | Chỉ làm sau khi #1 loại được giả thuyết prompt |

---

## G. Một cảnh báo về cách sửa

Trong nội bộ arm RRR, **câu trả lời càng dài thì điểm càng thấp**: Pearson `r = −0.310`
(len ↔ `answer_quality`), và `r = +0.219` với `missing_content`. Ở RRO thì độ dài
**không tương quan** (`r = +0.041`).

Nghĩa là: khi `acne-generator` bị đẩy dài ra, nó **lan man chứ không phủ thêm ý**. Đừng sửa
bằng cách nới `num_predict` hay thêm câu *"hãy trả lời chi tiết hơn"* vào prompt — đo được là
sẽ tệ hơn. Vấn đề không phải **số token**, mà là **nội dung trên mỗi token**, và cái đó chỉ
đổi được ở A (định dạng prompt) hoặc B (nhãn huấn luyện).
