# docs/

Mục lục để biết đọc cái nào. Quy tắc chung: **code là nguồn sự thật, tài liệu
giải thích *tại sao*.** Chỗ nào lệch thì tin code.

## Đang có hiệu lực

| File | Trả lời câu hỏi gì | Lưu ý |
|---|---|---|
| `config_reference.md` | Từng field trong `Settings` nghĩa là gì | Số đếm đã lệch — xem banner đầu file |
| `config_layout.md` | Config nằm ở đâu, `.env` vs `config.py` vs Modelfile | như trên |
| `DOCKER_QUICKSTART.md` | Chạy bằng Docker | |
| `EVAL_BLUEPRINT.md` | Hệ thống eval được thiết kế thế nào | |
| `schema_mapping.md` | Ánh xạ schema giữa các tầng | |
| `review_input_to_rag_to_prompt.md` | Một request đi qua những đâu | |
| `DATA_GEN_GIAI_THICH.md` | Pipeline sinh dữ liệu fine-tune | |
| `dashboard_phan_tich_workflow.md` | `research/dashboards/` sinh ra gì | |

## Bản ghi quyết định — đọc để biết *vì sao*, không phải *đang là gì*

| File | Ghi lại việc gì | Trạng thái |
|---|---|---|
| `CLEANUP_PLAN.md` | Dọn cấu trúc thư mục top-level | Đợt 0-2 xong 2026-08-14 |
| `CLEANUP_TASKS.md` | Các phase gỡ dead code trong runtime | phần lớn đã thực hiện |
| `DEAD_CODE.md` | Danh sách code chết đã xác minh từng dòng | |
| `rulebase_audit.md` | Kiểm kê rule-base trước khi cắt | baseline trước Phase 7 |
| `evaluation_refactor_evidence.md` | Bằng chứng cho đợt refactor evaluation | |

Bốn file đầu nhóm này chồng lấn nhau về chủ đề "cần dọn gì". Chúng **không**
được gộp vì mỗi cái ghi một quyết định ở một thời điểm khác nhau — gộp lại thì
mất dấu ai quyết gì, lúc nào. Đọc theo thứ tự thời gian, đừng đọc như spec.

## `archive/`

Prompt và plan đã xong việc, giữ để truy vết. **Không phải tài liệu đang có
hiệu lực.** `CONFIG_MAP.md` nằm ở đây vì nó nói 85 field trong khi thực tế là 73.

## `reports/`

Báo cáo dài: `context.md`, `report.md`, `runtime_audit.md`, `smoke_review.md`.
