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
as_of: 2026-08-23
baseline_commit: 585333cc68d6e29b666337bdf366c99e00abc9b7
branch: codex/simplify-chat-pipeline
---

# AcneLLM current truth

Đây là điểm vào canonical cho trạng thái repo sau safe remediation. Khi nội
dung ở đây mâu thuẫn với snapshot audit ngày 2026-08-22, nội dung ở đây thắng
nếu có evidence source/test tương ứng. Source live vẫn là nguồn thắng cuối cùng.

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

- Full test: `495 passed, 1 xfailed`.
- Unified intake targeted suite: `37 passed`.
- Chat stream targeted suite: `24 passed`.
- Compile/import checks: pass; `Settings` có `66` fields.
- Grep gates: không active legacy intake class/import/config; semantic/rule
  fallback vẫn tồn tại.
- `git diff --check`: pass.
- Bốn eval artifact được bảo toàn hash; xem [[SAFE_REMEDIATION_TASKS]].

## Điều chưa được chứng minh lại

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
- Quy tắc chọn nguồn: [[CONTEXT_INTEGRITY]].
- Bản đồ tri thức: [[KNOWLEDGE_INDEX]].
