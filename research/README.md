# research/

Không có gì trong thư mục này phục vụ một request runtime. Dockerfile không
copy nó; `docker-compose` không mount nó.

| Thư mục | Là gì |
|---|---|
| `dashboards/` | Script sinh dashboard và sơ đồ kiến trúc (trước đây là `visualization/`); ảnh/HTML đầu ra không được track để giữ repo gọn |
| `dataset_viz/` | Biểu đồ phân bố dataset (trước đây là `visualize/`) |
| `notebooks/` | Notebook thăm dò |

Hai cái tên `visualization/` và `visualize/` cũ đứng cạnh nhau ở root và không
nói lên chúng khác nhau ở chỗ nào. Đổi tên khi chuyển, xem `docs/CLEANUP_PLAN.md`.

Các package offline còn lại (`datagen/`, `evaluation/`, `LLMData/`,
`guideline_docs/`) cũng đã nằm ở đây — chúng import chéo nhau bằng tên tuyệt đối
nên `research` phải có trong `PYTHONPATH` (`pyproject.toml` và `tasks.sh` đã lo).

`ablation/` (oracle-substitution eval, 2³ factorial + Shapley) đã bị **xoá**: không
file nào ngoài nó import nó, nó chưa từng có `data/cases.jsonl`, và khâu ablation
đang dùng thật là `evaluation/runners/run_ablation.py`.
