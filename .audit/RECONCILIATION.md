---
title: AcneLLM Audit Reconciliation
tags:
  - acnellm
  - audit
  - reconciliation
status: verified-current
as_of: 2026-08-23
---

# Reconciliation sau remediation

Mục đích của note này là nối immutable one-pass audit ngày 2026-08-22 với cây
source sau remediation, không sửa hoặc giả vờ regenerate snapshot cũ.

## Hai lớp bằng chứng

| Lớp | Vai trò | Có được coi là current? |
|---|---|---|
| `runs/20260822T152307Z/**` | Snapshot đầy đủ 783 path trước remediation | Không; historical |
| `SAFE_REMEDIATION_TASKS.md` | Delta đã triển khai + test/hash gates | Có, cho delta được nêu |
| `CURRENT_TRUTH.md` | Synthesis hiện hành từ snapshot + delta | Có, entrypoint canonical |
| `FUTURE_BEHAVIOR_ROADMAP.md` | Hướng phát triển chưa làm | Không; planned |

## Delta kiến trúc đã reconcile

### Đã thêm

- `src/acne_llm/chat/intake_contract.py`: shared fallback exceptions.
- `tests/helpers/session_store.py`: in-memory store test-only.
- `tests/__init__.py`, `tests/helpers/__init__.py`: test package boundary.
- `docs/ARCHITECTURE_TRUTH.md`: canonical runtime architecture.
- Hai remediation/roadmap ledger trong `.audit`.

### Đã xóa khỏi active source

- `src/acne_llm/chat/routing/llm_router.py`.
- `src/acne_llm/chat/routing/llm_extractor.py`.
- `src/acne_llm/chat/session/memory.py`.
- Hai test suite chỉ dành cho legacy adapters.

### Đã đổi contract

- DI luôn dựng một Unified Intaker.
- Legacy intake settings bị hard-remove.
- Unified failure không retry extraction LLM.
- `turn_type` không còn giả làm primary intent.
- Dead product metadata flag bị xóa.
- Production session package không export in-memory store.
- API log dùng `runtime_*`; crawler giữ `crawl_*`.

## Findings cũ bị supersede

Mọi finding/claim nói các điều sau chỉ còn giá trị lịch sử:

- runtime có `INTAKE_MODE=legacy|unified`;
- dedicated `LLMRouter` hoặc `LLMExtractor` còn active;
- `extractor_mode` điều khiển normal path;
- `chat.session` export singleton in-memory store;
- `turn_type="answer"` bị thay bằng primary intent;
- `product_safety_check` là active route metadata.

Không xóa các finding đó vì chúng giải thích vì sao remediation tồn tại. Khi
đưa vào Obsidian, chúng phải mang quan hệ `superseded-by: CURRENT_TRUTH`.

## Khu vực giữ nguyên có chủ ý

- `model/legacy/**`: archive nghiên cứu, không active runtime.
- `docs/archive/**`, `docs/history/**`: historical documents.
- Eval reports cũ: historical baseline, hash được bảo toàn.
- Các dirty path đã có trước remediation được ghi trong
  [[SAFE_REMEDIATION_TASKS]]; không được tự quy thành thay đổi remediation.

## Giới hạn reconciliation

Đây là delta reconciliation, không phải semantic one-pass lần hai của 783 path.
Các file không thuộc remediation tiếp tục dùng evidence từ snapshot 22/08.
Nếu chúng thay đổi về sau, phải tạo delta mới hoặc chạy audit snapshot mới.
