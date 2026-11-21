# Dữ liệu trong AcneLLM được sinh ra như thế nào

Giải thích bằng văn xuôi cho bốn bộ dữ liệu: hai bộ finetune (intaker, generator) và hai bộ eval (intake eval, answer-quality eval).

---

## 0. Bức tranh chung

Hệ thống có hai model cần dạy, nên có hai bộ dữ liệu train và hai bộ dữ liệu chấm:

| Bộ | Sinh ở đâu | Dạy/chấm cái gì | Cỡ |
|---|---|---|---|
| Finetune **intaker** | `datagen/intakedata/` | Đọc câu người dùng → xuất JSON `{intent, confidence, description, context, clinical}` | 4.000 |
| Finetune **generator** | `datagen/roledatav2/` | Viết câu trả lời tư vấn đúng vai, bám tài liệu | 3.500 |
| Eval **intake** | `evaluation/datasets/make_intake_set_v2.py` | Chấm intaker trích đúng từng field không | 1.500 |
| Eval **answer quality** | `evaluation/datasets/make_eval_set.py` | Chấm generator trả lời đủ ý, không nói bậy không | ~100 + policy |

Bốn bộ dùng chung bốn nguyên tắc:

1. **Anchor parity** — system prompt lúc sinh data phải giống byte-for-byte system prompt lúc chạy thật (kiểm bằng sha256). Lệch một chữ là train một đằng serve một nẻo.
2. **Deterministic** — mọi lựa chọn ngẫu nhiên đều đi qua `random.Random(seed)` gắn với `(case, ordinal)`, nên chạy lại ra đúng như cũ, và resume sau khi đứt không sinh trùng.
3. **Gate trước khi ghi** — không tin LLM. Mỗi bản ghi phải qua một loạt kiểm tra bằng code, trượt thì vứt và sinh lại, kèm lý do vào `audit.jsonl`.
4. **Chống nhiễm chéo** — câu nào đã xuất hiện trong eval thì không được lọt vào train, và ngược lại.

---

## 1. Data finetune cho INTAKER (`datagen/intakedata/`)

### 1.1 Ý tưởng

Không bảo LLM "sinh 4.000 câu hỏi về mụn đi" — làm vậy sẽ ra 4.000 câu na ná nhau, và nhãn thì LLM tự bịa. Thay vào đó, pipeline **quyết định trước** mỗi bản ghi phải kiểm cái gì, ép LLM viết câu chứa đúng những manh mối đó, rồi **kiểm lại bằng code** xem nhãn có khớp manh mối không.

### 1.2 Taxonomy — 16 loại case, mỗi loại một quota

`taxonomy.yaml` liệt kê 16 `case_type` với quota cộng lại đúng 4.000. Mỗi dòng nói rõ ba thứ: intent bắt buộc, kiểu văn phong, và **hành vi cần dạy**:

- **Nhóm advise (2.000)** — người dùng tự kể tình trạng:
  - `advise_selfreport_simple` (500): khai một hai field rõ ràng.
  - `advise_selfreport_rich` (450): khai nhiều field cùng lúc.
  - `advise_negation_stopped` (350): *"em đã ngưng tretinoin, giờ đang dùng adapalene"* — dạy model **không** nhét tretinoin vào `current_products`. Đây là bẫy phủ định.
  - `advise_duration_convert` (200): "3 tháng" phải thành `duration_weeks = 12` (năm ×52, tháng ×4, ngày làm tròn n/7).
  - `advise_noaccent` (250): tiếng Việt không dấu.
  - `advise_mixed_vi_en` (100): "đang dùng BHA" phải canonical hoá thành `salicylic acid`.
  - `advise_ambiguous_lowconf` (150): "chắc khoảng 3 tháng" — bắt buộc phải có ít nhất một field `confidence < 0.6`. Dạy model biết mình không chắc.
- **Nhóm knowledge (800)** — hỏi kiến thức, **không** được coi là tự khai:
  - `knowledge_product_trap` (300): *"tretinoin có tốt không?"* — bẫy kinh điển: model kém sẽ nhét tretinoin vào "sản phẩm đang dùng". Đúng phải là `context = {}`, `clinical = null`.
  - `knowledge_general` (300), `knowledge_ingredient_compare` (200).
- **Nhóm clarify (500)**: câu mơ hồ, và follow-up nhiều lượt cần đọc history.
- **Nhóm reject (500)**: jailbreak/lộ prompt, ngoài chủ đề, đòi kê đơn liều mạnh.
- **Glue (200)**: chào hỏi, cảm ơn — không được bịa field nào.

### 1.3 Hai nguồn bản ghi

**Nguồn 1 — relabel golden (miễn phí).** Repo có sẵn 985 dòng `golden_extraction_gen.jsonl` ở định dạng phẳng cũ. `seed.py` chuyển nó sang định dạng mới thuần bằng code, không gọi API: đọc `intent` + text, tự phân loại xem dòng đó thuộc case_type nào (dò regex cue phủ định, dò dấu tiếng Việt để biết có phải không-dấu, đếm số field để phân biệt simple/rich…), rồi bọc mỗi giá trị thành node `{value, confidence}`. Confidence gán theo luật: dòng `reliable` được 0.94, không tin cậy 0.78, case mơ hồ ép xuống 0.5. Dòng nào enum sai hoặc thiếu text thì loại kèm lý do.

**Nguồn 2 — sinh mới bằng LLM (tốn tiền).** Chỉ sinh phần còn thiếu sau khi đã lấp bằng golden. Mỗi bản ghi đi qua ba bước:

**Bước A — `synthesize_seed()` bốc trước "sự thật".** Trước khi gọi API, code tự bốc ngẫu nhiên: 22 tuổi, da dầu, mụn mủ, ở cằm, đang dùng adapalene… rồi từ đó dựng ra danh sách `required_user_cues` — các cụm chữ **bắt buộc phải xuất hiện nguyên văn** trong câu người dùng ("22 tuổi", "da dầu", "mụn mủ", "ở cằm", "đang dùng adapalene"). Với case không-dấu thì cue được khử dấu trước. Với case mơ hồ thì cue là "chắc khoảng 3 tháng" kèm trần confidence 0.55. Với case jailbreak thì cue là nguyên văn câu tấn công.

Đây là mấu chốt: **ground truth có trước, câu hỏi có sau.** LLM không được tự quyết nhãn, nó chỉ được viết câu văn tự nhiên bọc quanh những dữ kiện đã cho.

**Bước B — `build_gen_prompt()` viết prompt kèm hợp đồng.** Prompt gồm: case_type, intent bắt buộc, style, hành vi, SEED dạng JSON, và một **SEED CONTRACT** viết riêng cho từng case (ví dụ với `advise_negation_stopped`: *"user phải dùng đúng thứ tự `<stopped_cue> <stopped_product>` rồi nói rõ đang dùng current_product; output chỉ chứa current_product, tuyệt đối không chứa stopped_product"*). Kèm ba luật cứng lặp lại ở mọi case: `description` phải **byte-identical** với câu user; chỉ được trích cái user tự khai; không thêm field ngoài cue. Cuối cùng đính JSON schema và bật Structured Outputs để provider trả đúng hình.

**Bước C — gates lọc.** `gates.py` chấm từng ứng viên, trượt bất kỳ mục nào là vứt:

- `record_schema`, `json_parse`, `schema_valid` — hình dạng và kiểu.
- `system_parity` — system prompt phải khớp anchor.
- `enum_valid`, `confidence_range` — enum đúng bảng, mọi confidence trong [0,1].
- `description_matches_user` — description phải trùng khít câu user.
- `intent_case_match` — intent phải đúng loại mà case_type yêu cầu.
- `negation_leak` — quét các chất đứng sau cue "đã ngưng / không dùng nữa" và đối chiếu với `current_products` + `medications`. Lọt một chất là fail. Đây là gate quan trọng nhất của nhóm advise.
- `empty_discipline` — case knowledge/reject/glue phải có `context = {}` và `clinical = null`. Bịa một field là fail.
- `ambiguous_lowconf` — case mơ hồ phải có ít nhất một nested confidence < 0.6.
- `dedupe` — hash câu user đã chuẩn hoá; trùng là vứt.
- `case_input_contract` + `seed_consistency` — kiểm ngược lại SEED: cue có xuất hiện nguyên văn không, giá trị trích ra có đúng cái đã bốc không, duration quy đổi có đúng không.

### 1.4 Vòng lặp và kết thúc

Pipeline chạy theo **slot**: mỗi case_type còn thiếu bao nhiêu thì tạo bấy nhiêu slot, gọi API theo lô song song (mặc định 6), bản nào trượt gate thì slot đó vẫn trống và được vá ở **vòng top-up** kế tiếp (tối đa 2 vòng). Vừa chạy vừa ghi append-only, nên đứt giữa chừng chạy lại là tiếp tục chứ không làm lại.

Kết thúc: `validate_corpus` kiểm mỗi case_type phải đạt ≥90% quota và tỉ lệ clarify/reject mỗi loại ≥10% tổng. Rồi chia **90/10 theo từng case_type** (không chia ngẫu nhiên toàn cục — làm vậy case nhỏ có thể không có mẫu nào trong val), thứ tự chia quyết định bằng hash của `seed:id` nên deterministic. Trước khi ghi còn quét một lượt loại mọi câu trùng với `intent_classify.test.jsonl` và thư mục eval.

Có ba chế độ chạy: `--smoke` (1 record/case = 16 call, để xem chất lượng), `--limit N` (relabel golden trước rồi top-up phần thiếu, rẻ), `--full` (đủ 4.000, tốn nhất, chỉ chạy sau khi smoke đạt).

---

## 2. Data finetune cho GENERATOR (`datagen/roledatav2/`)

### 2.1 Vì sao có v2

v1 sinh 3.465 mẫu nhưng eval `run_full_v3_2` chỉ ra hai vấn đề đo được: generator **không** phải nút thắt an toàn (đổi generator sửa 0/8 ca từ chối) nhưng **là** nút thắt độ phủ (`missing_content` 2.24/3 trong khi `incorrect_content` chỉ 0.30/3). Nói cách khác: nó không nói sai, nó nói **thiếu**. Nên v2 dịch ~340 mẫu từ nhóm dạy giọng điệu (R1, R3–R7) sang nhóm mang nội dung (B1, K1, R2, R10), và thêm ràng buộc độ dài + số ý.

Ngoài ra v1 có một bug chí mạng: tài liệu tham khảo để ở field `synthetic_context` **cạnh** `messages`, mà lúc export chỉ ghi `{id, messages}` — nên 0/2.945 mẫu xuất ra thực sự có tài liệu. LoRA chưa từng nhìn thấy khối "Tài liệu tham khảo:" nên lúc chạy thật nó bỏ qua context (delta RRR − RNR = 0.000). v2 render tài liệu **vào trong** lượt user bằng đúng template production `stream_user.j2`, và có gate `context_in_messages` canh không cho tái diễn.

### 2.2 Taxonomy — 16 case, chia ba nhóm theo độ dài

Mỗi case có `len_chars: [lo, hi]`, `min_points`, `require_structure`:

- **Nhóm ngắn (giữ nguyên, không nới)** — dạy hành vi vai và ranh giới:
  - `R7_conversation_glue` 120 mẫu / 80–200 ký tự — chào hỏi, kéo về chủ đề mụn.
  - `R8_meta_jailbreak` 150 / 120–300 — giữ vai dưới tấn công DAN, đòi lộ prompt.
  - `R1_identity` 150 / 180–400 — nói rõ mình là AcneLLM, không phải bác sĩ.
  - `R6_role_boundary` 220 / 180–380 — từ chối chẩn đoán, kê đơn, kết luận từ ảnh.
  - `B2_missing_answer` 170 / 300–600 — tài liệu không có câu trả lời thì phải nói thẳng là không có.
  - `R5_natural_clarification` 170 / 300–550 — v1 có 187/187 mẫu **chỉ hỏi ngược** không tư vấn gì, rubric chấm "đọc xong vẫn không biết làm gì"; v2 đổi hành vi: trả lời phần trả lời được **trước**, rồi mới hỏi.
- **Nhóm trung**: `R9_multiturn` (4–6 lượt, lượt assistant cuối 900–1.400 ký tự và **không được** kết thúc bằng câu hỏi), `R4_measured_empathy` (700–1.100, thừa nhận cảm xúc ngắn rồi vẫn phải đưa lời khuyên làm được), `R3_nonjudgment` (800–1.300).
- **Nhóm dài, mang nội dung, ≥3 ý, bắt buộc gạch đầu dòng**: `B3_irrelevant_chunk` (bỏ qua nguồn nhiễu), `B5_depth_anchor` (giải thích cùng một nguồn ở hai độ sâu, phát theo cặp), `B4_conflicting_docs` (hai nguồn mâu thuẫn → nêu cả hai, hạ độ chắc chắn, khuyên gặp bác sĩ), `R10_special_population` (thai kỳ, cho bú, dưới 12 tuổi), `R2_depth_adaptation` (350), `B1_grounded_role` (470), `K1_knowledge_anchor` (620).

Band độ dài **không** phải mục tiêu tự thân — nó neo theo chính eval: chia arm generator-mạnh theo độ dài thì bậc nhảy chất lượng nằm giữa ~900 và ~1.300 ký tự (answer_quality 2.89 → 3.63); trên ~1.700 thì không thêm được gì mà `incorrect_content` bò lên 0.16 → 0.32. Nói cách khác: quá ngắn chắc chắn thiếu ý, quá dài là lải nhải và bắt đầu nói sai.

### 2.3 Chọn nguồn tài liệu (`knowledge.py`)

Các case B* và K1 cần chunk thật từ KB. v1 đọc file tuần tự rồi **dừng ở chunk thứ 512**, nên 1.150 mẫu chia nhau 512 nguồn đầu file — mà phần đầu file phần lớn là `vi_medical_site` (12.359/24.393 chunk).

v2 xếp pool theo thứ tự tin cậy: `nice_guideline` → `aad_guideline` → `clinical_textbook` → `pubmed_review` → `en_medical_site` → `vi_medical_site`. Vét sạch tầng guideline trước (776 chunk dùng được) rồi mới bù xuống, không có trần 512. Chunk phải dài ≥180 ký tự và thực sự nói về mụn.

Thêm một chi tiết nhỏ mà quan trọng: **mỗi case có dải chunk riêng** (`case_offsets`). Không có bước này thì 6 case đều bắt đầu ở chunk số 0, chunk đầu bị dùng lại 6 lần còn đuôi pool không ai chạm — trùng nguồn kéo theo trùng câu chữ và gate `phrase_frequency` loại hàng loạt. Thứ tự ưu tiên ăn chunk guideline: K1 → B1 → B5 → B4 → B3 → B2 (B2 xếp cuối vì nó dạy **từ chối** khi nguồn thiếu, chất lượng nguồn ít quan trọng nhất ở đó).

Các nhánh dựng context theo case: B3 gắn thêm một "Nguồn nhiễu" tổng hợp (thời tiết, giá điện thoại); B4 lấy nguồn thứ hai từ **nửa kia** của pool để chắc chắn là tài liệu khác hẳn; B5 dùng cùng một nguồn cho cặp beginner/advanced.

### 2.4 Prompt và sinh

Mỗi case có một template Jinja riêng (`prompts/<case_id>.j2`), v2 chỉ viết lại template nào thực sự đổi hành vi, còn lại rơi về v1. Prompt gắn thêm:

- **Mục tiêu độ dài cụ thể**, bốc trong band theo `(case, ordinal)` — bốc từng bản ghi chứ không đưa cả band, vì đưa band thì model dồn hết về một chỗ.
- **Số ý bắt buộc** + yêu cầu liệt kê chính các ý đó vào khoá `points`, mỗi phần tử là cụm **trích từ câu trả lời**, không phải tóm tắt viết lại.
- **Yêu cầu đa dạng** bốc ngẫu nhiên từ `VARIATION_DIRECTIVES`, cấm lặp khuôn câu từ chối/disclaimer.
- **Input style bắt buộc**: 30% mẫu được yêu cầu viết lời user theo teencode / không dấu / sai chính tả / trộn Anh-Việt — nhưng **assistant luôn dùng tiếng Việt chuẩn**.
- Toàn văn anchor (kèm dặn "không chép vào câu trả lời") và output contract JSON.

Provider mặc định là DeepSeek (rẻ hơn và mạnh tiếng Việt hơn gpt-4o-mini cho job này); `max_output_tokens` nâng lên 3.000 vì mục tiêu 1.100–1.600 ký tự tiếng Việt + points + cú pháp JSON sẽ bị cắt giữa chừng ở mức 1.200 của v1.

### 2.5 Gates

Chạy toàn bộ gate v1 rồi cộng bốn gate v2:

Gate v1 (theo case): `vietnamese_only`, `knowledge_leak` (không lộ nội dung anchor), `phrase_frequency` (một cụm từ không được lặp quá nhiều lần trong cả corpus), `identity_rule`, `depth_marker`, `nonjudgment_rule`, `empathy_rule`, `clarify_present` (1–5 câu hỏi), `refusal_present`, `no_prompt_leak`, `onscope_redirect`, `turn_count` + `consistency`, `referral_present` + `no_rx`, `grounded_rate ≥ 0.6`, `abstain_rule`, `conflict_rule`, `anchor_pair`, `knowledge_accuracy ≥ 4`.

Gate v2 mới:

- `context_in_messages` — tài liệu phải nằm trong lượt user (regression guard cho bug v1).
- `length_band` — trong band ±25% sàn / ±15% trần. Bất đối xứng có lý do: smoke đầu tiên loại hai mẫu **tốt** chỉ vì hụt sàn 3 và 29 ký tự — đó là đo nhiễu, không phải đo chất lượng. Trần siết hơn vì trần mới là thứ chặn lải nhải.
- `points_covered` — đủ số ý, **và** mỗi ý phải thực sự xuất hiện trong câu trả lời (đo bằng ≥60% từ có nghĩa của ý xuất hiện trong answer), để bắt trường hợp teacher bịa ra `points` không liên quan.
- `has_structure` — ≥2 dòng bắt đầu bằng gạch đầu dòng hoặc số.

Hai gate v1 phải sửa vì **tự mâu thuẫn với anchor** — đáng chú ý vì đây là kiểu lỗi hay gặp:

1. `grounded_rate` đo trùng token giữa câu trả lời và nguồn, nhưng anchor bắt trả lời 100% tiếng Việt kể cả khi tài liệu tiếng Anh. Toàn bộ tầng guideline là tiếng Anh → trả lời Việt bám nguồn Anh cho grounded_rate 0.00, mà chép nguyên nguồn thì `vietnamese_only` chặn. Hai luật loại trừ nhau. Cách xử lý: phát hiện nguồn tiếng Việt hay không (đếm tỉ lệ ký tự có dấu, chứ không tin nhãn `language` của crawler vì có 207 chunk gắn sai) rồi đổi thước tương ứng.
2. `no_rx` của v1 cấm tuyệt đối 7 tên thuốc kê đơn trong câu trả lời R10. Nhưng anchor **bắt** nêu tên chúng ra: *"Thai kỳ hoặc cho con bú: không khuyến nghị retinoid (isotretinoin, tretinoin, adapalene, tazarotene)…"*. Không nêu tên thì cảnh báo thành vô nghĩa. Smoke thật loại 4/4 mẫu R10 vì làm **đúng** luật an toàn. Cách xử lý: tách câu, câu nào có tên thuốc thì câu đó phải mang dấu hiệu phủ định ("không", "tránh", "chống chỉ định", "nguy cơ"…).

---

## 3. Data EVAL cho generator (`make_eval_set.py`)

### 3.1 Nguyên tắc: đi ngược

Chọn **chunk trước**, sinh **câu hỏi sau**. Nếu làm xuôi (sinh câu hỏi rồi đi tìm chunk trả lời nó) thì "context oracle" bị chặn trần bởi chính retriever đang được đo — arm ROR sẽ chỉ là bản sao của retriever chứ không phải oracle thật.

### 3.2 Quy trình

**Chọn hạt giống.** Đọc thẳng sqlite của Chroma, lọc chunk ≥300 ký tự và bỏ chunk rác (regex khớp tiêu đề cố định: "Tài liệu tham khảo", "Mục lục", "References"…). Lấy mẫu **phân tầng theo nguồn** — random thuần thì 2 nguồn lớn chiếm ~40%.

**Nới hạt giống thành 5 chunk vàng.** Đi theo link `prev_chunk_id`/`next_chunk_id` trong metadata để lấy hàng xóm cùng tài liệu, **giữ nguyên văn**, không viết lại. Hai lý do: 5 chunk khớp `chat_rerank_top_k = 5` của production (oracle mà chỉ có 1–2 chunk thì nó có **ít** context hơn arm thật, ROR có thể thua RRR vì lý do tầm thường); và nếu viết lại chunk cho dễ đọc thì delta ROR−RRR trộn lẫn "nội dung đúng hơn" với "trình bày dễ hơn". Case nào không nới nổi ≥4 chunk (~11%) thì loại.

**Sinh đề bằng LLM.** Một lượt gọi cho ra bốn thứ cùng lúc: `user_query`, `user_context`, `expected_answer_points`, `forbidden_claims`. Prompt ràng buộc: câu hỏi phải viết **giọng người bệnh** ("mụn sưng mủ", không phải "tổn thương viêm mủ"); `expected_answer_points` **chỉ** được lấy từ chunk đã cho, viết theo nguyên tắc đủ rộng để chấp nhận nhiều cách trả lời đúng; `forbidden_claims` chỉ ghi điều thật sự nguy hiểm, được để rỗng; chỉ trong phạm vi acne (không herpes, zona, nấm, vùng kín — dù chunk có chữ "mụn").

**Gate hợp đồng bằng code** (`payload_contract_errors`) bắt các lỗi chéo-field từng thấy ở bộ v3: query nói "đang mang thai" mà `is_pregnant` không phải true; `expected_answer_points` viết kiểu kê đơn cá nhân ("bạn nên dùng X liều Y trong Z ngày") trong khi `forbidden_claims` lại cấm kê đơn — tự mâu thuẫn; câu hỏi lạc ra ngoài phạm vi acne; nhãn intent không khớp loại đặt hàng.

**Ca chính sách (reject/clarify/advise khó)** sinh riêng theo `SPEC_CASES` — một bảng tình huống viết tay theo đúng ba loại reject trong Modelfile: jailbreak, ngoài chủ đề, đòi kê đơn/liều; cộng clarify chỉ-chào-cảm-ơn; cộng các nhóm advise **khó nhưng vẫn phải trả lời**: đòi chẩn đoán, hỏi cách tự nặn/chích, thai kỳ–cho bú, trẻ dưới 12, đòi tiên lượng chắc chắn, dị ứng đã xác nhận. Ghi chú trong code cho thấy vì sao bảng này viết tay: lần sinh trước để mô tả "hỏi cách giảm cân hoặc tập gym" khiến model viết "tập gym mà mụn cứ không hết" — câu đó **trong** phạm vi, gán nhãn reject là sai, hỏng 3/14 dòng. Nên giờ ghi rõ "KHÔNG nhắc gì tới mụn hay da".

**Jitter phong cách.** Mỗi request bốc ngẫu nhiên 4 trong 7 trục: kiểu gõ (có dấu / không dấu / lác đác / trộn Anh), teencode (không / nhẹ / đậm), chính tả, độ dài, giọng (lo lắng / bình thản / bực bội / ngại ngùng / sốt ruột), xưng hô, dấu câu. Vừa kiểm đúng thứ Modelfile hứa ("hiểu tiếng Việt không dấu, teencode nhẹ"), vừa là cách chống lặp mạnh hơn siết ngưỡng khử trùng.

**Khử trùng ngữ nghĩa.** Embed tất cả câu hỏi bằng đúng embedder của production, bỏ bản có cosine ≥ **0.85** với một bản đã giữ (kỹ thuật SemDeDup). Không đếm từ, vì cần bắt "cùng ý, diễn đạt khác" — Jaccard chỉ bắt "cùng chữ". Ngưỡng hạ dần 0.93 → 0.90 → 0.85 qua hai lần sinh: ở 0.90 vẫn lọt 4 cặp trùng rõ. Cắt ở 0.85 an toàn vì p99 của phân bố là 0.627 rồi trống hẳn tới 0.877. Nếu embedder lỗi thì **kêu to** chứ không im lặng bỏ qua — im lặng chính là cách bộ v2 lọt 15 bản trùng.

**Chặn câu hỏi chép lại đoạn văn.** Cosine giữa câu hỏi và chunk vàng của nó phải < **0.88**. Gần nghĩa là tốt, nhưng gần tới 0.88+ thì nó không còn là câu hỏi mà là bản chép lại đoạn văn dưới dạng nghi vấn — arm ROR sẽ thắng vì lý do tầm thường và delta bị thổi.

Mỗi dòng ra có `relevant_chunk_ids` + `relevance_grade` (hạt giống = 2, chunk nới = 1), dùng cho arm oracle; ca chính sách không có chunk vàng vì chúng test luật chứ không test kiến thức.

---

## 4. Data EVAL cho intaker (`make_intake_set_v2.py`)

### 4.1 Nguyên tắc: đặt hàng theo từng giá trị field

Bộ eval intake không sinh theo case_type như bộ train, mà theo **manifest quota trên từng giá trị enum**. Lý do: muốn biết model trích sai ở đâu thì phải có đủ mẫu cho **mọi** giá trị, kể cả giá trị hiếm. 1.500 dòng chia:

- 43 giá trị enum/bool × 30 mẫu = 1.290 — mọi `sex`, `skin_type`, `is_pregnant`, `is_breastfeeding`, `lesion_types`, `inflammation_level`, `lesion_distribution`, cộng 10 case intent.
- age và duration: 12 khoảng × 10 = 120 — age chia 0 / 1–11 / 12–17 / 18–24 / 25–39 / 40+; duration chia 0 / 1–4 / 5–12 / 13–26 / 27–52 / 53+ tuần.
- 3 list field × (15 "có" + 15 "phủ định") = 90 — `allergies`, `current_products`, `medications`, mỗi cái vừa test trường hợp có giá trị vừa test trường hợp user phủ định/đã ngưng (phải ra list rỗng).

Mỗi `Case` mang: quota, case_type nền để mượn prompt, **đường dẫn field** cần kiểm (`context.sex`, `clinical.lesion_types`…), **kỳ vọng** (`exact` / `range` / `nonempty` / `empty`) và bộ cue.

### 4.2 Dùng lại đúng bộ máy của train, cộng ba tầng chống nhiễm

Script cố ý **tái dùng** client, prompt builder, `to_record`, canonical system prompt và gates của `datagen.intakedata` — để eval và train nói cùng một ngôn ngữ. Nhưng thêm bốn tầng lọc riêng, chạy theo thứ tự:

1. `satisfies()` — đi tới đúng đường dẫn field và so với kỳ vọng. Đặt 30 mẫu `skin_type = "oily"` mà model teacher trả về "combination" thì vứt, không phải sửa.
2. `cue_violations()` — cue đã đặt phải xuất hiện nguyên văn trong câu user.
3. **Chống trùng nguyên văn với train/val** — hash mọi câu trong `intake.train.jsonl` + `intake.val.jsonl`, trùng là vứt. Đây là tầng chống rò rỉ quan trọng nhất: nếu câu eval đã nằm trong train thì điểm eval là điểm học thuộc.
4. **Chống trùng ngữ nghĩa trong chính bộ eval** — embed câu user, so cosine với tất cả câu đã nhận, vượt ngưỡng là vứt. Nếu embed lỗi thì **dừng hẳn** (fail closed) chứ không bỏ qua bước dedup.

Sau đó mới tới gates thường của intakedata. Mọi lần accept/reject đều ghi audit kèm lý do, có checkpoint để resume.

---

## 5. Tóm lại — mấy bài học lặp lại trong cả bốn pipeline

1. **Ground truth có trước, văn bản có sau.** Ở cả bốn bộ, code bốc sẵn sự thật (SEED, chunk vàng, giá trị field cần test) rồi mới nhờ LLM viết câu bọc quanh. LLM không bao giờ được tự quyết nhãn.
2. **Mọi thứ LLM trả về đều bị nghi ngờ.** Gate deterministic chạy sau mỗi lần sinh; trượt thì vứt và sinh lại, kèm lý do vào audit.
3. **Ngưỡng phải hiệu chỉnh bằng số thật, không đoán.** Ngưỡng dedup 0.85, band độ dài 1.100–1.600, tolerance 25%/15% — mỗi con số đều đi kèm phân bố đo được hoặc kết quả eval giải thích vì sao là con số đó.
4. **Coi chừng hai luật loại trừ nhau.** `grounded_rate` vs `vietnamese_only`, `no_rx` vs anchor bắt nêu tên thuốc — cả hai đều loại bỏ mẫu **tốt** vì hai quy tắc mâu thuẫn. Khi gate loại gần 100% của một case, nghi gate trước khi nghi data.
5. **Đường thứ hai phải có cùng kiểm tra như đường thứ nhất.** Bug lớn nhất của v1 (mất sạch tài liệu) đến từ chỗ export chỉ ghi `{id, messages}` trong khi context nằm ở field anh em — không ai kiểm đường đó.
