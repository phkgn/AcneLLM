---
title: AcneLLM Audit Reconciliation
tags:
  - acnellm
  - audit
  - reconciliation
status: verified-current
as_of: 2026-08-25
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

## Delta 2026-08-24 — khóa parity deploy/eval

Trước: default generator là `acne-generator`, `docker/ollama-init.sh` dựng nó từ
`Modelfile.full` (GGUF round 1 + system prompt sha `36b70b7a…`). `v2_full` lại
chấm `acne-generator-v2` (GGUF `acnellm-role-v2` + system prompt sha
`5421f207…`). Deployment mặc định vì thế phục vụ một bộ trọng số và một prompt
mà không con số eval nào đo trên nó.

Sau: `config.py::llm_model`, hai chỗ trong `docker-compose.yml`,
`docker/ollama-init.sh`, `.env.baseline` và `.env.docker.example` đều trỏ vào
`acne-generator-v2` dựng từ `acnellm-role-v2.Q4_K_M.gguf` + `Modelfile`.

Supersedes: claim số 5 trong `SLIDE_FACT_CHECK_2026-08-23.md`
("`acne-generator-v2` không phải model Compose mặc định") — đúng tại 2026-08-23,
`historical` từ 2026-08-24. Không sửa ledger đó; đọc kèm delta này.

Behavior impact: **answer-changing** đối với ai đang chạy bằng default cũ.

Đã xác minh 2026-08-24: `pytest -q` → `495 passed, 1 xfailed` trên worktree sau
thay đổi. **Chưa** chạy smoke SSE trên gói mới — pytest không chạm endpoint thật,
nên parity ở mức runtime vẫn là `unverified-runtime`.

Kèm theo trong cùng đợt: `Settings.intake_timeout` 60 → 120 giây và
`tests/chat/test_unified_intake.py` cập nhật theo. Đây không phải thay đổi mới mà
là kéo default Python về khớp deployment — `docker-compose.yml` đã đặt
`INTAKE_TIMEOUT` mặc định 120 và `.env.docker.example` cũng 120 từ trước. Trước
đợt này worktree bẩn ở đúng dòng đó nên full suite thực tế đang đỏ 1 test dù HEAD
xanh; con số `495 passed` trong tài liệu chỉ đúng cho HEAD, không đúng cho
worktree. Nay cả hai cùng xanh.

Còn một nguồn truth thừa chưa dọn: `src/acne_llm/di.py:134` vẫn hardcode `60.0`
làm fallback cho cùng giá trị. Nhánh đó không bao giờ chạy vì `Settings` luôn có
thuộc tính, nên không gây lỗi.

## Delta 2026-08-24 — deck bảo vệ sửa theo hai thay đổi trên

`docs/presentations/AcneLLM_Project_E2E_20min_Scientific_Verified.pptx` sửa bốn
slide: 11 (parity — từ "KHÔNG KHỚP" sang "ĐÃ KHỚP", đổi khối runtime sang xanh),
20 (hạn chế 03 — từ "judge chưa hiệu chuẩn" sang "hiệu chuẩn còn hẹp", kèm κ có
trọng số 0,53), 21 (P0 → XONG), 22 (kết luận). Speaker notes của bốn slide viết
lại, giữ khối `[Sources]`. Speaker script `..._SPEAKER_SCRIPT.txt` sửa theo.

QA: `validate.py --original` pass; render lại bốn slide, không tràn chữ;
22/22 slide vẫn có `[Sources]`.

Supersedes: mục "Presentation artifact and QA" trong
`SLIDE_FACT_CHECK_2026-08-23.md` ghi SHA-256 `DDA6589A…D8F8`. SHA đó `historical`
— deck đã lưu lại sau khi ledger viết, và sửa thêm lần này. Không sửa ledger;
muốn hash hiện hành thì băm lại file.

## Delta 2026-08-25 — current snapshot, context và cấu trúc bảo vệ

Một immutable capture mới được tạo tại `runs/20260825T090826Z/` trên HEAD
`487a7f614e628b804e693992060465fe54275e37`. Scope dùng toàn bộ 833 tracked path
và 4 non-ignored untracked path ngoài `.audit`; 42 file `.audit/**` được ghi
`exclude` có lý do để tránh audit tự đệ quy. Kết quả: 590 semantic capture, 205
skip có lý do, 590/590 snapshot đúng hash, 10.335 block và 82.680/82.680 mục
1-8. Gate động `SNAPSHOT_GATE.md` PASS.

Full test được chạy lại bằng repo venv trên cùng checkout:
`495 passed, 1 xfailed in 53.86s`. Không chạy model service, SSE smoke hoặc full
behavior evaluation, nên các ranh giới `unverified-runtime` giữ nguyên.

Context bảo vệ được materialize thành hai artifact:

- `SLIDE_FACT_CHECK_2026-08-25.md`: current code/data/audit truth và claim
  boundary; ledger 2026-08-23 giữ nguyên như historical.
- `docs/presentations/AcneLLM_Defense_E2E_Context_2026-08-25.md`: cấu trúc 22
  slide chính, appendix, evidence map và timing 20 phút.

Binary deck hiện tại không bị sửa trong delta này. Hash deck đã duyệt được ghi
trong fact ledger mới để tránh nhầm “đề xuất cấu trúc” với “đã sửa PPTX”.

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
