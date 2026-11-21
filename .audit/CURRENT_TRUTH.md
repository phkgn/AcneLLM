---
title: AcneLLM Current Truth
aliases:
  - Current Truth
  - Repository Truth
tags:
  - acnellm
  - architecture
  - current
status: verified-current
as_of: 2026-08-25
baseline_commit: 487a7f614e628b804e693992060465fe54275e37
audit_run: 20260825T090826Z
branch: codex/simplify-chat-pipeline
---

# AcneLLM current truth

Đây là điểm vào canonical cho trạng thái repo sau safe remediation và context
refresh ngày 2026-08-25. Khi nội dung ở đây mâu thuẫn với snapshot audit cũ,
nội dung ở đây thắng nếu có evidence source/test tương ứng. Source live vẫn là
nguồn thắng cuối cùng.

## Mức chứng minh

- `verified-current`: đã đối chiếu source sau remediation và có test/grep/import.
- `historical`: đúng tại immutable run `20260822T152307Z`, không tự carry-forward.
- `planned`: chưa triển khai; chỉ nằm trong roadmap.
- `unverified-runtime`: cần model/service/eval thật, không suy từ unit test.

## Kiến trúc production hiện hành

Luồng intake cố định:

```text
Unified Intaker (acne-intaker; LLM intake duy nhất)
  -> SemanticRouter (local embedding; không LLM)
  -> rule router + rule extractor (deterministic; không LLM)
```

`src/acne_llm/di.py::build_container` dựng đúng một `UnifiedIntake`.
`llm_router` và `llm_extractor` là hai tên interface cùng trỏ vào instance đó.
Success path dùng một inference chung; model/JSON/intent failure rơi semantic,
sau đó dùng rule extraction và không retry một LLM intake thứ hai.

Runtime config intake chỉ còn:

- `INTAKE_MODEL` / `Settings.intake_model`.
- `INTAKE_TIMEOUT` / `Settings.intake_timeout`.

Không còn active intake mode, dedicated LLM router/extractor class hoặc config
router/extractor. `model/legacy/**` chỉ là archive nghiên cứu.

## Pipeline trả lời

1. API chat nhận message và session id.
2. `chat/intake.py` preprocess, đọc history, chạy hard input checks và intake.
3. `chat/orchestrator.py` quyết retrieval/template từ `IntakeResult`.
4. `chat/_retrieval.py` chạy hybrid retrieval, guideline/safety pass, rerank và
   chunk filters khi RAG khả dụng.
5. Generator stream prose; `chat/_safety.py` xử lý safety output.
6. User/assistant turns được persist bằng SQLite session store.

## Safety ownership

- `guardrails/runner.py`: hard input guards và medication policy.
- `intent_router.compute_route_flags`: tín hiệu text cho prompt/output; không
  phải một refusal gate độc lập.
- `chat/_safety.py`: output-side dose/self-use và safety suffix.
- Semantic/rule router là fallback availability, không phải safety authority.
- Product-ingredient metadata flag cũ đã xóa vì không có behavioral consumer.

## Contract đã thống nhất

- `RouteDecision.metadata.primary_intent`: intent nghiệp vụ.
- `RouteDecision.metadata.turn_type`: đúng turn type, mặc định `answer`.
- Semantic confidence là clipped `nearest_similarity`, không phải xác suất đã
  calibration.
- Production session persistence chỉ dùng `SQLiteSessionStore`.
- In-memory `SessionStore` chỉ tồn tại dưới `tests/helpers` và mỗi owner nhận
  store độc lập.

## Evidence hiện tại

- Immutable capture `20260825T090826Z`: 837/837 path (833 tracked + 4
  non-ignored untracked ngoài `.audit`), gồm 589 semantic capture, 205 skip có
  lý do và 42 `.audit/**` exclusion chống tự đệ quy. Dynamic gate xác minh
  590/590 snapshot, 0 hash mismatch, 10.335 block và 82.680/82.680 mục 1-8.
- Full test: `495 passed, 1 xfailed in 53.86s` — chạy lại 2026-08-25 bằng repo
  venv trên chính worktree đã capture.
- Unified intake targeted suite: `37 passed`.
- Chat stream targeted suite: `24 passed`.
- Compile/import checks: pass; `Settings` có `66` fields.
- Grep gates: không active legacy intake class/import/config; semantic/rule
  fallback vẫn tồn tại.
- `git diff --check`: pass.
- Bốn eval artifact được bảo toàn hash; xem [[SAFE_REMEDIATION_TASKS]].
- Hiệu chuẩn judge bằng người, arm `RRR`, n = 145 (2026-08-24):
  `answer_quality` κ 0,4653 / κ_quad 0,5338 / AC1 0,521;
  `incorrect_content` κ 0,4049 / κ_quad 0,5663 / AC1 0,487;
  `missing_content` κ 0,2126 / AC1 0,276; `role_tone` κ 0,1829 / AC1 0,599.
  Cả bốn trục nằm trong `khong_du_tin_cay` theo ngưỡng κ_quad ≥ 0,61.
  Artifact: `calibration_rrr/judge_calibration_rrr145.json` và
  `calibration_rrr/ket_qua_rrr145.json`.
- Chất lượng tuyệt đối theo người trên `RRR`: 3,076/5 (judge 2,779).
- Cổng an toàn do judge suy luận có precision thấp: `harmful_incorrect_content`
  0,50 và `forbidden_claim` 0,42. Hệ thống báo 32 hàng safety fail, người xác
  nhận 24 — thừa 12, thiếu 4.

Worktree tại capture không sạch. Ba non-audit untracked path và các thay đổi ở
Chroma/Judge SQLite cùng `research/dataset_viz/README.md` đã được ghi nguyên
trạng trong manifest. Chúng không thay đổi wiring production được mô tả ở trên,
nhưng commit SHA một mình không đủ mô tả source state của mọi artifact.

## Điều chưa được chứng minh lại

- Hiệu chuẩn người đã **chốt ở phạm vi**: một arm (`RRR`), một người chấm,
  bốn trục answer. Đây là quyết định phạm vi, không phải hạng mục làm dở.
  Hạn chế đã biết, đồng thời là hướng phát triển: chưa có inter-annotator
  agreement; người chấm không phải chuyên gia da liễu nên vòng này kiểm thang
  rubric chứ không kiểm tính đúng đắn lâm sàng; chưa có arm đối chứng nên không
  delta nào có bằng chứng người; 5 trục context của `judges/context.py` chưa
  từng được đối chiếu.
- Không chạy full intake evaluation 1.490 mẫu sau remediation.
- Không chạy retrieval evaluation/RAG ablation mới.
- Không chạy generator T3 mới hoặc lane T4/SSE production parity.
- Không chứng minh model/service readiness từ unit tests.

Các thay đổi có thể làm lệch hành vi nằm trong [[FUTURE_BEHAVIOR_ROADMAP]].

## Nguồn liên quan

- Runtime architecture chi tiết: `../docs/ARCHITECTURE_TRUTH.md`.
- Remediation evidence: [[SAFE_REMEDIATION_TASKS]].
- Snapshot toàn repo trước remediation: [[ARCHITECTURE]] và release asset
  [`audit-run-20260822T152307Z.zip`](https://github.com/phkgn/AcneLLM/releases/download/knowledge-2026-08-23/audit-run-20260822T152307Z.zip).
- Snapshot context hiện tại: `runs/20260825T090826Z/` và
  `runs/20260825T090826Z/SNAPSHOT_GATE.md`.
- Fact ledger bảo vệ: [[SLIDE_FACT_CHECK_2026-08-25]].
- Cấu trúc slide E2E đề xuất:
  `../docs/presentations/AcneLLM_Defense_E2E_Context_2026-08-25.md`.
- Quy tắc chọn nguồn: [[CONTEXT_INTEGRITY]].
- Bản đồ tri thức: [[KNOWLEDGE_INDEX]].
