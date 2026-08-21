# Đặc tả sơ đồ workflow eval — AcneLLM

Dùng cho: GPT Image 2 (hoặc bất kỳ model sinh ảnh nào), draw.io, Figma, hoặc
người vẽ tay. Phần 1 là prompt dán thẳng. Phần 2 là đặc tả từng hộp từng mũi tên.

---

## ĐỌC TRƯỚC — giới hạn của model sinh ảnh

Sơ đồ này có **hơn 90 nhãn chữ**, phần lớn tiếng Việt có dấu, cộng tên file và
tên hàm dạng `snake_case`. Model sinh ảnh **không render chữ chính xác** ở mật
độ này: dấu tiếng Việt sẽ sai, `snake_case` sẽ bị nuốt gạch dưới, và số liệu sẽ
bị bịa. Đưa nguyên đặc tả này vào GPT Image 2 sẽ ra một tấm ảnh *trông giống*
sơ đồ nhưng không đọc được.

Ba cách dùng, xếp theo mức khuyến nghị:

1. **Đưa Phần 2 cho draw.io / Figma / Excalidraw** (hoặc cho một model sinh code
   SVG). Chữ chính xác 100%, sửa được, xuất PNG/PDF cho báo cáo. Đây là cách nên
   dùng cho khoá luận.
2. **Đưa Phần 1 (prompt rút gọn) cho GPT Image 2** để lấy một tấm *poster tổng
   quan* — ít chữ, tiếng Anh, dùng cho slide mở đầu chứ không dùng làm hình
   kỹ thuật trong báo cáo.
3. Đưa Phần 2 cho model sinh ảnh và chấp nhận sửa tay chữ sau — không khuyến
   khích.

---

# PHẦN 1 — Prompt rút gọn cho GPT Image 2

Bản tiếng Anh, tối giản chữ, chỉ giữ 18 nhãn ngắn. Dán nguyên khối dưới đây.

```
A clean technical workflow diagram for a machine-learning evaluation pipeline,
drawn as a flat vector infographic on a light cool-grey background (#F5F7F9).
Top-to-bottom flow in 6 horizontal bands, each band a row of rounded rectangles
with thin 1px borders, connected by thin arrows with arrowheads.

Two vertical lanes separated by a subtle gap: the LEFT lane (wider, ~2/3 width)
is labelled "GENERATOR + RAG", the RIGHT lane (~1/3 width) is labelled "INTAKER".

Band 1 "SOURCES": three boxes — "Knowledge Base / 24,393 chunks",
"Hand-written policy cases", "67 quota cases".
Band 2 "GENERATE": two boxes tinted warm amber (#F7F0DE, border #8F6317) —
"make_eval_set", "make_intake_set_v2".
Band 3 "FILTER GATES": two short wide bars tinted dusty rose (#F7E9EB,
border #7A2E3C) labelled "GATES".
Band 4 "FROZEN TEST SETS": two white boxes with a thicker indigo border
(#33507E) — "generator_eval 145" and "intake_eval 1500".
Band 5 "EVAL STAGES": one box "RAG stage", one box "INTAKER stage", and below
them one full-width box "ABLATION" containing six small chips in a row labelled
RRR, RNR, ROR, ORR, RRO, RNO — the first four chips tinted pale indigo, the last
two tinted warm amber.
Band 6 "JUDGE + REPORTS": one amber box "LLM JUDGE", one white box "REPORTS".

Colour code, stated in a small legend at the bottom: indigo = runs locally and
is free, amber = calls a paid API, rose = a filter that rejects.

Style: precise, engineering-drawing feel, generous white space, flat colours,
no gradients, no drop shadows, no 3D, no icons, no photographs, no people.
Typography: a clean geometric sans-serif, uppercase band labels with wide
letter-spacing, sentence-case box labels. Thin hairline rules separating bands.
Landscape orientation, 16:10.
```

**Mẹo khi chạy:** yêu cầu tỉ lệ 16:10 hoặc 3:2, đừng dùng vuông. Nếu chữ vẫn
hỏng, bỏ hết nhãn trong prompt và ghi “no text labels, leave label areas blank”
rồi tự chèn chữ bằng Figma — cách này cho ra hình sạch nhất.

---

# PHẦN 2 — Đặc tả đầy đủ

## 2.1 Khung và lưới

| Thuộc tính | Giá trị |
|---|---|
| Khung vẽ | 1180 × 1148 (đơn vị tuỳ ý, giữ tỉ lệ) |
| Lề trái (nhãn băng) | x = 0 … 140 |
| Vùng nội dung | x = 150 … 1160 |
| Làn GENERATOR + RAG | x = 150 … 815 |
| Làn INTAKER | x = 840 … 1160 |
| Bo góc hộp | 4 |
| Nét viền | 1 px, hộp nhấn 1,6 px |
| Mũi tên | nét 1,4 px, đầu mũi tam giác đặc |

## 2.2 Bảng màu

| Vai trò | Sáng | Tối | Dùng cho |
|---|---|---|---|
| Nền trang | `#F5F7F9` | `#10151C` | |
| Mặt hộp | `#FFFFFF` | `#171E27` | hộp trung tính |
| Chữ chính | `#131A26` | `#E7ECF2` | |
| Chữ phụ | `#5A6675` | `#96A2B1` | chú thích |
| Đường kẻ | `#D9DFE6` | `#2B3644` | viền, kẻ ngang |
| **Chàm — cục bộ, miễn phí** | `#33507E` | `#8FB0E0` | viền + mũi tên |
| Nền chàm nhạt | `#EAEFF7` | `#1B2534` | hộp chạy cục bộ |
| **Nâu đồng — tốn API** | `#8F6317` | `#D8AC5B` | viền + mũi tên |
| Nền đồng nhạt | `#F7F0DE` | `#2A2417` | hộp gọi API |
| **Đỏ rượu — cổng chặn** | `#7A2E3C` | `#DE9AA6` | cổng lọc, cảnh báo |
| Nền rượu nhạt | `#F7E9EB` | `#2C1B20` | hộp cổng |

> Màu **mã hoá thông tin**, không trang trí: nhìn màu là biết chỗ nào tiêu tiền.
> Nếu in đen trắng, thay bằng: nét liền = cục bộ, nét đứt = API, nét đôi = cổng.

## 2.3 Chữ

| Vai | Font | Cỡ | Ghi chú |
|---|---|---|---|
| Nhãn băng | sans, 700 | 10,5 | HOA, giãn chữ 1,4 |
| Tiêu đề hộp | sans, 700 | 13,5 | |
| Nội dung hộp | serif hoặc sans, 400 | 11,5 | |
| Đường dẫn / hàm | mono, 400–600 | 10,5–13 | `snake_case` giữ nguyên |
| Nhãn mũi tên | sans, 400 | 10,5 | màu chữ phụ |
| Mã arm | mono, 600 | 14 | giãn chữ 0,6 |

Font gợi ý có dấu tiếng Việt đầy đủ: **Be Vietnam Pro** (tiêu đề),
**Source Serif 4** (nội dung), **IBM Plex Mono** (đường dẫn).

---

## 2.4 BĂNG 1 · NGUỒN — y 56 … 144

Ba hộp trung tính, mặt trắng, viền xám.

**1A · x 150, w 320**
```
Chroma KB                        (tiêu đề)
24.393 chunk                     (mono, chữ phụ)
guideline · pubmed · site VN/EN
mỗi chunk có prev/next
```

**1B · x 495, w 320**
```
policy_cases.jsonl               (tiêu đề, mono)
ca chính sách VIẾT TAY
hiện 2 dòng · human_written
chỗ duy nhất người soạn đề       (màu đỏ rượu)
```

**1C · x 840, w 320**
```
67 ca có hạn ngạch               (tiêu đề)
_build_cases()                   (mono, chữ phụ)
mỗi ca dò ĐÚNG một field
pregnant_true 30 · lesion_* 30…
```

---

## 2.5 BĂNG 2 · SINH — y 186 … 270

Hai hộp **nền đồng nhạt, viền nâu đồng** (tốn API).

**2A · x 150, w 665**
```
make_eval_set --generate                                    (tiêu đề)
Đưa 5 chunk cho LLM: "viết một câu hỏi mà mấy đoạn này trả lời được".
Sinh kèm barem: expected_answer_points · forbidden_claims · intent_label.
--n 100 --policy-n 45 · tốn API                             (mono, màu đồng)
```

**2B · x 840, w 320**
```
make_intake_set_v2                        (tiêu đề)
Mỗi ca đặt hàng trước thứ
nó phải sinh ra, rồi kiểm lại.
tốn API                                   (mono, màu đồng)
```

---

## 2.6 BĂNG 3 · CỔNG — y 292 … 338

Hai thanh ngang thấp, **nền rượu nhạt, viền đỏ rượu**.

**3A · x 150, w 665**
```
CỔNG LỌC   trùng lặp ngữ nghĩa · thiếu chunk vàng · sai schema
trượt thì sinh lại, không hạ chuẩn
```

**3B · x 840, w 320**
```
CỔNG LỌC   790 trượt / 1500 nhận
eval_cosine 401 · cue_missing 233 · exact_train 8      (mono, cỡ nhỏ)
```

---

## 2.7 BĂNG 4 · BỘ ĐỀ (đóng băng) — y 384 … 524

Hai hộp mặt trắng, **viền chàm dày 1,6 px** — đây là trung tâm của sơ đồ.

**4A · x 150, w 665, h 140**
```
active/generator_eval.v3_2_145.jsonl              (mono, đậm)
145 dòng · 100 kiến thức + 45 ca chính sách       (chữ phụ)
───────────────────────────────────────────────   (kẻ ngang)
user_query                        → vào hệ thống như người dùng gõ
relevant_chunk_ids                → CHỈ để bơm context cho arm ROR
intent_label · user_context       → CHỈ cho arm ORR
expected_answer_points · forbidden_claims
                                  → đi thẳng sang judge, KHÔNG vào hệ
```
Tên trường in đậm, phần sau mũi tên thường.

**4B · x 840, w 320, h 140**
```
active/intake_eval.v2_1500                        (mono, đậm)
1500 dòng hội thoại                               (chữ phụ)
────────────────────────────────
messages          → user gõ gì
assistant JSON    → gold 15 slot
meta.quota_path   → field mà dòng này được sinh để dò
```

---

## 2.8 BĂNG 5 · KHÂU 2 & KHÂU 1 — y 564 … 692

**5A · x 150, w 320** — mặt trắng, viền xám
```
KHÂU 2 · RAG                       (tiêu đề)
run_retrieval                      (mono, chữ phụ)
Chạy retriever thật, lấy 5 chunk,
judge chấm từng đoạn.
Bỏ ca reject/clarify → 120 câu     (chữ phụ)
KHÔNG dùng chunk vàng              (màu đỏ rượu)
```

**5B · x 840, w 320** — **nền chàm nhạt, viền chàm** (miễn phí)
```
KHÂU 1 · INTAKER                   (tiêu đề)
run_intake                         (mono, chữ phụ)
So JSON model trả với gold.
Chấm tất định, không cần judge.
MIỄN PHÍ · Ollama cục bộ           (màu chàm)
cắt lát theo quota_path            (chữ phụ)
```

---

## 2.9 BĂNG 6 · KHÂU 3 ABLATION — y 716 … 898

Một hộp **chiếm trọn chiều ngang**, x 150, w 1010, h 182, mặt trắng.

Dòng đầu:
```
KHÂU 3 · ABLATION    run_ablation    Arm = 3 ký tự [intaker][rag][generator]
                                     — R chạy thật · O bản hoàn hảo · N tắt hẳn
```
Kẻ ngang, rồi **một hàng sáu chip**, mỗi chip w 152, h 56, cách nhau 12:

| Chip | Nền | Dòng 1 (mono 14, đậm) | Dòng 2 | Dòng 3 |
|---|---|---|---|---|
| x 166 | chàm nhạt | `RRR` | mốc — sản phẩm | generator cục bộ |
| x 330 | chàm nhạt | `RNR` | RAG đóng góp gì? | generator cục bộ |
| x 494 | chàm nhạt | `ROR` | retriever dư địa? | generator cục bộ |
| x 658 | chàm nhạt | `ORR` | intaker đáng sửa? | generator cục bộ |
| x 822 | **đồng nhạt** | `RRO` | trần của generator | API gpt-5.6-terra |
| x 986 | **đồng nhạt** | `RNO` | model mạnh cần RAG? | API gpt-5.6-terra |

Ba dòng chú thích dưới hàng chip:
```
Mỗi arm ghép cặp với RRR TRONG CÙNG ARTIFACT → paired delta + bootstrap 95% CI.
Toàn bộ đi qua pipeline production thật: preprocess → guardrails → routing →
retrieval → prompt → generate.
Cắt đúng một khúc cuối: get_safety_suffix của runtime KHÔNG chạy — điểm an toàn
là của generator thô.                                       (màu đỏ rượu)
```

---

## 2.10 BĂNG 7 · CHẤM — y 944 … 1016

Một hộp **nền đồng nhạt, viền nâu đồng dày 1,6 px**, x 150, w 660.
```
JUDGE · gpt-5.6-luna     chấm mù — tên model không bao giờ vào prompt judge
4 mặt câu trả lời: answer_quality · role_tone · incorrect_content · missing_content
5 mặt context: relevance · precision · sufficiency · ranking_quality · groundedness
```

---

## 2.11 BĂNG 8 · KẾT QUẢ — y 1036 … 1120

Một hộp chiếm trọn chiều ngang, x 150, w 1010, mặt trắng.
```
reports/v2_full/                                            (mono, đậm)

intake/report.json       macro-F1 · lift theo quota_path
retrieval/results.json   5 mặt context · điểm theo source_type
ablation/results.json    6 arm + delta so RRR
ablation/rows.jsonl      từng câu trả lời — rescore được
```

---

## 2.12 Mũi tên — đầy đủ

| # | Từ | Đến | Nhãn | Màu |
|---|---|---|---|---|
| 1 | 1A đáy | 2A đỉnh | 1 hạt giống + 4 chunk kề | chàm |
| 2 | 1B đáy | 2A đỉnh | nối thêm | chàm |
| 3 | 1C đáy | 2B đỉnh | — | chàm |
| 4 | 2A đáy | 3A đỉnh | — | rượu |
| 5 | 2B đáy | 3B đỉnh | — | rượu |
| 6 | 3A đáy | 4A đỉnh | freeze sha256 → MANIFEST.json | chàm |
| 7 | 3B đáy | 4B đỉnh | — | chàm |
| 8 | 4A đáy (x 310) | 5A đỉnh | — | chàm |
| 9 | 4A đáy (x 620) | 6 đỉnh | cùng bộ đề — bắt buộc, nếu khác thì delta bắt cặp mất nghĩa | chàm |
| 10 | 4B đáy | 5B đỉnh | — | chàm |
| 11 | 5A đáy | 6 đỉnh | — | đồng |
| 12 | 6 đáy | 7 đỉnh | — | đồng |
| 13 | 5B đáy | 8 đỉnh (đi vòng bên phải, bỏ qua băng 7) | không gọi API | chàm |
| 14 | 7 đáy | 8 đỉnh | — | đồng |

Mũi tên 13 là mũi tên dài nhất và cố ý: nó cho thấy khâu 1 **không đi qua judge**.

---

## 2.13 Chú giải — đặt dưới cùng

```
■ chàm    chạy cục bộ, miễn phí
■ đồng    gọi API tính tiền
■ rượu    cổng chặn hoặc giới hạn đã biết
```

---

## 2.14 Ba điều sơ đồ phải nói được

Nếu bản vẽ ra mà người xem không rút được ba điều này thì bố cục đã hỏng:

1. **Tiền chỉ chảy ở ba chỗ** — hai bước sinh dữ liệu, hai arm trần, và judge.
   Mọi thứ còn lại chạy cục bộ.
2. **Hai nhánh dữ liệu tách nhau từ đầu tới cuối** và không bao giờ trộn; khâu 2
   với khâu 3 buộc phải dùng chung một bộ đề, còn khâu 1 dùng bộ riêng.
3. **Barem chấm điểm không bao giờ vào hệ thống** — `expected_answer_points` và
   `forbidden_claims` đi thẳng từ bộ đề sang judge.
