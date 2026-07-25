# PROMPT — Thêm tab "Semantic Router Probe" vào Eval Dashboard

> Copy toàn bộ prompt dưới đây vào Claude Code / Codex / agent, chạy từ repo root `AcneLLM/`.
> Mục tiêu: gõ 1 câu tiếng Việt → xem embedding intent router (`SemanticRouter`) phân loại
> có đúng không, và TẠI SAO (neighbor nào, khoảng cách OOS, biên ambiguity).

---

Bạn là senior fullstack engineer. Thêm MỘT tab mới tên **"Router Probe"** vào Eval Dashboard
Next.js hiện có. KHÔNG sửa logic trong `src/acne_llm/` (chỉ được thêm 1 file probe mới ở
`evaluation/`). KHÔNG đụng `frontend/` (chat UI production). Chỉ thêm: 1 script Python probe +
1 tab dashboard + 1 entry whitelist.

## 0. Bối cảnh repo (ĐÃ XÁC MINH — không cần khám phá lại)

Router embedding thật nằm ở `src/acne_llm/chat/semantic_router.py`:

- Class `SemanticRouter`. Hàm chẩn đoán đầy đủ:

  ```python
  def predict(self, text: str, *, k=None, oos_distance_threshold=None,
              ambiguity_margin=None) -> SemanticPrediction
  ```

  (hàm production `classify(text) -> RouteDecision` chỉ trả kết quả gọn; **dùng `predict()`**
  vì nó trả full diagnostics và cho override 3 tham số để thử live.)

- `SemanticPrediction` (dataclass, frozen) có các field CẦN hiển thị:
  - `primary_intent`: một trong `"advise" | "knowledge" | "clarify" | "reject"`
    - `"reject"` = OOS (khi `nearest_distance > oos_distance_threshold`)
    - `"clarify"` = mơ hồ (khi `vote_margin < ambiguity_margin`, và winner ≠ clarify)
  - `nearest_similarity` (float), `nearest_distance` (float = 1 − similarity)
  - `vote_scores`: dict `{intent: score}` cho 3 lớp in-scope (advise/knowledge/clarify), tổng = 1
  - `vote_margin` (float = top − second)
  - `neighbor_labels`: tuple[str] (nhãn của k hàng train gần nhất, đã sort giảm dần)
  - `neighbor_similarities`: tuple[float] (similarity tương ứng)
  - `ambiguity_reason`: str | None (chuỗi giải thích khi reject/clarify)

- Lớp in-scope: `advise`, `knowledge`, `clarify` (xem `_IN_SCOPE_INTENTS`). OOS → `reject`.

- Cách dựng router (SAO CHÉP y hệt di.py, `build_container`, ~dòng 250–300):

  ```python
  from acne_llm.config import settings
  from acne_llm.rag.embedder import Embedder
  from acne_llm.chat.semantic_router import SemanticRouter

  emb_model = getattr(settings, "embedding_model_multilingual", "") or settings.embedding_model
  embedder = Embedder(model_name=emb_model, device=settings.device)
  router = SemanticRouter(
      embedder=embedder,
      train_path=getattr(settings, "semantic_router_train_path", "./data/intent_classify.train.jsonl"),
      cache_path=getattr(settings, "semantic_router_cache_path", "./data/intent_router_index.npz"),
      k=int(getattr(settings, "semantic_router_k", 9)),
      oos_distance_threshold=float(getattr(settings, "semantic_router_oos_distance_threshold", 0.483609)),
      ambiguity_margin=float(getattr(settings, "semantic_router_ambiguity_margin", 0.08)),
  )
  ```

- Config mặc định: `k=9`, `oos_distance_threshold=0.483609`, `ambiguity_margin=0.08`,
  index cache `./data/intent_router_index.npz`, train `./data/intent_classify.train.jsonl`
  (mỗi dòng `{"text": ..., "intent": "advise|knowledge|clarify"}`).
- Chạy Python: Windows, venv `.venv\Scripts\python.exe` (fallback `python`), từ repo root.

## 1. Script probe (file MỚI: `evaluation/probe/semantic_probe.py`)

Argparse:

```
python -m evaluation.probe.semantic_probe --text "<câu>" [--k N] [--oos F] [--margin F] \
    [--expect advise|knowledge|clarify|reject] [--neighbors] --json
```

Hành vi:
1. Dựng `SemanticRouter` đúng như §0 (embedder + index cache — index đã cache nên KHÔNG rebuild;
   embedder vẫn load mỗi lần, chấp nhận được cho tab test tay).
2. Gọi `router.predict(text, k=..., oos_distance_threshold=..., ambiguity_margin=...)`
   (chỉ truyền override khi flag có mặt; None thì dùng mặc định của router).
3. In ra STDOUT **đúng 1 dòng JSON** gồm: toàn bộ field của `SemanticPrediction` (dataclass →
   `dataclasses.asdict`), cộng thêm:
   - `effective_k`, `effective_oos_threshold`, `effective_margin` (giá trị thực đã dùng)
   - `model_name` (`router.model_name`), `indexed_rows` (`router.indexed_rows`)
   - `correct`: bool | null — `primary_intent == --expect` nếu có `--expect`, else null
4. **`--neighbors` (tùy chọn nhưng nên làm):** để hiển thị *câu train* mà query khớp — cực kỳ
   hữu ích để phán "đúng/sai". `predict()` không trả index hàng train. Cách rẻ nhất KHÔNG sửa
   `semantic_router.py`: trong probe, đọc `train_path` (jsonl) và với mỗi `(label, sim)` trong
   `neighbor_labels/neighbor_similarities`, tìm dòng train **đầu tiên chưa dùng** có `intent==label`
   để hiển thị text gần đúng. (Nếu muốn chính xác tuyệt đối theo index, thêm `neighbor_indices`
   vào `SemanticPrediction` — 1 dòng — nhưng đó là sửa src, để tùy chọn.) Trả thêm mảng
   `neighbors: [{rank, label, similarity, text}]`.
5. Lỗi (text rỗng, embedder fail, dim mismatch) → in `{"error": "..."}` một dòng, exit code ≠ 0.

## 2. Whitelist command

Thêm vào bảng lệnh hợp lệ của dashboard (cùng cơ chế các lệnh khác):

| id | Lệnh |
|----|------|
| `probe_semantic` | `python -m evaluation.probe.semantic_probe --text "<TEXT>" [--k N] [--oos F] [--margin F] [--expect X] --neighbors --json` |

`<TEXT>` truyền từ input người dùng — **phải escape/quote an toàn** (shell injection: dùng
`spawn` với mảng args, KHÔNG nối chuỗi vào shell).

## 3. Tab "Router Probe" (Next.js)

**Input:**
- 1 textarea "Câu người dùng (tiếng Việt)".
- (tùy chọn, collapsible "Thresholds") 3 input số: `k` (default 9), `oos_distance_threshold`
  (default 0.483609), `ambiguity_margin` (default 0.08) — để thử live xem đổi ngưỡng thì quyết
  định đổi ra sao. Bỏ trống = dùng mặc định.
- (tùy chọn) dropdown "Kỳ vọng" (advise/knowledge/clarify/reject) → truyền `--expect`.
- Nút **Run**. Enter trong textarea cũng chạy.

**Output (render từ JSON):**
1. **Verdict lớn:** `primary_intent`, tô màu — `reject`=đỏ, `clarify`=hổ phách, `advise`/`knowledge`=xanh.
   Nếu có `--expect`: badge ✅/❌ theo `correct`.
2. **Cổng OOS:** thanh so `nearest_distance` vs `effective_oos_threshold`
   ("distance 0.42 ≤ threshold 0.48 → IN-DOMAIN" hoặc "> → REJECT"). Hiện `nearest_similarity`.
3. **Vote scores:** bar chart 3 lớp (advise/knowledge/clarify) từ `vote_scores`; đánh dấu winner.
4. **Cổng ambiguity:** `vote_margin` vs `effective_margin`
   ("margin 0.05 < 0.08 → CLARIFY" hoặc "≥ → giữ winner"). Hiện `ambiguity_reason` nếu có.
5. **Bảng neighbors (k dòng):** rank | label (tô theo lớp) | similarity | text (nếu `--neighbors`).
   Đây là phần để mắt người phán "khớp có hợp lý không".
6. Footer nhỏ: `model_name`, `indexed_rows`, 3 giá trị effective threshold đã dùng.

**Trạng thái:** loading khi chạy; hiện `error` gọn nếu script fail; giữ kết quả lần trước tới khi có kết quả mới.

## 4. (Tùy chọn) Batch mini
Cho dán nhiều dòng (mỗi dòng 1 câu, có thể `\t<expect>`), chạy tuần tự, ra bảng
text | predicted | expected | ✅/❌ | nearest_sim, kèm accuracy tổng. Giữ đơn giản, không bắt buộc.

## 5. Ràng buộc
- KHÔNG sửa `src/acne_llm/chat/semantic_router.py` (trừ khi bạn chủ động chọn thêm 1 dòng
  `neighbor_indices` cho §1.4 — nếu làm thì giữ backward-compatible, field optional default None).
- Chỉ thêm `evaluation/probe/semantic_probe.py` + `evaluation/probe/__init__.py`.
- Args truyền qua mảng (spawn), không nối shell.
- Không rebuild index (dùng cache `.npz` sẵn có); nếu cache thiếu, để `_ensure_index` tự dựng
  và báo "đang dựng index lần đầu…".
- Xong: chạy thử 3 câu để tự kiểm — 1 knowledge rõ ("mụn đầu đen hình thành thế nào?"),
  1 advise rõ ("da mình mụn viêm nhiều nên dùng gì?"), 1 OOS ("giá vàng hôm nay bao nhiêu?") —
  và xác nhận lần lượt ra `knowledge`, `advise`, `reject`.
