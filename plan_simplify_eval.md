# Eval — bản cuối

Eval làm đúng **4 khâu**, không làm gì khác.

| Khâu | Đo gì | Cần LLM chấm | Đọc từ |
|---|---|---|---|
| 1 | Intaker rút đúng 15 slot không | Không | arm `RRR` |
| 2 | RAG tìm đúng tài liệu không | Không | chạy riêng trên qrels |
| 3 | Generator viết tốt đến đâu khi input hoàn hảo | Có | arm `OOR` |
| 4 | Thay từng khâu bằng bản hoàn hảo, chênh bao nhiêu | Có | `RRR` vs `ORR`/`ROR`/`RRO` |

---

## Chạy gì

**Khâu 1, 3, 4** — một lệnh, 5 arm:

```bash
python -m ablation.run --arms RRR,ORR,ROR,RRO,OOR --cases ablation/data/cases.jsonl
python -m ablation.judge  --run ablation/runs/main.jsonl
python -m ablation.report --run ablation/runs/main.judged.jsonl
```

100 case × 5 arm = **500 lượt sinh + 500 lượt chấm**.
(Hiện tại: 1.100 sinh + 2.640 chấm.)

**Khâu 2** — chạy riêng, không tốn lượt sinh nào:

```bash
python -m ablation.retrieval --qrels evaluation/datasets/v1/retrieval_test.jsonl
```

---

## Khâu 2 dùng lại data có sẵn — không sinh mới

`evaluation/datasets/v1/retrieval_test.jsonl` đã có đủ, 100/100 dòng:

- `relevant_chunk_ids` — danh sách chunk đúng
- `relevance_grade` — chấm mức 0/1/2 cho nDCG có trọng số
- `annotation_status: approved`, đã relabel xong (0 `needs_relabel`)

Đây là thứ duy nhất trong `evaluation/datasets/v1` đáng giữ. **Không thêm
`golden_chunk_ids` vào case format ablation** — khâu 2 là bài đo riêng, dữ liệu
riêng, đã có sẵn và đã review tay.

Đo: `recall@k` · `precision@k` · `MRR` · **graded nDCG** · `hit@k`
Mode: `sparse` / `dense` / `hybrid` / `hybrid_rerank` / `hybrid_mmr_rerank`

---

## Việc phải làm

**1. `ablation/retrieval.py` — file mới, ~150 LOC**

Gộp closure 506 LOC hiện tại (`run_retrieval` 127 + `common` 113 + `registry` 92 +
`metrics/retrieval` 94 + `adapters/_repo` 80) thành 1 file:

- 4 hàm metric thuần, copy từ `evaluation/metrics/retrieval.py`
- vòng lặp 5 mode, copy `retrieve_ids()` từ `run_retrieval.py:29-45`
- container lấy từ `ablation/repo_adapter.container()` — đã có
- bỏ `registry.load_dataset` (kiểm sha256 manifest) → `read_jsonl` thẳng
- `demo()` self-check như các module ablation khác

**2. `ablation/report.py` — 406 → ~200 LOC**

Giữ §0 (bảng arm → khâu 3), §1 (headroom → khâu 4), §4 (slot accuracy → khâu 1),
thêm §2b (retrieval → khâu 2).

Bỏ: §2 Shapley, §3 interaction (cần 8 arm, ta chạy 5) · §5 propagation ·
§6 latency · §7 by tag · §8 regression · §9 length gaming.

**3. `ablation/run.py` — đổi default arms**

`FACTORIAL` (8 arm) → `RRR,ORR,ROR,RRO,OOR`.

**4. Sinh case set thật** ← việc chặn duy nhất, và là việc của người

```bash
python -m ablation.gen_cases --n 20 --seed 1 --source-dir guideline_docs \
       --out ablation/data/cases.dev.jsonl        # pilot, review tay
python -m ablation.gen_cases --n 80 --seed 2 --source-dir guideline_docs \
       --out ablation/data/cases.test.jsonl
```

`--source-dir` bắt buộc — không có nó, `golden_context` do model bịa và arm `ROR`
đo hư không. Case chưa review bị đánh dấu `needs_source_review`.

**5. Chạy, so số với artifact `evaluation/` cũ, rồi xóa trong 1 commit.**

---

## Còn lại 8 file, ~1.270 LOC

```
ablation/cases.py         137   schema case, chấm slot            khâu 1
ablation/gen_cases.py     121   sinh case set
ablation/repo_adapter.py  213   file DUY NHẤT import acne_llm, 3 seam
ablation/frontier.py      109   1 lệnh gọi API, cache đĩa
ablation/run.py           212   ma trận arm, resume được
ablation/judge.py         131   judge mù → sự kiện, điểm tính bằng Python
ablation/report.py       ~200   §0 §1 §2b §4                      khâu 1,3,4
ablation/retrieval.py    ~150   MỚI                               khâu 2
+ evaluation/datasets/v1/retrieval_test.jsonl   (data, 100 dòng)
```

Mỗi file có `demo()` chạy được không cần mạng, không cần Ollama.

## Xóa ~32.600 LOC

| Xóa | LOC |
|---|---:|
| `evaluation/` (trừ `datasets/v1/retrieval_test.jsonl`) | 16.842 |
| `evaluation/dashboard/` (Next.js + node_modules) | 9.920 |
| `scripts/eval_*.py`, `probe_*.py`, `gen_*.py`, `judge_agreement.py` | 7.029 |
| `src/acne_llm/eval/` | 131 |
| `tests/test_*eval*.py` (4 file), `run_eval_overnight.bat` | ~400 |

Kèm: `codex_*_prompt.md` (20 file) → `docs/history/`; xóa `overnight.log`,
`run2.log`, `run3.log`; `evaluation/reports/` 49 MB (37/41 thư mục là run debug
tháng 7 — **artifact thí nghiệm, bạn quyết**).

**33.922 → 1.270 LOC. Còn 3,7%.**

---

## Ba điều bỏ, nói rõ để bạn biết mình đang bỏ gì

**Shapley.** 5 arm cho biết khâu nào mất nhiều điểm nhất — đủ để quyết định sửa
cái gì. Nhưng ba số Δ không cộng thành tổng khoảng cách, nên không viết được câu
"RAG chịu trách nhiệm 45%". Cần thêm 3 arm (`ORO`, `ROO`, `OOO`) → 8 arm, đắt hơn
60%. Thêm sau được, không phải làm lại gì.

**Judge calibration.** Cả khâu 3 và 4 dựa trên một LLM judge chưa ai kiểm.
`evaluation/judges/calibrate.py` (Cohen's κ + Spearman) và `bias_tests.py` đang
có sẵn — port sang tốn ~230 LOC. Đây là thứ duy nhất trong danh sách xóa mà tôi
sẽ tranh luận nên giữ, vì không có nó thì mọi con số khâu 3/4 không phòng thủ
được trước hội đồng. Bạn quyết.

**828 case đã review tay** trong `datasets/v1` — giữ `retrieval_test` (khâu 2),
bỏ 7 bộ còn lại. Trong đó 488 case (safety, adversarial, out_of_scope,
hard_cases, multi_turn) **hiện đã không pipeline nào chạy**, nên không mất gì
thật. `answer_quality_test` 140 case thì đang dùng — nhưng nó thiếu rubric
`must_cover`/`must_not_say` nên không dùng trực tiếp làm case ablation được.
