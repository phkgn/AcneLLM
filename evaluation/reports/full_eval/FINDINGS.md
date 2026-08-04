# Kết quả eval — 804/804 dòng

Bộ câu hỏi `evaluation/datasets/eval_set.jsonl` · 134 câu × 6 arm
Generator local `acne-generator` · judge `gpt-5.4-mini` · generator API `gpt-5.6-terra`

---

## Bảng arm

| arm | ok | bỏ | lỗi | quality | tone | safety✗ | refusal | dài p50 |
|---|---|---|---|---|---|---|---|---|
| `RRR` mốc | 134 | 0 | 0 | 2.70 | 3.50 | **18** | 86% | 404 |
| `RNR` tắt RAG | 134 | 0 | 0 | 2.67 | 3.52 | **18** | 86% | 346 |
| `ROR` RAG hoàn hảo | 103 | 31 | 0 | 3.21 | 3.86 | 0 † | 99% † | 404 |
| `ORR` intaker hoàn hảo | 132 | 0 | 2 | 2.72 | 3.63 | **0** | 99% | 388 |
| `RRO` generator API | 134 | 0 | 0 | 4.15 | 4.32 | **18** | 86% | 1583 |
| `RNO` API, tắt RAG | 133 | 0 | 1 | 4.04 | 4.25 | 16 | 88% | 1618 |

† `ROR` bỏ 31 ca `reject`/`clarify` (không có chunk vàng — thiết kế, xem
`eval_context.md` §5). Safety 0 và refusal 99% của nó là **hệ quả của việc bỏ**,
không phải thành tích. Không được trích hai ô này.

## Δ ghép cặp trên cùng câu hỏi

| so sánh | n | Δ | CI 95% | | đọc ra |
|---|---|---|---|---|---|
| `RRR − RNR` | 134 | +0.030 | [−0.134, +0.187] | | RAG thật vs tắt (local) |
| `ROR − RRR` | 103 | **+0.388** | [+0.165, +0.621] | * | RAG hoàn hảo vs thật |
| `ROR − RNR` | 103 | **+0.417** | [+0.223, +0.621] | * | RAG hoàn hảo vs tắt |
| `ORR − RRR` | 132 | +0.008 | [−0.159, +0.174] | | intaker hoàn hảo |
| `RRO − RRR` | 134 | **+1.448** | [+1.246, +1.649] | * | đổi generator |
| `RNO − RNR` | 133 | **+1.376** | [+1.150, +1.594] | * | đổi generator, không RAG |
| `RRO − RNO` | 133 | +0.105 | [−0.045, +0.256] | | RAG thật vs tắt (model mạnh) |

`*` = CI không cắt 0.

---

## Ba kết luận

### 1. Retrieval hiện tại đóng góp bằng không — nhưng RAG thì có

Tắt RAG hẳn, điểm không đổi (`+0.030`, CI cắt 0). Không phải vì model local
không biết dùng: đổi sang `gpt-5.6-terra` thì RAG **vẫn** không đóng góp
(`+0.105`, CI cắt 0). Hai model, cùng kết luận.

Nhưng RAG **hoàn hảo** thì có (`+0.388`, CI không cắt 0). Tỉ lệ khai thác của
retriever ≈ `0.030 / 0.417` = **7%**.

Đo trực tiếp, không qua judge:

```
recall@5 chunk vàng    10/103 = 10%
recall@5 tài liệu      11/103 = 11%   ← sai tài liệu 89%
```

Hai số gần bằng nhau ⇒ hỏng ở **tầng tìm**, không phải tầng xếp hạng. Nếu
reranker là thủ phạm thì doc-recall phải cao hơn hẳn chunk-recall.

Phân bố nguồn, đo độc lập với chunk vàng:

| source_type | trong KB | retriever lấy |
|---|---|---|
| `vi_medical_site` | 51% | **92.7%** |
| `pubmed_review` | 21% | 2.1% |
| `blog` | 14% | 1.1% |
| `en_medical_site` | 9% | 1.0% |

Nghi can chính: `embedding_model = AITeamVN/Vietnamese_Embedding` — model chỉ
tiếng Việt, trên KB **40% tiếng Anh** (9.679 chunk, gồm toàn bộ NICE, AAD,
PubMed, textbook). Cơ chế source-aware đã có sẵn trong `retriever.py`
(`_SOURCE_TYPE_BOOST` guideline 1.60×, guideline pass lọc cứng `source_type`,
MMR) và **đang thua** — boost chỉ nhân vào điểm của chunk đã lọt vào danh sách
ứng viên. Reranker `bge-reranker-v2-m3` vốn đa ngữ, nhưng chưa từng được đưa
cho ứng viên tiếng Anh nào.

### 2. Generator là nút thắt lớn nhất

`+1.448`, gấp gần 4 lần dư địa retriever, và giữ nguyên khi bỏ RAG (`+1.376`).
Hai đường đo độc lập, cùng kết luận.

**Không phải lỗi cấu hình.** Đã loại trừ:

- 0/634 câu trả lời bị cắt giữa chừng (câu nào cũng kết thúc bằng dấu câu)
- `num_predict = 1200` tok ≈ 3600 ký tự; model viết 404, dùng **11%** hạn mức
- `RNR` tắt RAG hẳn — cửa sổ trống, dư >2600 tok — viết **346** ký tự,
  *ngắn hơn* cả khi có tài liệu

Model tự dừng vì nó nghĩ đã nói xong. Ngắn vì bản thân nó ngắn.

Lỗi phụ, rẻ: **9% câu trả lời `RRR` kể lại nguồn** thay vì trả lời
(*"Nguồn 1 cho biết…, Nguồn 2 lại nhấn mạnh…"*). Nhóm đó được 2.17 so với
2.75 của phần còn lại. `RRO` chỉ 1%. Sửa ở prompt.

### 3. Safety chỉ sửa được bằng router — generator mạnh KHÔNG cứu được

| arm | safety✗ | intent của ca hỏng |
|---|---|---|
| `RRR` | 18 | toàn bộ `reject` |
| `RNR` | 18 | toàn bộ `reject` |
| `RRO` **API** | **18** | toàn bộ `reject` |
| `RNO` API | 16 | 15 `reject` + 1 `knowledge` |
| `ORR` | **0** | — |

Đây là kết quả quan trọng nhất của cả run. Thay generator bằng model mạnh gấp
bội, chất lượng lên 1.45 điểm — **safety không nhúc nhích**, vẫn đúng 18 ca
hỏng. Chỉ khi bơm intent đúng vào intaker (`ORR`) thì mới về 0.

Nghĩa là: những ca `reject` bị hỏng **không phải vì model viết dở**, mà vì
**router chuyển nhầm chúng xuống nhánh tư vấn**. Model càng mạnh thì càng viết
một bài tư vấn hay hơn cho một câu lẽ ra phải từ chối.

Phân ly của intaker vì thế là hoàn chỉnh: **0 giá trị cho chất lượng
(`+0.008`), là lá chắn duy nhất cho an toàn.**

---

## Chưa đủ để công bố

**Cohen's κ chưa có.** Toàn bộ cột quality dựa trên một LLM judge chưa ai kiểm.
Không chặn việc sửa — hai việc đáng sửa nhất (recall@5, safety) đều không dựa
vào judge — nhưng chặn việc mang số ra ngoài.

```bash
python -m evaluation.judges.calibrate --export   # 50 mẫu, giấu điểm + giấu arm
# người chấm
python -m evaluation.judges.calibrate --import
```

**`RRO − RRR` nhiễm.** Trace ghi `acne-generator → temperature_0` nhưng
`gpt-5.6-terra → temperature_unsupported_three_runs` (API từ chối
`temperature=0`, lùi về mặc định nhà cung cấp). Hai thay đổi trong một arm —
đúng thứ nguyên tắc (a) của `eval_context.md` sinh ra để chặn. `+1.448` quá lớn
để decoding giải thích hết, nên kết luận đứng, nhưng con số cụ thể thì đừng
trích.

**Sampling của eval khác production, chưa khai báo ở đâu:**

| | ship | eval |
|---|---|---|
| `llm_temperature` | 0.35 | 0.0 |
| `llm_top_p` | 0.85 | 1.0 |
| `llm_top_k` | 40 | 20 |
| `llm_repeat_penalty` | 1.1 | 1.0 |
| `seed` | — | 42 |

Chọn greedy để tái lập được là đúng, nhưng mục bất biến chỉ liệt kê fallback và
cache. Con số 2.70 mô tả *`acne-generator` chạy greedy*, không phải như người
dùng gặp.

**Đã khớp, xác nhận bằng dữ liệu chứ không bằng config:** `llm_model`,
`num_ctx` 3072, `num_predict` 1200, embedder, reranker,
`chat_rerank_top_k` = 5 (0 dòng vượt 5 chunk), `chat_max_context_chars` 6000,
`chat_rerank_floor` 0.5. Fallback chưa từng lén chạy — `generator_model` chỉ
nhận hai giá trị, không lần nào là `qwen2.5:3b`.

**Lỗi kỹ thuật:** 3/804 dòng. 2 `ORR` tràn cửa sổ (đầu vào 3098 > 3072),
1 `RNO`. 0.4%, không đổi kết luận. Nâng `num_ctx` lên 4096 giờ đã an toàn
(run đã xong) — nhưng đừng kỳ vọng nó làm câu trả lời dài ra.

**`grounding_support` không so được giữa các arm.** Metric là
`max(lexical, semantic)` ngưỡng 0.5. `RRR` chọn chunk theo độ tương đồng với
câu hỏi nên context vốn đã trùng từ với câu hỏi (lexical 0.36–0.58); `ROR` lấy
5 chunk liền mạch của một tài liệu, không chọn theo từ khoá (lexical
0.05–0.07). Không phải do ngôn ngữ — đã tách: 0.154 nguồn Anh vs 0.166 nguồn
Việt. Chỉ dùng Δ quality.

---

## Việc tiếp theo, theo thứ tự

**1. Chạy base model chưa fine-tune, 1 arm, cùng bộ câu hỏi.**
Rẻ nhất và quyết định toàn bộ hướng sửa generator. Base tốt hơn → fine-tune làm
hỏng, đi soi SFT data (nhiều khả năng câu trả lời mẫu quá ngắn). Base cũng tệ →
7B không đủ, lên 14B hoặc dùng API cho khâu viết. Hai kết luận dẫn đến hai việc
hoàn toàn khác nhau; hiện chưa có số nào phân biệt được.

```bash
python -m evaluation.runners.run_ablation --arms RRR --model <base-7b> \
  --output evaluation/reports/base_model/results.json
```

**2. Đo recall@50 trước rerank so với recall@5 sau rerank.**
Một script, không train, không API. `@50` cao → reranker vứt nhầm. `@50` cũng
~10% → embedder hỏng, rebuild index bằng `BAAI/bge-m3` (cùng họ với reranker
đang dùng, đã multilingual sẵn).

Phép thử 5 phút trước khi rebuild: lấy nguyên văn một chunk vàng làm query, tìm
lại trong index. Không ra hạng 1 → index hỏng thật (model embedding lúc build
khác lúc query, hoặc quên normalize vector).

**3. Sửa router cho ca `reject`.** 18 ca, và là lá chắn duy nhất — không có
đường vòng nào qua generator. Lưu ý một câu hỏi phương pháp còn mở: 6 category
`reject` trong dataset không khớp hoàn toàn với chính sách sản phẩm; trong 18 ca
hỏng, ~4 là lệch nhãn, ~13 là hỏng thật.

**4. Ba việc vặt.** Ghi 5 tham số sampling vào mục bất biến; ghi
`settings_snapshot` vào `run_meta` để lần sau khỏi audit thủ công; khi so `RRO`
thì cho arm local chạy đúng sampling production để chỉ còn khác mỗi model.

Việc 1 và 2 chạy song song được — một cái ăn GPU cho Ollama, một cái ăn CPU cho
embedder.
